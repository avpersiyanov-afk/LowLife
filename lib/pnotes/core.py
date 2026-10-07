# -*- coding: utf-8 -*-
"""Заметки по проекту: настройки, связь с Google Таблицей, сведения из модели."""
import os
import io
import json
import uuid
import time
import datetime
import threading

import clr
clr.AddReference('System')
import System
from System.Net import (HttpWebRequest, ServicePointManager, SecurityProtocolType, CredentialCache,
                        WebException, WebExceptionStatus)
from System.IO import StreamReader, IOException
from System.Text import Encoding

from Autodesk.Revit.DB import (BuiltInParameter, StorageType, ModelPathUtils, ElementId, ViewSheet, View,
                               FilteredElementCollector)


# lib/pnotes/core.py → три уровня вверх = корень расширения (корень репозитория LowLife)
EXT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
USER_DIR = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'pyRevit', 'ProjectNotes')

# config.json в корне расширения не коммитится (.gitignore) — репозиторий публичный.
# Обычно адрес и токен вводятся в окне «Настройка» и лежат в USER_CONFIG.
EXT_CONFIG = os.path.join(EXT_DIR, 'config.json')
USER_CONFIG = os.path.join(USER_DIR, 'config.json')
SETTINGS_CACHE = os.path.join(USER_DIR, 'settings_cache.json')
NOTES_CACHE = os.path.join(USER_DIR, 'notes_cache.json')
QUEUE_FILE = os.path.join(USER_DIR, 'queue.json')
STATE_FILE = os.path.join(USER_DIR, 'state.json')

STATUS_OPEN = u'Открыто'
STATUS_WORK = u'В работе'
STATUS_DONE = u'Выполнено'
STATUS_CANCEL = u'Отменено'
STATUS_PENDING = u'Не отправлено'
CLOSED = (STATUS_DONE, STATUS_CANCEL)
# Тип «Вопрос» нельзя закрыть как «Выполнено» без «Решения» (то же правило в Code.gs)
QUESTION_TYPE = u'Вопрос'

# Значение параметра «код проекта», означающее «брать имя файла модели»
FILE_KEY = u'(имя файла модели)'

DEFAULT_SETTINGS = {
    'types': [u'Замечание', u'Задача', u'Вопрос', u'Напоминание', u'Решение', u'Идея'],
    'sections': [u'Общее', u'АР', u'КР', u'ОВиК', u'ВК', u'ЭОМ', u'СС', u'ТХ', u'ГП', u'ПОС'],
    'people': [],
    'key_param': u'',
    'name_param': u'',
    'extra_params': [],
    'remind_days': 1,
    'remind_on_open': True,
    'sheet_url': u'',
}

# Служебные встроенные параметры, которые нет смысла показывать при анализе
SKIP_BIP_PREFIXES = ('ELEM_', 'EDITED_BY', 'IFC_', 'DESIGN_OPTION', 'PHASE_', 'SYMBOL_', 'ALL_MODEL_')


class ApiError(Exception):
    pass


def err_text(ex):
    # У собственных исключений текст — в args; у .NET-исключений — в Message
    if isinstance(ex, ApiError) and ex.args:
        return u'{}'.format(ex.args[0])
    msg = getattr(ex, 'Message', None)
    if msg:
        return msg
    try:
        return u'{}'.format(ex)
    except Exception:
        return u'ошибка'


# ---------------------------------------------------------------- файлы

def _read_json(path, default=None):
    try:
        with io.open(path, 'r', encoding='utf-8-sig') as f:
            return json.loads(f.read())
    except Exception:
        return default


def _dumps(data, indent=None):
    """json.dumps с ASCII-результатом, безопасный для IronPython.

    Стандартный ensure_ascii=True в IronPython (pyRevit на части машин, напр. Revit 2022) падает на
    любой кириллице: UnicodeEncodeError 'ascii' codec can't encode character. Поэтому строим текст
    с ensure_ascii=False и сами заменяем не-ASCII символы на \\uXXXX — результат тот же, что у CPython.
    """
    text = json.dumps(data, ensure_ascii=False, indent=indent)
    out = []
    for ch in text:
        code = ord(ch)
        if code < 128:
            out.append(ch)
        elif code > 0xFFFF:  # CPython 3: символ вне BMP — суррогатная пара
            code -= 0x10000
            out.append(u'\\u{:04x}\\u{:04x}'.format(0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)))
        else:
            out.append(u'\\u{:04x}'.format(code))
    return u''.join(out)


