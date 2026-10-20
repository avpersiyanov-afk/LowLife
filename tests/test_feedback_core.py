# -*- coding: utf-8 -*-
import datetime

from lowlife import feedback_core as fc


def _item(i, text=u"текст"):
    return {u"id": u"id%d" % i, u"created": u"2026-10-20 10:00", u"panel": u"СКС", u"button": u"",
            u"kind": u"Проблема", u"text": text, u"user": u"ivanov", u"model": u"A.rvt"}


def test_add_to_history_keeps_only_message_fields_and_limit():
    history = []
    for i in range(fc.HISTORY_MAX + 5):
        history = fc.add_to_history(history, _item(i))
    assert len(history) == fc.HISTORY_MAX
    assert history[0][u"id"] == u"id5" and history[-1][u"id"] == u"id%d" % (fc.HISTORY_MAX + 4)
    assert u"user" not in history[-1] and u"model" not in history[-1]
    assert history[-1][u"reply"] == u""


def test_add_to_history_replaces_same_id():
    history = fc.add_to_history([], _item(1, u"старый"))
    history = fc.add_to_history(history, _item(1, u"новый"))
    assert [h[u"text"] for h in history] == [u"новый"]


def test_merge_replies_counts_new_and_changed_answers():
    history = fc.add_to_history(fc.add_to_history([], _item(1)), _item(2))
    history, changed = fc.merge_replies(history, [
        {u"id": u"id1", u"status": u"В работе", u"reply": u"", u"replied": u""},
        {u"id": u"id2", u"status": u"Сделано", u"reply": u"Исправлено", u"replied": u"20.10.2026 12:00"},
        {u"id": u"чужой", u"status": u"Новое", u"reply": u"не наш"},
    ])
    assert changed == 1
    assert history[0][u"status"] == u"В работе" and history[0][u"delivered"]
    assert history[1][u"reply"] == u"Исправлено" and history[1][u"replied"] == u"20.10.2026 12:00"
    assert [h[u"id"] for h in fc.unread(history)] == [u"id2"]

    history, changed = fc.merge_replies(history, [{u"id": u"id2", u"status": u"Сделано", u"reply": u"Исправлено"}])
    assert changed == 0
    history, changed = fc.merge_replies(history, [{u"id": u"id2", u"reply": u"Исправлено, обновите LowLife"}])
    assert changed == 1


def test_mark_seen_and_unread_after_reply_changes():
    history, _ = fc.merge_replies(fc.add_to_history([], _item(1)), [{u"id": u"id1", u"reply": u"Да"}])
    history = fc.mark_seen(history)
    assert fc.unread(history) == []
    history, _ = fc.merge_replies(history, [{u"id": u"id1", u"reply": u"Да, готово"}])
    assert len(fc.unread(history)) == 1


def test_unsent_message_is_not_delivered():
    history, _ = fc.merge_replies(fc.add_to_history([], _item(1)), [])
    assert not history[0].get(u"delivered")
    assert fc.ids_to_check(history) == [u"id1"]


def test_check_due():
    now = datetime.datetime(2026, 10, 20, 12, 0)
    assert fc.check_due(u"", now)
    assert fc.check_due(u"мусор", now)
    assert not fc.check_due(u"2026-10-20 11:00", now)
    assert fc.check_due(u"2026-10-20 08:59", now)
    assert fc.check_due(u"2026-10-21 08:00", now)  # часы на компьютере переводили назад


def test_where_and_notice():
    assert fc.where_text({u"panel": u"СКС", u"button": u"Узлы трассы"}) == u"СКС → Узлы трассы"
    assert fc.where_text({u"panel": u"", u"button": u""}) == u"LowLife в целом"
    assert u"(3)" in fc.unread_notice(3)
    assert u"ответил на ваше сообщение" in fc.unread_notice(1)
