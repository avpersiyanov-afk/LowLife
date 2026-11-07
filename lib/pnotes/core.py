# -*- coding: utf-8 -*-
"""Заметки по проекту: настройки, связь с Google Таблицей, сведения из модели."""
import os
from lowlife.i18n import tr, N_
from pnotes.localization import server_error
import io
import json
import uuid
import datetime

import clr
clr.AddReference('System')
import System
from System.Threading import Thread, ThreadStart

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

STATUS_OPEN = N_(u'Открыто')
STATUS_WORK = N_(u'В работе')
STATUS_DONE = N_(u'Выполнено')
STATUS_CANCEL = N_(u'Отменено')
STATUS_PENDING = N_(u'Не отправлено')
CLOSED = (STATUS_DONE, STATUS_CANCEL)
# Тип «Вопрос» нельзя закрыть как «Выполнено» без «Решения» (то же правило в Code.gs)
QUESTION_TYPE = u'Вопрос'

# Значение параметра «код проекта», означающее «брать имя файла модели»
FILE_KEY = N_(u'(имя файла модели)')

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


from lowlife.cloud_io import ApiError, err_text, dumps_ascii, Transport, AppDomainLock


# ---------------------------------------------------------------- файлы

def _read_json(path, default=None):
    try:
        with io.open(path, 'r', encoding='utf-8-sig') as f:
            return json.loads(f.read())
    except Exception:
        return default


_dumps=dumps_ascii


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
TRANSPORT=Transport()
_active=TRANSPORT._active
_lock=TRANSPORT._lock
_cancelled=TRANSPORT._cancelled
begin_requests=TRANSPORT.begin_requests
abort_requests=TRANSPORT.abort_requests
_post=TRANSPORT._post
_is_transient=TRANSPORT._is_transient
last_server_ms=TRANSPORT.last_server_ms


def call(action, payload=None, timeout_ms=15000, url=None, token=None, retries=1, track=True,
         retry_timeout=False):
    cfg=load_config()
    return TRANSPORT.call(action,payload,timeout_ms,url or cfg['url'],token or cfg['token'],
                          retries,track,retry_timeout,error_transform=server_error)


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
            kind = N_(u'Встроенный')
        else:
            kind = N_(u'Общий') if p.IsShared else N_(u'Параметр проекта')
        result.append({'ref': param_ref(p), 'name': p.Definition.Name, 'value': _value(p), 'kind': kind})
    result.sort(key=lambda r: (r['value'] == u'', r['kind'] != u'Встроенный', r['name']))
    return result


def read_param(doc,ref):
    if not ref or ref==FILE_KEY:
        return u''
    from lowlife.params import read_project_parameter
    return read_project_parameter(doc,ref)


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


def _QueueLock(key='pnotes_queue_lock'):
    return AppDomainLock(key)


def queue_size():
    return len(_load_queue())


def flush_queue(timeout_ms=15000, track=True, retry_timeout=False):
    """Отправляет очередь. Возвращает (отправлено, осталось).
    Из файла убираются только отправленные заметки: то, что добавили во время отправки, не теряется."""
    queue = _load_queue()
    if not queue:
        return 0, 0
    sent = set()
    for note in queue:
        try:
            call('add', {'note': note}, timeout_ms, track=track, retry_timeout=retry_timeout)
            sent.add(note.get('id'))
        except ApiError:
            break  # нет связи — остальные не пробуем, уйдут в следующий раз
    with _QueueLock():
        left = [n for n in _load_queue() if n.get('id') not in sent]
        if sent:
            _write_json(QUEUE_FILE, left)
    return len(sent), len(left)


def queue_note(note):
    """Кладёт заметку в локальную очередь (ничего не теряется); отправляет flush_queue."""
    with _QueueLock():
        queue = _load_queue()
        queue.append(note)
        _write_json(QUEUE_FILE, queue)


def run_detached(flag, flush):
    """flush() -> (отправлено, осталось) — в фоновом потоке, который живёт дольше скрипта кнопки
    (у такой кнопки постоянный движок pyRevit: engine: persistent в bundle.yaml). Пока очередь
    убывает, отправка повторяется. flag — имя флага в AppDomain: если отправка уже идёт, вторая
    не запускается (идущая перечитывает очередь и заберёт новое)."""
    domain = System.AppDomain.CurrentDomain
    if domain.GetData(flag):
        return
    domain.SetData(flag, True)

    def body():
        try:
            while True:
                sent, left = flush()
                if not left or not sent:
                    break
        except:  # noqa: E722 — исключение из фонового потока уронило бы Revit
            pass
        finally:
            try:
                domain.SetData(flag, None)
            except:  # noqa: E722
                pass

    thread = Thread(ThreadStart(body))
    thread.IsBackground = True
    try:
        thread.Start()
    except Exception:
        domain.SetData(flag, None)


def send_queue_detached(timeout_ms=30000):
    """Отправить очередь заметок в фоне, не дожидаясь ответа: окно уже закрыто, Revit свободен.
    Не отправилось — заметка остаётся в очереди и уйдёт со следующей заметкой или при открытии
    сводки (там она видна как «Не отправлено»)."""
    run_detached('pnotes_sending', lambda: flush_queue(timeout_ms, track=False, retry_timeout=True))


def add_note(note, timeout_ms=15000):
    """Сначала в очередь, затем отправка. True — дошла."""
    queue_note(note)
    sent, left = flush_queue(timeout_ms)
    return left == 0


def cached_notes(key):
    """(заметки из последней копии + неотправленные, время копии или '') — мгновенно, без сети."""
    entry = (_read_json(NOTES_CACHE, {}) or {}).get(key) or {}
    return (entry.get('notes') or []) + pending_notes(key), entry.get('time') or u''


def load_notes(key, timeout_ms=15000, retry_timeout=False):
    """(заметки, есть_связь, текст_ошибки). Без связи — последняя копия + неотправленные.
    retry_timeout=True — для фоновой загрузки: «зависший» запрос повторяется один раз."""
    error = None
    try:
        flush_queue(timeout_ms, retry_timeout=retry_timeout)
        notes = call('list', {'project_key': key}, timeout_ms,
                     retry_timeout=retry_timeout).get('notes') or []
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
            error += tr(u'\nПоказана копия от ') + entry['time'] + u'.'
        online = False
    return notes + pending_notes(key), online, error


def set_status(ids, status, user):
    return call('setStatus', {'ids': ids, 'status': status, 'by': user}, 20000, retry_timeout=True)


def update_note(note, changes, user):
    """Правка полей заметки (тип, раздел, текст, срок, кому). Неотправленная — правится в очереди."""
    if note.get('status') == STATUS_PENDING:
        with _QueueLock():
            queue = _load_queue()
            for queued in queue:
                if queued.get('id') == note.get('id'):
                    queued.update(changes)
            _write_json(QUEUE_FILE, queue)
        return {'ok': True}
    return call('update', {'id': note['id'], 'fields': changes, 'by': user}, 20000, retry_timeout=True)


def set_answer(note_id, answer, status, user):
    """Записывает «Решение»; status — None (не менять) или новый статус."""
    return call('answer', {'id': note_id, 'answer': answer, 'status': status, 'by': user}, 20000,
                retry_timeout=True)


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