def _write_json(path, data):
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    text = _dumps(data, indent=2)  # чистый ASCII
    with io.open(path, 'w', encoding='utf-8') as f:
        f.write(u'' + text)


def load_state():
    return _read_json(STATE_FILE, {}) or {}


def save_state(**values):
    state = load_state()
    state.update(values)
    try:
        _write_json(STATE_FILE, state)
    except Exception:
        pass


# ---------------------------------------------------------------- подключение

def _config_file(path):
    data = _read_json(path, {}) or {}
    return (data.get('url') or u'').strip(), (data.get('token') or u'').strip()


def load_config():
    """Общий config.json из папки расширения; личный из %APPDATA% его перекрывает."""
    url, token = _config_file(EXT_CONFIG)
    u_url, u_token = _config_file(USER_CONFIG)
    return {'url': u_url or url, 'token': u_token or token}


def save_user_config(url, token):
    url, token = url.strip(), token.strip()
    if (url, token) == _config_file(EXT_CONFIG):
        if os.path.exists(USER_CONFIG):
            os.remove(USER_CONFIG)
        return
    _write_json(USER_CONFIG, {'url': url, 'token': token})


def is_configured():
    cfg = load_config()
    return bool(cfg['url'] and cfg['token'])


# Запросы, идущие сейчас (в т.ч. из фоновых потоков окон): при закрытии окна их обрывают,
# чтобы фоновый поток не пережил окно.
_active = []
_lock = threading.Lock()
_cancelled = [False]


def begin_requests():
    _cancelled[0] = False


def abort_requests():
    """Оборвать все идущие запросы (окно закрыто); следующие до begin_requests() не начнутся."""
    _cancelled[0] = True
    with _lock:
        reqs = list(_active)
    for req in reqs:
        try:
            req.Abort()
        except Exception:
            pass


def _post(url, body, timeout_ms):
    try:
        ServicePointManager.SecurityProtocol = ServicePointManager.SecurityProtocol | SecurityProtocolType.Tls12
        # Без этого .NET шлёт «Expect: 100-continue» и ждёт лишний обмен с сервером (часть прокси его рвёт)
        ServicePointManager.Expect100Continue = False
    except Exception:
        pass
    data = Encoding.UTF8.GetBytes(body)
    req = HttpWebRequest.Create(url)
    req.Method = 'POST'
    req.ContentType = 'text/plain; charset=utf-8'
    req.Timeout = timeout_ms
    req.ReadWriteTimeout = timeout_ms
    req.AllowAutoRedirect = True  # Apps Script отвечает редиректом на googleusercontent.com
    if req.Proxy is not None:
        req.Proxy.Credentials = CredentialCache.DefaultNetworkCredentials
    req.ContentLength = data.Length
    with _lock:
        _active.append(req)
    try:
        stream = req.GetRequestStream()
        try:
            stream.Write(data, 0, data.Length)
        finally:
            stream.Close()
        resp = req.GetResponse()
        try:
            return StreamReader(resp.GetResponseStream(), Encoding.UTF8).ReadToEnd()
        finally:
            resp.Close()
    finally:
        with _lock:
            if req in _active:
                _active.remove(req)


_TRANSIENT = (WebExceptionStatus.ConnectionClosed, WebExceptionStatus.KeepAliveFailure,
              WebExceptionStatus.ReceiveFailure, WebExceptionStatus.SendFailure,
              WebExceptionStatus.ConnectFailure, WebExceptionStatus.NameResolutionFailure,
              WebExceptionStatus.PipelineFailure, WebExceptionStatus.SecureChannelFailure)


def _is_transient(ex):
    """Сбой, который у Google случается сам по себе и проходит при повторе (обрыв, 5xx, 429).
    Таймаут и отмену не повторяем: это удвоило бы ожидание."""
    if _cancelled[0]:
        return False
    net = getattr(ex, 'clsException', None) or ex
    if isinstance(net, WebException):
        if net.Status == WebExceptionStatus.ProtocolError:
            try:
                code = int(net.Response.StatusCode)
            except Exception:
                return False
            return code >= 500 or code == 429
        return net.Status in _TRANSIENT
    return isinstance(net, IOException)


