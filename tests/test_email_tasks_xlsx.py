# -*- coding: utf-8 -*-
"""Тесты для lowlife.email_tasks_xlsx — таблица задач через openpyxl в
отдельном приложении «Задачи из почты» (apps/mail)."""

import datetime

import pytest

openpyxl = pytest.importorskip("openpyxl")

from lowlife import email_tasks_core, email_tasks_xlsx  # noqa: E402

ROWS = [
    {"task": u"=Сделать схему", "requester": u"ГИП", "deadline": datetime.date(2026, 10, 1),
     "priority": u"высокий", "comment": u"", "subject": u"Схема", "sender": u"a@b.c",
     "received": datetime.datetime(2026, 9, 30, 10, 15)},
    {"task": u"Ответить", "requester": u"", "deadline": None, "priority": u"низкий", "comment": u"к пятнице",
     "subject": u"RE:", "sender": u"", "received": None},
]


def test_workbook_matches_the_revit_table(tmpdir):
    path = str(tmpdir.join("t.xlsx"))
    assert email_tasks_xlsx.save_tasks(ROWS, path, open_file=False) == []
    wb = openpyxl.load_workbook(path)
    ws = wb[u"Задачи"]
    assert [c.value for c in ws[1]] == [title for title, _w in email_tasks_core.COLUMNS]
    first = [c.value for c in ws[2]]
    assert first[0] == 1 and first[1] == u"'=Сделать схему"  # не формула
    assert first[3].date() == datetime.date(2026, 10, 1) and ws[u"D2"].number_format == u"dd.mm.yyyy"
    assert first[5] == email_tasks_core.STATUSES[0]
    assert ws[u"J2"].number_format == u"dd.mm.yyyy hh:mm"
    assert ws[u"D3"].value is None
    assert ws.freeze_panes == u"A2" and ws.auto_filter.ref == u"A1:J3"
    assert wb[u"Списки"].sheet_state == u"hidden" and wb[u"Списки"][u"B1"].value == u"=TODAY()"
    assert set(wb.defined_names.keys()) >= {u"StatusList", u"TodayDate"}
    validation = ws.data_validations.dataValidation[0]
    assert validation.formula1 == u"=StatusList" and str(validation.sqref) == u"F2:F203"
    rules = dict((str(k.sqref), [r.formula[0] for r in v]) for k, v in ws.conditional_formatting._cf_rules.items())
    assert rules[u"A2:J3"] == [u'$F2="Готово"']
    assert u"TodayDate" in rules[u"D2:D3"][0]


def test_empty_list_still_has_a_header(tmpdir):
    path = str(tmpdir.join("e.xlsx"))
    email_tasks_xlsx.save_tasks([], path, open_file=False)
    ws = openpyxl.load_workbook(path)[u"Задачи"]
    assert ws.max_row == 1


def test_default_output_path(tmpdir, monkeypatch):
    monkeypatch.setattr(email_tasks_xlsx, "documents_folder", lambda: str(tmpdir))
    path = email_tasks_xlsx.default_output_path(datetime.datetime(2026, 10, 23, 9, 5))
    assert path == str(tmpdir.join(u"Задачи из почты", u"Задачи_2026-10-23_0905.xlsx"))
    assert tmpdir.join(u"Задачи из почты").isdir()
