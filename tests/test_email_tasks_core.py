# -*- coding: utf-8 -*-
"""Тесты для lowlife.email_tasks_core — чистая логика кнопки «Задачи из
почты»: обрезка истории переписки, пачки писем, устойчивый разбор ответа
модели, нормализация и сортировка задач, тестовые письма."""

import datetime
import os

import pytest

from lowlife import email_tasks_core as core

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_EMAILS = os.path.join(ROOT, "LowLife.tab", "Mail.panel", "EmailTasks.pushbutton", "test_emails.json")


@pytest.mark.parametrize("body,expected", [
    (u"Сделай отчёт.\n\nОт: Иванов\nОтправлено: вчера\n> старое", u"Сделай отчёт."),
    (u"Ok\r\n-----Original Message-----\r\nFrom: x", u"Ok"),
    (u"Ok\n-----Исходное сообщение-----\nстарое", u"Ok"),
    (u"Пришли схему.\n\nПн, 29 сент. 2026 г. в 14:02, Иван Иванов пишет:\n> старое", u"Пришли схему."),
    (u"Текст\nFrom: someone@example.com\nSent: ...", u"Текст"),
])
def test_trim_body_cuts_history(body, expected):
    assert core.trim_body(body) == expected


def test_trim_body_keeps_marker_on_first_line():
    # Пересланное письмо целиком: маркер в первой строке — не режем до пустоты
    body = u"From: Иванов\nПрошу проверить спецификацию."
    assert core.trim_body(body) == body


def test_trim_body_limits_length_and_collapses_blank_lines():
    assert core.trim_body(u"a\n\n\n\nb") == u"a\n\nb"
    trimmed = core.trim_body(u"x" * 9000)
    assert trimmed.startswith(u"x" * 4000)
    assert len(trimmed) < 4100


def _email(i, body_len=100):
    return {"id": i, "received": datetime.datetime(2026, 10, 1, 9, 0), "sender": u"s",
            "to": u"t", "cc": u"", "subject": u"тема", "body": u"я" * body_len}


def test_make_batches_respects_limit_and_order():
    emails = [_email(i, 4000) for i in range(1, 21)]
    batches = core.make_batches(emails, batch_chars=30000)
    assert len(batches) > 1
    assert [e["id"] for b in batches for e in b] == list(range(1, 21))
    for batch in batches:
        assert sum(len(core.format_email(e)) for e in batch) <= 30000


def test_make_batches_oversized_email_goes_alone():
    batches = core.make_batches([_email(1, 50), _email(2, 50000), _email(3, 50)], batch_chars=30000)
    assert [[e["id"] for e in b] for b in batches] == [[1], [2], [3]]


def test_build_request_contains_today_and_ids():
    text = core.build_request(u"ПРОМПТ", [_email(7)], datetime.date(2026, 10, 1))
    assert text.startswith(u"ПРОМПТ")
    assert u"Сегодняшняя дата: 2026-10-01." in text
    assert u"email_id=7" in text


@pytest.mark.parametrize("answer,count", [
    (u'{"tasks":[{"email_id":1,"task":"a"}]}', 1),
    (u'```json\n{"tasks":[{"email_id":1,"task":"a"}]}\n```', 1),
    (u'```\n{"tasks":[{"email_id":1,"task":"a"}]}', 1),
    (u'Вот задачи:\n{"tasks":[{"email_id":1,"task":"a {b}"},{"email_id":2,"task":"c"}]}\nВсё.', 2),
    (u'[{"email_id":2,"task":"x"}]', 1),
    (u'{"tasks":[]}', 0),
])
def test_parse_tasks_json_tolerant(answer, count):
    assert len(core.parse_tasks_json(answer)) == count


@pytest.mark.parametrize("answer", [u"", u"Задач нет.", u'{"tasks": [', u'{"other": 1}'])
def test_parse_tasks_json_errors(answer):
    with pytest.raises(core.ParseError):
        core.parse_tasks_json(answer)


def test_normalize_task_fields():
    email = _email(3)
    email["sender_name"] = u"Иванов Иван"
    row = core.normalize_task(
        {"email_id": "3", "task": u" Проверить ", "requester": u"", "deadline": u"2026-10-07",
         "priority": u"Высокий", "comment": None},
        {3: email})
    assert row["task"] == u"Проверить"
    assert row["requester"] == u"Иванов Иван"
    assert row["deadline"] == datetime.date(2026, 10, 7)
    assert row["priority"] == core.PRIORITY_HIGH
    assert row["comment"] == u""
    assert row["subject"] == u"тема"


@pytest.mark.parametrize("value", [None, u"null", u"", u"до пятницы", u"2026-13-01"])
def test_normalize_task_bad_deadline_is_none(value):
    assert core.normalize_task({"email_id": 1, "task": u"x", "deadline": value}, {})["deadline"] is None


def test_sort_rows_priority_deadline_received():
    d = datetime.date
    t = datetime.datetime
    rows = [
        {"id": "low", "priority": core.PRIORITY_LOW, "deadline": d(2026, 10, 2), "received": t(2026, 10, 1)},
        {"id": "high-nodl", "priority": core.PRIORITY_HIGH, "deadline": None, "received": t(2026, 10, 1)},
        {"id": "high-late", "priority": core.PRIORITY_HIGH, "deadline": d(2026, 10, 9), "received": t(2026, 10, 1)},
        {"id": "high-soon-old", "priority": core.PRIORITY_HIGH, "deadline": d(2026, 10, 2), "received": t(2026, 9, 29)},
        {"id": "high-soon-new", "priority": core.PRIORITY_HIGH, "deadline": d(2026, 10, 2), "received": t(2026, 10, 1)},
        {"id": "mid", "priority": core.PRIORITY_MEDIUM, "deadline": None, "received": None},
    ]
    assert [r["id"] for r in core.sort_rows(rows)] == [
        "high-soon-new", "high-soon-old", "high-late", "high-nodl", "mid", "low"]


def test_load_test_emails():
    now = datetime.datetime(2026, 10, 1, 12, 0)
    emails = core.load_test_emails(TEST_EMAILS, now=now)
    assert 5 <= len(emails) <= 6
    assert [e["id"] for e in emails] == list(range(1, len(emails) + 1))
    received = [e["received"] for e in emails]
    assert received == sorted(received, reverse=True)
    # «Спасибо» с цитатой: просьба из истории переписки отрезана
    thanks = [e for e in emails if e["subject"].startswith(u"RE:")][0]
    assert u"Прошу прислать" not in thanks["body"]
