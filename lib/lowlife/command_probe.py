# -*- coding: utf-8 -*-
"""
Разовый перехват идентификатора команды ленты — диагностика.

Нужен, чтобы узнать точный id кнопки «Экспорт» ModPlus: без него не
сделать хук ``hooks/command-after-exec[<id>].py``, а журналы Revit у
пользователя не пишутся.

Подписывается на ``Autodesk.Windows.ComponentManager.ItemExecuted`` — оно
срабатывает на клик по ЛЮБОЙ кнопке ленты, включая кнопки сторонних
плагинов, и даёт объект ``RibbonItem`` с его ``Id`` / ``Text`` / ``Cookie``.
Каждый пойманный элемент дописывается строкой в
``%APPDATA%\\pyRevit\\LowLifeExportRename_commands.log``; ``arm()`` перед
этим пишет строку-маркер, ``show_results()`` показывает всё, что поймано
после последнего маркера.

Событие ``ComponentManager.ItemExecuted`` статическое и живёт всё время
процесса Revit, поэтому подписка переживает перезапуск движка pyRevit
между нажатиями кнопки (в отличие от обычных python-глобалов). Ценой
возможной «висящей» подписки до перезапуска Revit — для разовой
диагностики приемлемо.
"""

import os
import io
import datetime

try:
    from pyrevit import forms
except Exception:
    forms = None

try:
    from lowlife import export_rename
except Exception:
    export_rename = None


LOG_NAME = "LowLifeExportRename_commands.log"
MARKER = u"=== armed "
# сколько строк писать после одного маркера, чтобы лог не пух
MAX_LINES_PER_SESSION = 60

_subscribed = False
_handler = None
_since_marker = 0


def _log_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(appdata, "pyRevit")
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except Exception:
            pass
    return os.path.join(folder, LOG_NAME)


def _component_manager():
    import clr
    clr.AddReference("AdWindows")
    from Autodesk.Windows import ComponentManager
    return ComponentManager


def _describe(item):
    parts = []
    for attr in (u"Text", u"Id", u"Cookie", u"UID", u"GroupName"):
        try:
            v = getattr(item, attr, None)
        except Exception:
            v = None
        if v:
            parts.append(u"{}={}".format(
                attr, unicode(v).replace(u"\n", u" ").replace(u"\r", u"")))
    try:
        parts.append(u"Type={}".format(type(item).__name__))
    except Exception:
        pass
    return u" | ".join(parts) or u"(пустой элемент)"


def _append(line):
    try:
        with io.open(_log_path(), "a", encoding="utf-8") as f:
            f.write(line + u"\n")
    except Exception:
        pass


def arm():
    """Обычный клик по кнопке: включить перехват."""
    global _subscribed, _handler, _since_marker

    if forms is None:
        return

    try:
        cm = _component_manager()
    except Exception:
        forms.alert(u"Не удалось подключить Autodesk.Windows (AdWindows) — "
                    u"перехват команд в этой сборке недоступен.")
        return

    _since_marker = 0
    _append(u"{}{}".format(
        MARKER, datetime.datetime.now().strftime(u"%Y-%m-%d %H:%M:%S")))

    if not _subscribed:
        def _on_item_executed(sender, e):
            global _since_marker
            if _since_marker >= MAX_LINES_PER_SESSION:
                return
            try:
                item = e.Item
            except Exception:
                item = None
            if item is None:
                return
            _since_marker += 1
            _append(u"  {}  {}".format(
                datetime.datetime.now().strftime(u"%H:%M:%S"), _describe(item)))

        try:
            cm.ItemExecuted += _on_item_executed
        except Exception:
            forms.alert(u"Не удалось подписаться на ComponentManager.ItemExecuted.")
            return
        _handler = _on_item_executed
        _subscribed = True

    forms.alert(
        u"Перехват включён.\n\n"
        u"1. Нажми кнопку «Экспорт» в ModPlus (сам экспорт запускать не "
        u"обязательно — достаточно клика по кнопке ленты).\n"
        u"2. Вернись сюда и нажми эту кнопку с Shift — покажу, что поймал.\n\n"
        u"Лог: {}".format(_log_path()))


def _watcher_diag():
    """Сводка авто-режима переименования (export_watcher) + хвост его лога —
    чтобы понять, почему «не работает»."""
    out = []
    ew = None
    try:
        from lowlife import export_watcher as ew
    except Exception as exc:
        out.append(u"export_watcher НЕ ИМПОРТИРУЕТСЯ: {}".format(exc))

    if ew is not None:
        try:
            out.append(ew.status_text())
        except Exception as exc:
            out.append(u"export_watcher.status_text() упал: {}".format(exc))

    try:
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        p = os.path.join(appdata, "pyRevit", "LowLifeExportRename_watcher.log")
        with io.open(p, "r", encoding="utf-8") as f:
            wl = f.read().splitlines()
        out.append(u"\n--- watcher.log (последние 45 строк) ---")
        out.extend(wl[-45:] if wl else
                   [u"(лог ПУСТ — install() не отработал: ни startup.py, ни "
                    u"hooks/doc-opened.py не дописали)"])
    except Exception:
        out.append(u"\n--- watcher.log нет / не прочитать ---")
    return u"\n".join(out)


def show_results():
    """Shift+клик: пойманные команды + диагностика авто-режима."""
    if forms is None:
        return

    path = _log_path()
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except Exception:
        lines = []

    tail = []
    for ln in reversed(lines):
        if ln.startswith(MARKER):
            break
        tail.append(ln)
    tail.reverse()
    tail = [ln for ln in tail if ln.strip()]

    if not tail:
        forms.alert(
            u"Перехват команд: после последнего включения ничего не поймано "
            u"(обычный клик по кнопке → «Экспорт» в ModPlus → Shift+клик).\n\n"
            u"{}".format(_watcher_diag()))
        return

    best = None
    for ln in tail:
        low = ln.lower()
        if u"modplus" in low and (u"export" in low or u"экспорт" in low):
            best = ln
            break
    if best is None:  # запаснее: любая строка ModPlus
        for ln in tail:
            if u"modplus" in ln.lower():
                best = ln
                break

    msg = u"Поймано после последнего включения:\n\n{}\n\nПолный лог:\n{}".format(
        u"\n".join(tail), path)

    if best:
        cid = u""
        for part in best.split(u" | "):
            if part.strip().startswith(u"Id="):
                cid = part.split(u"=", 1)[1].strip()
        msg += u"\n\nПохоже на ModPlus «Экспорт»:\n{}".format(best)
        if cid:
            msg += u"\n\nId для хука: {}".format(cid)
            if export_rename is not None:
                try:
                    export_rename.save_config({"last_seen_command": cid})
                except Exception:
                    pass
        else:
            msg += u"\n\n(строки Id нет — пришли мне эту строку целиком)"

    msg += u"\n\n" + _watcher_diag()
    forms.alert(msg)