def call(action, payload=None, timeout_ms=15000, url=None, token=None, retries=1):
    """Запрос к веб-приложению. Временный сбой связи повторяется (retries раз): все действия
    сервера безопасно повторять — «add» отсеивает повторную отправку по id."""
    cfg = load_config()
    url = url or cfg['url']
    token = token or cfg['token']
    if not (url and token):
        raise ApiError(u'Не настроено подключение к таблице (кнопка «Настройка»).')
    body = dict(payload or {})
    body['action'] = action
    body['token'] = token
    text = _dumps(body)
    attempt = 0
    while True:
        if _cancelled[0]:
            raise ApiError(u'Запрос отменён: окно закрыто.')
        try:
            raw = _post(url, text, timeout_ms)
        except Exception as ex:
            if attempt < retries and _is_transient(ex):
                attempt += 1
                time.sleep(1)
                continue
            raise ApiError(u'Нет связи с Google Таблицей: ' + err_text(ex))
        try:
            resp = json.loads(raw)
        except Exception:
            # Google иногда отдаёт страницу ошибки вместо ответа скрипта — один раз повторяем
            if attempt < retries and not _cancelled[0]:
                attempt += 1
                time.sleep(1)
                continue
            raise ApiError(u'Таблица ответила не данными, а страницей. Проверьте адрес (должен заканчиваться на /exec) '
                           u'и что веб-приложение развернуто с доступом «Все».')
        break
    if not resp.get('ok'):
        raise ApiError(resp.get('error') or u'Неизвестная ошибка')
    return resp


# ---------------------------------------------------------------- настройки команды (лист «Настройки»)

def _merge_settings(data):
    s = dict(DEFAULT_SETTINGS)
    for k, v in (data or {}).items():
        s[k] = v
    for k in ('types', 'sections'):
        if not s.get(k):
            s[k] = list(DEFAULT_SETTINGS[k])
    return s


def get_settings(online=True, timeout_ms=10000):
    """Возвращает (настройки, получены_ли_с_сервера). Без связи — последняя сохранённая копия."""
    if online and is_configured():
        try:
            resp = call('settings', timeout_ms=timeout_ms)
            data = resp.get('settings') or {}
            data['sheet_url'] = resp.get('sheet_url') or u''
            _write_json(SETTINGS_CACHE, data)
            return _merge_settings(data), True
        except ApiError:
            pass
    return _merge_settings(_read_json(SETTINGS_CACHE, {})), False


def has_cached_settings():
    return os.path.exists(SETTINGS_CACHE)


def get_settings_fast():
    """Настройки без ожидания сети: сохранённая копия, а если её ещё нет (первый запуск) — с сервера.
    Копию обновляют окна в фоне (get_settings), так что правки листа «Настройки» доходят со следующего открытия."""
    if has_cached_settings():
        return get_settings(online=False)[0]
    return get_settings()[0]


def save_mapping(key_param, name_param, extra_params):
    call('saveSettings', {'settings': {
        'key_param': key_param, 'name_param': name_param, 'extra_params': extra_params}})
    data = _read_json(SETTINGS_CACHE, {}) or {}
    data.update({'key_param': key_param, 'name_param': name_param, 'extra_params': extra_params})
    _write_json(SETTINGS_CACHE, data)


# ---------------------------------------------------------------- сведения о проекте

def _bip_of(p):
    try:
        bip = p.Definition.BuiltInParameter
        if bip != BuiltInParameter.INVALID:
            return bip
    except Exception:
        pass
    return None


def _value(p):
    try:
        if p is None or not p.HasValue:
            return u''
        v = p.AsString() if p.StorageType == StorageType.String else p.AsValueString()
        return (v or u'').strip()
    except Exception:
        return u''


def param_ref(p):
    """«Номер проекта [PROJECT_NUMBER]» для встроенных, просто имя — для общих/проектных."""
    bip = _bip_of(p)
    name = p.Definition.Name
    return u'{} [{}]'.format(name, bip) if bip is not None else name


def ref_label(ref):
    if ref.endswith(u']') and u' [' in ref:
        return ref[:-1].rsplit(u' [', 1)[0]
    return ref


