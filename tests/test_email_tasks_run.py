# -*- coding: utf-8 -*-
"""Тесты для lowlife.email_tasks_run — сценарий «Задач из почты», общий для
кнопки в Revit и отдельного приложения (apps/mail): тестовые письма → ИИ
пачками → запись в Excel, ошибки и отмена."""

import json
import os

import pytest

from lowlife import email_ai_core, email_tasks_run

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_EMAILS = os.path.join(ROOT, "LowLife.tab", "Mail.panel", "EmailTasks.pushbutton", "test_emails.json")
SETTINGS = {"days": 3, "unread_only": True, "subfolder": u"", "include_subfolders": True, "test_mode": True}


class Progress(object):
    def __init__(self, cancel_after=None):
        self.titles = []
        self.calls = 0
        self.cancel_after = cancel_after

    def title(self, text):
        self.titles.append(text)

    def progress(self, done, total):
        pass

    def busy(self):
        pass

    def cancelled(self):
        self.calls += 1
        return self.cancel_after is not None and self.calls > self.cancel_after


class Engine(object):
    name = u"Тест"
    description = u"тест"

    def __init__(self, answer=None, error=None):
        self.answer = answer
        self.error = error
        self.requests = []

    def run(self, request_text, tick=None):
        self.requests.append(request_text)
        if self.error is not None:
            raise self.error
        return self.answer


class Excel(object):
    class ExcelError(Exception):
        def __init__(self, message):
            Exception.__init__(self, message)
            self.message = message

    def __init__(self, fail=False):
        self.saved = None
        self.fail = fail

    def default_output_path(self):
        return u"out.xlsx"

    def save_tasks(self, rows, path):
        if self.fail:
            raise self.ExcelError(u"нет Excel")
        self.saved = (rows, path)
        return [u"предупреждение"]


def _answer(*ids):
    return json.dumps({"tasks": [{"email_id": i, "task": u"Задача {}".format(i), "priority": u"высокий"}
                                 for i in ids]})


def _run(engine, progress=None, excel=None, settings=SETTINGS):
    return email_tasks_run.run(settings, u"промпт", engine, progress or Progress(), excel or Excel(),
                               test_emails_file=TEST_EMAILS)


def test_tasks_are_saved_to_excel():
    excel = Excel()
    result = _run(Engine(_answer(1, 2)), excel=excel)
    assert len(result.emails) == 6 and result.folder_name.startswith(u"ТЕСТОВЫЙ РЕЖИМ")
    assert [r["task"] for r in result.rows] == [u"Задача 1", u"Задача 2"]
    assert result.excel_path == u"out.xlsx" and excel.saved[1] == u"out.xlsx"
    assert result.excel_warnings == [u"предупреждение"]
    assert not result.fatal_error and not result.cancelled
    assert result.period == u"3 дн., только непрочитанные"
    assert email_tasks_run.table(result.rows)[0][:2] == [1, u"Задача 1"]


def test_fatal_ai_error_stops_without_excel():
    excel = Excel()
    result = _run(Engine(error=email_ai_core.AIError(u"нет ключа", fatal=True, details=u"401")), excel=excel)
    assert result.fatal_error.startswith(u"нет ключа") and u"401" in result.fatal_error
    assert excel.saved is None and result.rows == []


def test_non_fatal_error_is_collected_per_batch():
    result = _run(Engine(error=email_ai_core.AIError(u"сбой")))
    assert result.batch_errors and result.batch_errors[0].startswith(u"Часть 1 из 1: сбой")
    assert not result.fatal_error and result.excel_path is None


def test_unparsable_answer_is_kept_in_a_file(tmpdir, monkeypatch):
    monkeypatch.setenv("TEMP", str(tmpdir))
    result = _run(Engine(u"не JSON"))
    assert u"не удалось разобрать ответ" in result.batch_errors[0]
    saved = tmpdir.join("LowLifeEmailTasks").listdir()
    assert len(saved) == 1 and saved[0].read_text("utf-8") == u"не JSON"


def test_cancel_during_ai():
    class Cancelling(Engine):
        def run(self, request_text, tick=None):
            raise email_ai_core.Cancelled()
    excel = Excel()
    result = _run(Cancelling(), excel=excel)
    assert result.cancelled and excel.saved is None


def test_excel_error_keeps_rows():
    result = _run(Engine(_answer(1)), excel=Excel(fail=True))
    assert result.excel_error == u"нет Excel" and result.excel_path is None and len(result.rows) == 1


def test_missing_test_file_is_fatal():
    result = email_tasks_run.run(SETTINGS, u"п", Engine(_answer(1)), Progress(), Excel(),
                                 test_emails_file=u"нет-такого.json")
    assert u"Не удалось прочитать тестовые письма" in result.fatal_error
