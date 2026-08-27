# -*- coding: utf-8 -*-
"""Тесты для чистых (без Revit API) функций lowlife.scs_schematic —
panel_riser_x, panel_collector_y и panel_color_rgb; sync_panel_buses/
_get_or_create_line_style импортируют Autodesk.Revit.DB лениво (внутри
тела функции) именно затем, чтобы этот модуль оставался импортируемым
и тестируемым вне Revit (см. tests/README.md)."""

import pytest

from lowlife import scs_schematic


def test_first_panel_is_at_base_offset():
    # index=0 -> RISER_BASE_OFFSET_MM левее X=0 (рамок), без RISER_SPACING_MM.
    x0 = scs_schematic.panel_riser_x(0)
    expected = -scs_schematic.RISER_BASE_OFFSET_MM * scs_schematic.MM_TO_FT
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


def test_panel_color_rgb_returns_distinct_colors_for_distinct_panels():
    colors = [scs_schematic.panel_color_rgb(i, 4) for i in range(4)]
    assert len(set(colors)) == 4


def test_panel_color_rgb_components_in_byte_range():
    for i in range(5):
        r, g, b = scs_schematic.panel_color_rgb(i, 5)
        for component in (r, g, b):
            assert 0 <= component <= 255


def test_panel_color_rgb_single_panel_does_not_crash():
    # panel_count=1 (или 0, защитный случай) — hue=0, не деление на ноль.
    assert scs_schematic.panel_color_rgb(0, 1) is not None
    assert scs_schematic.panel_color_rgb(0, 0) is not None


def test_first_panel_collector_is_at_base_drop_offset():
    y0 = scs_schematic.panel_collector_y(0, 100.0)
    expected = 100.0 - scs_schematic.BUS_DROP_OFFSET_MM * scs_schematic.MM_TO_FT
    assert y0 == pytest.approx(expected)


def test_panel_collectors_stack_further_from_level_for_each_next_panel():
    level_y = 50.0
    y0 = scs_schematic.panel_collector_y(0, level_y)
    y1 = scs_schematic.panel_collector_y(1, level_y)
    y2 = scs_schematic.panel_collector_y(2, level_y)

    # Каждая следующая панель дальше (ниже) от этажа — коллекторы не
    # накладываются друг на друга по Y.
    assert y1 < y0
    assert y2 < y1

    spacing_ft = scs_schematic.BUS_DROP_SPACING_MM * scs_schematic.MM_TO_FT
    assert y0 - y1 == pytest.approx(spacing_ft)
    assert y1 - y2 == pytest.approx(spacing_ft)


def test_trunk_jump_overlapping_ranges_touches_both_directly():
    # A: [0, 10], B: [5, 20] -> пересечение [5, 10], jump на верхней границе (10).
    jump_y, ext_a, ext_b = scs_schematic.trunk_jump_geometry(0.0, 10.0, 5.0, 20.0)
    assert jump_y == pytest.approx(10.0)
    assert ext_a is None
    assert ext_b is None


def test_trunk_jump_far_apart_ranges_meets_in_the_middle_of_the_gap():
    # A: [0, 10] (например, нижние этажи), B: [50, 60] (далёкие верхние
    # этажи) -> разрыв [10, 50], переход посередине (30), а не впритык
    # к границе одного из стояков.
    jump_y, ext_a, ext_b = scs_schematic.trunk_jump_geometry(0.0, 10.0, 50.0, 60.0)
    assert jump_y == pytest.approx(30.0)
    assert ext_a == pytest.approx((10.0, 30.0))
    assert ext_b == pytest.approx((50.0, 30.0))


def test_trunk_jump_far_apart_ranges_order_independent():
    # То же самое, но панели переданы в обратном порядке (B ниже A) —
    # результат симметричный.
    jump_y, ext_a, ext_b = scs_schematic.trunk_jump_geometry(50.0, 60.0, 0.0, 10.0)
    assert jump_y == pytest.approx(30.0)
    assert ext_a == pytest.approx((50.0, 30.0))
    assert ext_b == pytest.approx((10.0, 30.0))


def test_trunk_jump_touching_ranges_no_gap_no_extension():
    # A: [0, 10], B: [10, 20] -> касаются ровно в одной точке (10),
    # переход там же, достройка не нужна ни одной из сторон.
    jump_y, ext_a, ext_b = scs_schematic.trunk_jump_geometry(0.0, 10.0, 10.0, 20.0)
    assert jump_y == pytest.approx(10.0)
    assert ext_a is None
    assert ext_b is None


def test_trunk_jump_single_point_ranges():
    # Панель без своих устройств (только сама панель) на одном этаже
    # каждая — min_y == max_y для обеих.
    jump_y, ext_a, ext_b = scs_schematic.trunk_jump_geometry(5.0, 5.0, 25.0, 25.0)
    assert jump_y == pytest.approx(15.0)
    assert ext_a == pytest.approx((5.0, 15.0))
    assert ext_b == pytest.approx((25.0, 15.0))
