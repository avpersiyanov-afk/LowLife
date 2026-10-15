# -*- coding: utf-8 -*-
"""Статистика запусков кнопок LowLife — чистая логика без Revit API (тесты: tests/test_usage_core.py).

Revit-часть (подписка на клики по ленте, очередь, отправка) — `pnotes/usage.py`.
Кнопка на ленте имеет Id вида `CustomCtrl_%CustomCtrl_%LowLife%<подпись панели>%<папка кнопки>`
(у кнопки в выпадающем списке между ними ещё папка списка).
"""
import uuid
import datetime

try:
    unicode
except NameError:
    unicode = str

TAB_NAME = u"LowLife"
SOURCE_RIBBON = u"Лента"
SOURCE_SEARCH = u"Поиск"

# Когда отправлять накопленное: столько запусков или первый из них старше стольких минут
FLUSH_COUNT = 20
FLUSH_AGE_MIN = 30
BATCH_SIZE = 200          # запусков в одном запросе к таблице
MAX_QUEUE = 5000          # без связи неделями очередь не растёт бесконечно — старые отбрасываются
DUPLICATE_SECONDS = 10    # «Поиск» записал запуск сам — тот же клик от ленты в эти секунды не считаем
TIME_FORMAT = u"%Y-%m-%d %H:%M:%S"


def parse_item_id(item_id, tab=TAB_NAME):
    """(подпись панели, [папки от панели до кнопки]) из Id элемента ленты или None, если не LowLife."""
    parts = [p for p in unicode(item_id or u"").split(u"%") if p]
    for i, part in enumerate(parts):
        if part == tab and not part.startswith(u"CustomCtrl_"):
            rest = parts[i + 1:]
            if len(rest) >= 2:
                return rest[0], rest[1:]
            return None
    return None


def find_entry(entries, panel_title, path):
    """Кнопка из ribbon_catalog.list_buttons() по подписи панели и пути папок; None — не нашлась
    (не кнопка, а например список «Тема»)."""
    if not path:
        return None
    candidates = [e for e in entries if e[u"panel_title"] == panel_title or e[u"panel"] == panel_title]
    for e in candidates:
        if e[u"path"] == list(path):
            return e
    for e in candidates:
        if e[u"button"] == path[-1]:
            return e
    return None


def new_event(entry, source, ctx, now=None):
    now = now or datetime.datetime.now()
    return {
        u"id": uuid.uuid4().hex[:12],
        u"time": now.strftime(TIME_FORMAT),
        u"user": ctx.get(u"user") or u"",
        u"windows_user": ctx.get(u"windows_user") or u"",
        u"panel": entry[u"panel_title"],
        u"button": entry[u"title"],
        u"button_id": u"/".join([entry[u"panel"]] + list(entry[u"path"])),
        u"source": source,
        u"model": ctx.get(u"model") or u"",
        u"version": ctx.get(u"version") or u"",
        u"revit": ctx.get(u"revit") or u"",
    }


def _parse_time(text):
    try:
        return datetime.datetime.strptime(text, TIME_FORMAT)
    except (TypeError, ValueError):
        return None


def should_flush(queue, now=None, count=FLUSH_COUNT, age_min=FLUSH_AGE_MIN):
    if not queue:
        return False
    if len(queue) >= count:
        return True
    first = _parse_time(queue[0].get(u"time"))
    now = now or datetime.datetime.now()
    return first is None or (now - first).total_seconds() >= age_min * 60


def batch_id(events):
    """Одна и та же пачка при повторной отправке получает тот же id — таблица не запишет её дважды."""
    return u"{}-{}-{}".format(events[0].get(u"id"), events[-1].get(u"id"), len(events)) if events else u""


def trim_queue(queue, limit=MAX_QUEUE):
    return queue[-limit:] if len(queue) > limit else queue


def is_duplicate(last_mark, button_id, now_seconds, seconds=DUPLICATE_SECONDS):
    """last_mark — (button_id, время в секундах) последнего запуска, записанного «Поиском»."""
    if not last_mark:
        return False
    mark_id, mark_time = last_mark
    return mark_id == button_id and 0 <= now_seconds - mark_time <= seconds