def list_project_params(doc):
    """Все осмысленные параметры «Сведений о проекте» с текущими значениями."""
    result = []
    for p in doc.ProjectInformation.Parameters:
        bip = _bip_of(p)
        if bip is not None:
            if p.StorageType != StorageType.String or str(bip).startswith(SKIP_BIP_PREFIXES):
                continue
            kind = u'Встроенный'
        else:
            kind = u'Общий' if p.IsShared else u'Параметр проекта'
        result.append({'ref': param_ref(p), 'name': p.Definition.Name, 'value': _value(p), 'kind': kind})
    result.sort(key=lambda r: (r['value'] == u'', r['kind'] != u'Встроенный', r['name']))
    return result


def read_param(doc, ref):
    if not ref or ref == FILE_KEY:
        return u''
    pi = doc.ProjectInformation
    name, bipname, p = ref, None, None
    if ref.endswith(u']') and u' [' in ref:
        name, bipname = ref[:-1].rsplit(u' [', 1)
    if bipname:
        try:
            p = pi.get_Parameter(getattr(BuiltInParameter, bipname))
        except Exception:
            p = None
    if p is None:
        p = pi.LookupParameter(name)
    return _value(p)


def model_path(doc):
    try:
        if doc.IsWorkshared:
            central = doc.GetWorksharingCentralModelPath()
            if central is not None:
                return ModelPathUtils.ConvertModelPathToUserVisiblePath(central)
    except Exception:
        pass
    return doc.PathName or doc.Title


def file_key(doc):
    base = model_path(doc).replace('\\', '/').rstrip('/').split('/')[-1]
    if base.lower().endswith('.rvt'):
        base = base[:-4]
    return base or doc.Title


def short_file(path):
    return (path or u'').replace('\\', '/').split('/')[-1]


def project_key(doc, settings):
    return read_param(doc, settings.get('key_param')) or file_key(doc)


def id_value(eid):
    v = getattr(eid, 'Value', None)  # Revit 2024+
    return v if v is not None else eid.IntegerValue


def to_element_id(n):
    try:
        return ElementId(System.Int64(n))
    except Exception:
        return ElementId(int(n))


def view_label(view):
    if view is None:
        return u''
    if isinstance(view, ViewSheet):
        return u'Лист {} - {}'.format(view.SheetNumber, view.Name)
    return view.Name


def find_view(doc, label):
    """Вид или лист по подписи из заметки (обратное к view_label); None — не найден."""
    label = (label or u'').strip()
    if not label:
        return None
    views = [v for v in FilteredElementCollector(doc).OfClass(View) if not v.IsTemplate]
    for v in views:
        try:
            if view_label(v) == label:
                return v
        except Exception:
            continue
    return None


def get_context(doc, uidoc, settings):
    key = read_param(doc, settings.get('key_param'))
    key_from_file = not key
    if not key:
        key = file_key(doc)
    extras = []
    for ref in settings.get('extra_params') or []:
        v = read_param(doc, ref)
        if v:
            extras.append(u'{}: {}'.format(ref_label(ref), v))
    view, selection = u'', []
    if uidoc is not None:
        try:
            view = view_label(uidoc.ActiveView)
        except Exception:
            pass
        try:
            selection = [id_value(i) for i in uidoc.Selection.GetElementIds()]
        except Exception:
            pass
    return {
        'key': key,
        'key_from_file': key_from_file,
        'name': read_param(doc, settings.get('name_param')) or file_key(doc),
        'info': u'; '.join(extras),
        'file': model_path(doc),
        'view': view,
        'selection': selection,
        'user': doc.Application.Username,
    }


# ---------------------------------------------------------------- заметки

def new_note(ctx, ntype, section, text, due, assignee, elements):
    return {
        'id': uuid.uuid4().hex[:16],
        'created': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'author': ctx['user'],
        'project_key': ctx['key'],
        'project_name': ctx['name'],
        'type': ntype,
        'section': section,
        'text': text,
        'due': due or u'',
        'assignee': assignee or u'',
        'status': STATUS_OPEN,
        'file': ctx['file'],
        'view': ctx['view'],
        'elements': u';'.join(u'{}'.format(i) for i in elements),
        'info': ctx['info'],
    }


def _load_queue():
    return _read_json(QUEUE_FILE, []) or []


def pending_notes(key):
    """Заметки, сохранённые без связи и ещё не ушедшие в таблицу."""
    result = []
    for n in _load_queue():
        if n.get('project_key') == key:
            n = dict(n)
            n['status'] = STATUS_PENDING
            result.append(n)
    return result


