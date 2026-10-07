# -*- coding: utf-8 -*-
"""Тесты чистой логики кнопки «Проверка LOI» (lowlife/loi_check_core.py,
LOI.panel/CheckLOI)."""
from lowlife import loi_check_core as core


def test_parse_labels_skips_blank_and_duplicates():
    text = u"Производитель\n\n  Марка  \nПроизводитель\r\nАртикул\n"
    assert core.parse_labels(text) == [u"Производитель", u"Марка", u"Артикул"]


def test_parse_labels_empty():
    assert core.parse_labels(None) == []
    assert core.parse_labels(u"  \n ") == []


def test_build_rows_falls_back_to_label():
    rows = core.build_rows([u"Марка", u"Артикул"], {u"Марка": u" X_Марка ", u"Артикул": u"  "})
    assert rows == [(u"Марка", u"X_Марка"), (u"Артикул", u"Артикул")]


def test_clean_param_map_keeps_only_current_nonempty():
    m = {u"Марка": u"X_Марка", u"Старое": u"Y", u"Артикул": u""}
    assert core.clean_param_map([u"Марка", u"Артикул"], m) == {u"Марка": u"X_Марка"}


def test_status_of():
    assert core.status_of(False, None) == core.ABSENT
    assert core.status_of(True, None) == core.EMPTY
    assert core.status_of(True, u"  ") == core.EMPTY
    assert core.status_of(True, u"0") == core.FILLED


def test_category_summary_counts():
    s = core.CategorySummary(u"Оборудование", [(u"A", u"pa"), (u"B", u"pb")])
    assert s.add([core.FILLED, core.FILLED]) is False
    assert s.add([core.EMPTY, core.FILLED]) is True
    assert s.add([core.FILLED, core.ABSENT]) is True
    assert s.total == 3
    assert s.incomplete == 2
    a, b = s.stats
    assert (a.filled, a.empty, a.absent) == (2, 1, 0)
    assert (b.filled, b.empty, b.absent) == (2, 0, 1)


def test_status_text():
    assert core.status_text(core.FILLED, u" x ") == u"x"
    assert core.status_text(core.EMPTY, None) == u"—"
    assert core.status_text(core.ABSENT, None) == u"нет параметра"


def test_schedule_name_strips_forbidden_chars():
    assert core.schedule_name(u"LOI проверка", u"Лотки: [кабельные]") == \
        u"LOI проверка — Лотки_ _кабельные_"
