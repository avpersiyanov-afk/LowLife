# -*- coding: utf-8 -*-
"""Статистика запусков кнопок LowLife: кто, какую кнопку и когда нажал — в таблицу автора.

Таблица и веб-приложение — те же, что у «Обратной связи» (`docs/feedback/Code.gs`, действие
`usage`, лист «Запуски»). Клики ловит подписка на `Autodesk.Windows.ComponentManager.ItemExecuted`,
которую ставит `hooks/app-init.py` (`install`); кнопка «Поиск» запускает кнопки через
`PostCommand` и записывает запуск сама (`record_entry`). Обработчик клика только дописывает запуск
в локальную очередь — сеть не трогает; накопленное (`usage_core.should_flush`) уходит пачками
в фоновом потоке. Пользователь выключает отправку галочкой в окне «Обратная связь» (`set_enabled`).
"""
import os
import time
import json

import System

from pnotes import core, feedback
from lowlife import about, ribbon_catalog, usage_core

try:
    unicode
except NameError:
    unicode = str

USER_DIR = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'pyRevit', 'LowLifeUsage')
CONFIG_FILE = os.path.join(USER_DIR, 'config.json')
QUEUE_FILE = os.path.join(USER_DIR, 'queue.json')

QUEUE_LOCK = 'lowlife_usage_queue_lock'
SENDING_FLAG = 'lowlife_usage_sending'
HANDLER_KEY = 'LowLife_UsageStats_Handler'      # подписка одна на процесс Revit, а не на движок
SEARCH_MARK_KEY = 'LowLife_UsageStats_SearchMark'

_cache = {}  # каталог кнопок и версии — один раз на движок


def is_enabled():
    return (core._read_json(CONFIG_FILE, {}) or {}).get('enabled', True) is not False


def set_enabled(value):
    config = core._read_json(CONFIG_FILE, {}) or {}
    config['enabled'] = bool(value)
    core._write_json(CONFIG_FILE, config)
    if not value:  # выключили — и накопленное не отправляем
        with core._QueueLock(QUEUE_LOCK):
            core._write_json(QUEUE_FILE, [])


# ---------------------------------------------------------------- запись

def _entries():
    if 'entries' not in _cache:
        _cache['entries'] = ribbon_catalog.list_buttons()
    return _cache['entries']


def _context(uiapp):
    if 'static' not in _cache:
        ctx = {'user': u'', 'windows_user': os.environ.get('USERNAME') or u'',
               'version': about.version_text(), 'revit': u''}
        try:
            app = uiapp.Application
            ctx['user'] = app.Username or u''
            ctx['revit'] = u'{} ({})'.format(app.VersionName, app.VersionBuild)
        except Exception:
            pass
        _cache['static'] = ctx
    ctx = dict(_cache['static'])
    ctx['model'] = u''
    try:
        uidoc = uiapp.ActiveUIDocument
        if uidoc is not None:
            ctx['model'] = core.short_file(uidoc.Document.PathName) or uidoc.Document.Title
    except Exception:
        pass
    return ctx


def _append(event):
    with core._QueueLock(QUEUE_LOCK):
        queue = core._read_json(QUEUE_FILE, []) or []
        queue.append(event)
        queue = usage_core.trim_queue(queue)
        core._write_json(QUEUE_FILE, queue)
    return queue


def _record(uiapp, entry, source):
    if not is_enabled():
        return
    queue = _append(usage_core.new_event(entry, source, _context(uiapp)))
    if usage_core.should_flush(queue):
        send_detached()


def record_entry(uiapp, entry):
    """Запуск из «Поиска» (entry — из ribbon_catalog.list_buttons()). Никогда не падает."""
    try:
        event_entry = usage_core.find_entry(_entries(), entry[u'panel_title'], entry[u'path']) or entry
        System.AppDomain.CurrentDomain.SetData(
            SEARCH_MARK_KEY, u'{}|{}'.format(u'/'.join([entry[u'panel']] + list(entry[u'path'])), time.time()))
        _record(uiapp, event_entry, usage_core.SOURCE_SEARCH)
    except Exception:
        pass


