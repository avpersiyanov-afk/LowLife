# -*- coding: utf-8 -*-
"""Тесты для lowlife.scs_schematic.panel_riser_x — единственная чистая
(без Revit API) функция в модуле; sync_panel_buses импортирует
lowlife.sot_schematic лениво (внутри тела функции) именно затем, чтобы
этот модуль оставался импортируемым и тестируемым вне Revit (см.
tests/README.md)."""

import pytest

from lowlife import scs_schematic


def test_first_panel_is_closest_to_room_frames():
    # index=0 -> одно расстояние RISER_SPACING_MM левее X=0 (рамок).
    x0 = scs_schematic.panel_riser_x(0)
    expected = -scs_schematic.RISER_SPACING_MM * scs_schematic.MM_TO_FT
    assert x0 == pytest.approx(expected)


def test_risers_spaced_out_and_ordered_left_to_right():
    x0 = scs_schematic.panel_riser_x(0)
    x1 = scs_schematic.panel_riser_x(1)
    x2 = scs_schematic.panel_riser_x(2)

    # Каждая следующая панель левее предыдущей (дальше от рамок) — не
    # накладываются друг на друга.
    assert x1 < x0
    assert x2 < x1

    spacing_ft = scs_schematic.RISER_SPACING_MM * scs_schematic.MM_TO_FT
    assert x0 - x1 == pytest.approx(spacing_ft)
    assert x1 - x2 == pytest.approx(spacing_ft)
