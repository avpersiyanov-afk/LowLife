# -*- coding: utf-8 -*-
"""Ответы автора на «Обратную связь» — чистая логика без Revit API (тесты: tests/test_feedback_core.py).

Каждое отправленное сообщение остаётся у пользователя в истории (`pnotes/feedback.py`, файл
`sent.json`). Автор пишет ответ в столбец «Ответ пользователю» своей таблицы; LowLife в фоне
спрашивает веб-приложение (действие `replies`) статус и ответ по ID своих сообщений — ID случайный
и известен только отправителю и автору, поэтому чужие ответы так не прочитать.
"""
import datetime
from lowlife.i18n import N_, tr

try:
    unicode
except NameError:
    unicode = str

HISTORY_MAX = 100        # столько последних сообщений помним и проверяем
CHECK_HOURS = 3          # фоновая проверка ответов не чаще
TIME_FORMAT = u"%Y-%m-%d %H:%M"

# поля сообщения, которые остаются в истории
_KEPT = (u"id", u"created", u"panel", u"button", u"kind", u"text")


def add_to_history(history, item):
    """Новая история: сообщение item (из feedback.new_item) в конце, не больше HISTORY_MAX."""
    entry = dict((k, item.get(k) or u"") for k in _KEPT)
    entry.update({u"status": u"", u"reply": u"", u"replied": u"", u"reply_seen": u""})
    out = [h for h in (history or []) if h.get(u"id") != entry[u"id"]] + [entry]
    return out[-HISTORY_MAX:]


def ids_to_check(history):
    return [h[u"id"] for h in (history or []) if h.get(u"id")]


def merge_replies(history, replies):
    """Вписывает в историю статусы и ответы от веб-приложения ([{id, status, reply, replied}]).
    Возвращает (новая история, сколько ответов появилось или изменилось)."""
    by_id = dict((unicode(r.get(u"id") or u""), r) for r in (replies or []) if r.get(u"id"))
    out, changed = [], 0
    for h in history or []:
        h = dict(h)
        r = by_id.get(h.get(u"id"))
        if r is not None:
            reply = unicode(r.get(u"reply") or u"").strip()
            if reply and reply != (h.get(u"reply") or u""):
                changed += 1
            h[u"reply"] = reply
            h[u"status"] = unicode(r.get(u"status") or u"").strip()
            h[u"replied"] = unicode(r.get(u"replied") or u"").strip()
            h[u"delivered"] = True
        out.append(h)
    return out, changed


def is_unread(entry):
    reply = entry.get(u"reply") or u""
    return bool(reply) and reply != (entry.get(u"reply_seen") or u"")


def unread(history):
    return [h for h in (history or []) if is_unread(h)]


def mark_seen(history):
    out = []
    for h in history or []:
        h = dict(h)
        h[u"reply_seen"] = h.get(u"reply") or u""
        out.append(h)
    return out


def check_due(last_checked, now=None, hours=CHECK_HOURS):
    """Пора ли снова спрашивать таблицу: last_checked — строка TIME_FORMAT или пусто."""
    now = now or datetime.datetime.now()
    try:
        last = datetime.datetime.strptime(last_checked or u"", TIME_FORMAT)
    except (ValueError, TypeError):
        return True
    return last > now or now - last >= datetime.timedelta(hours=hours)


def where_text(entry, general=None):
    return (u" → ".join(p for p in (entry.get(u"panel"), entry.get(u"button")) if p)
            or (tr(u"LowLife в целом") if general is None else general))


# Stored statuses remain the service's original values; only display labels change.
FEEDBACK_STATUSES = (N_(u'Новое'), N_(u'В работе'), N_(u'Сделано'), N_(u'Не будет'), N_(u'Дубль'))


def status_label(value):
    return tr(value) if value in FEEDBACK_STATUSES else value


def unread_notice(count):
    if count == 1:
        return tr(u"Автор LowLife ответил на ваше сообщение. Ответ — в «Обратной связи», вкладка «Мои сообщения».")
    return (tr(u"Автор LowLife ответил на ваши сообщения ({}). Ответы — в «Обратной связи», "
            u"вкладка «Мои сообщения».").format(count))