def _search_mark():
    try:
        raw = System.AppDomain.CurrentDomain.GetData(SEARCH_MARK_KEY)
        button_id, seconds = unicode(raw).rsplit(u'|', 1)
        return button_id, float(seconds)
    except Exception:
        return None


def _on_click(uiapp, item_id):
    parsed = usage_core.parse_item_id(item_id)
    if not parsed:
        return
    entry = usage_core.find_entry(_entries(), parsed[0], parsed[1])
    if entry is None:  # не кнопка (список «Тема») или кнопки нет в каталоге
        return
    button_id = u'/'.join([entry[u'panel']] + list(entry[u'path']))
    if usage_core.is_duplicate(_search_mark(), button_id, time.time()):
        return
    _record(uiapp, entry, usage_core.SOURCE_RIBBON)


def install(uiapp):
    """Подписка на клики по ленте (из hooks/app-init.py) и отправка накопленного с прошлых сеансов.
    После перезагрузки pyRevit старая подписка заменяется новой — со свежим кодом."""
    import clr
    clr.AddReference('AdWindows')
    from Autodesk.Windows import ComponentManager

    def handler(sender, e):
        try:
            item = e.Item
            if item is not None:
                _on_click(uiapp, unicode(item.Id or u''))
        except:  # noqa: E722 — исключение из обработчика ленты не должно доходить до Revit
            pass

    domain = System.AppDomain.CurrentDomain
    old = domain.GetData(HANDLER_KEY)
    if old is not None:
        try:
            ComponentManager.ItemExecuted -= old
        except Exception:
            pass
        domain.SetData(HANDLER_KEY, None)
    # подписка стоит и при выключенной статистике: _record проверяет галочку на каждом клике,
    # так что включение в окне «Обратная связь» действует сразу, без перезапуска Revit
    try:
        from System import EventHandler
        from Autodesk.Windows import RibbonItemExecutedEventArgs
        delegate = EventHandler[RibbonItemExecutedEventArgs](handler)
    except Exception:
        delegate = handler  # IronPython сам обернёт функцию в делегат
    ComponentManager.ItemExecuted += delegate
    domain.SetData(HANDLER_KEY, delegate)
    if is_enabled() and core._read_json(QUEUE_FILE, []):
        send_detached()


# ---------------------------------------------------------------- отправка

def _send(events, timeout_ms=20000):
    url = feedback.feedback_url()
    if not url:
        raise core.ApiError(u'Адрес таблицы не задан.')
    body = core._dumps({'action': 'usage', 'usage': {'batch': usage_core.batch_id(events), 'events': events}})
    try:
        raw = core._post(url, body, timeout_ms, track=False)
    except Exception as ex:
        if not core._is_transient(ex, timeout=True):
            raise core.ApiError(core.err_text(ex))
        raw = core._post(url, body, timeout_ms, track=False)  # разовый сбой Google — один повтор
    try:
        resp = json.loads(raw)
    except Exception:
        raise core.ApiError(u'Таблица ответила не данными, а страницей.')
    if not resp.get('ok'):
        raise core.ApiError(resp.get('error') or u'Неизвестная ошибка')


def flush_queue(timeout_ms=20000):
    """Отправляет очередь пачками. Возвращает (отправлено, осталось); из файла убираются только
    отправленные запуски — записанные во время отправки остаются."""
    queue = core._read_json(QUEUE_FILE, []) or []
    if not queue or not is_enabled():
        return 0, 0
    sent = set()
    for start in range(0, len(queue), usage_core.BATCH_SIZE):
        events = queue[start:start + usage_core.BATCH_SIZE]
        try:
            _send(events, timeout_ms)
        except Exception:
            break  # нет связи — остальное уйдёт в следующий раз
        sent.update(e.get('id') for e in events)
    with core._QueueLock(QUEUE_LOCK):
        left = [e for e in (core._read_json(QUEUE_FILE, []) or []) if e.get('id') not in sent]
        if sent:
            core._write_json(QUEUE_FILE, left)
    return len(sent), len(left)


def send_detached():
    if feedback.feedback_url():
        core.run_detached(SENDING_FLAG, flush_queue)