def flush_queue(timeout_ms=15000):
    """Отправляет очередь. Возвращает (отправлено, осталось)."""
    queue = _load_queue()
    if not queue:
        return 0, 0
    left, sent, failed = [], 0, False
    for note in queue:
        if not failed:
            try:
                call('add', {'note': note}, timeout_ms)
                sent += 1
                continue
            except ApiError:
                failed = True
        left.append(note)
    _write_json(QUEUE_FILE, left)
    return sent, len(left)


def queue_note(note):
    """Кладёт заметку в локальную очередь (ничего не теряется); отправляет flush_queue."""
    queue = _load_queue()
    queue.append(note)
    _write_json(QUEUE_FILE, queue)


def add_note(note, timeout_ms=15000):
    """Сначала в очередь, затем отправка. True — дошла."""
    queue_note(note)
    sent, left = flush_queue(timeout_ms)
    return left == 0


def cached_notes(key):
    """(заметки из последней копии + неотправленные, время копии или '') — мгновенно, без сети."""
    entry = (_read_json(NOTES_CACHE, {}) or {}).get(key) or {}
    return (entry.get('notes') or []) + pending_notes(key), entry.get('time') or u''


def load_notes(key, timeout_ms=15000):
    """(заметки, есть_связь, текст_ошибки). Без связи — последняя копия + неотправленные."""
    error = None
    try:
        flush_queue(timeout_ms)
        notes = call('list', {'project_key': key}, timeout_ms).get('notes') or []
        cache = _read_json(NOTES_CACHE, {}) or {}
        cache[key] = {'time': datetime.datetime.now().strftime('%d.%m.%Y %H:%M'), 'notes': notes}
        try:
            _write_json(NOTES_CACHE, cache)
        except Exception:
            pass
        online = True
    except ApiError as ex:
        entry = (_read_json(NOTES_CACHE, {}) or {}).get(key) or {}
        notes = entry.get('notes') or []
        error = err_text(ex)
        if entry.get('time'):
            error += u'\nПоказана копия от ' + entry['time'] + u'.'
        online = False
    return notes + pending_notes(key), online, error


def set_status(ids, status, user):
    return call('setStatus', {'ids': ids, 'status': status, 'by': user})


def update_note(note, changes, user):
    """Правка полей заметки (тип, раздел, текст, срок, кому). Неотправленная — правится в очереди."""
    if note.get('status') == STATUS_PENDING:
        queue = _load_queue()
        for queued in queue:
            if queued.get('id') == note.get('id'):
                queued.update(changes)
        _write_json(QUEUE_FILE, queue)
        return {'ok': True}
    return call('update', {'id': note['id'], 'fields': changes, 'by': user})


def set_answer(note_id, answer, status, user):
    """Записывает «Решение»; status — None (не менять) или новый статус."""
    return call('answer', {'id': note_id, 'answer': answer, 'status': status, 'by': user})


def is_question(note):
    return (note.get('type') or u'').strip().lower().startswith(QUESTION_TYPE.lower())


def needs_answer(note):
    """Вопрос без ответа, который ещё не отменён."""
    return (is_question(note) and not (note.get('answer') or u'').strip()
            and note.get('status') != STATUS_CANCEL)


def is_closed(note):
    return note.get('status') in CLOSED


def due_date(note):
    try:
        return datetime.datetime.strptime(note.get('due', '')[:10], '%Y-%m-%d').date()
    except Exception:
        return None


def is_overdue(note, today=None):
    d = due_date(note)
    return d is not None and not is_closed(note) and d < (today or datetime.date.today())


def is_mine(note, user):
    user = (user or u'').lower()
    return bool(user) and user in ((note.get('assignee') or u'').lower(), (note.get('author') or u'').lower())


def reminders(notes, user, days):
    """Открытые заметки со сроком в ближайшие N дней (и просроченные) + назначенные мне."""
    limit = datetime.date.today() + datetime.timedelta(days=int(days or 0))
    me = (user or u'').lower()
    result = []
    for n in notes:
        if is_closed(n) or n.get('status') == STATUS_PENDING:
            continue
        d = due_date(n)
        if (d is not None and d <= limit) or (me and (n.get('assignee') or u'').lower() == me):
            result.append(n)
    return result
