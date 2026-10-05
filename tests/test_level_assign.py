# -*- coding: utf-8 -*-
"""Тесты для lowlife.level_assign.pick_level_by_elevation — уровень по
высоте для элементов без опорного уровня (кнопка «Обновить имя уровня»,
LOI.panel/UpdateLevelName)."""

from lowlife.level_assign import pick_level_by_elevation

LEVELS = [(10.0, "L2"), (-5.0, "B1"), (0.0, "L1"), (20.0, "L3")]


def test_no_levels():
    assert pick_level_by_elevation(3.0, []) is None


def test_nearest_level_below():
    assert pick_level_by_elevation(3.0, LEVELS) == "L1"
    assert pick_level_by_elevation(15.0, LEVELS) == "L2"
    assert pick_level_by_elevation(100.0, LEVELS) == "L3"
    assert pick_level_by_elevation(-1.0, LEVELS) == "B1"


def test_on_level_within_tolerance():
    assert pick_level_by_elevation(10.0, LEVELS) == "L2"
    assert pick_level_by_elevation(9.995, LEVELS) == "L2"
    assert pick_level_by_elevation(9.9, LEVELS) == "L1"


def test_below_all_levels_gets_lowest():
    assert pick_level_by_elevation(-50.0, LEVELS) == "B1"
