# -*- coding: utf-8 -*-
"""Тесты для lowlife.tray_boxes_core — размеры и положение боксов кнопки
«Боксы на лотки» (Tools.panel/TrayOpeningBoxes)."""

import math

from lowlife.tray_boxes_core import (merge_intervals, wall_box, floor_box, sized_type_name,
                                     name_has, split_words, SKIP_SLOPED, SKIP_ANGLE)


def _close(a, b, tol=1e-9):
    return abs(a - b) < tol


def test_merge_intervals():
    assert merge_intervals([(5, 6), (1, 2), (2, 3)]) == [(1, 3), (5, 6)]
    assert merge_intervals([(3, 1)]) == [(1, 3)]
    assert merge_intervals([(1, 4), (2, 3)]) == [(1, 4)]
    assert merge_intervals([]) == []


def test_wall_box_perpendicular():
    # лоток 300×100 вдоль X сквозь стену вдоль Y толщиной 200
    box, why = wall_box((0, 0, 3000), (1, 0, 0), (0, 1, 0), 200.0, 300.0, 100.0,
                        50.0, 0.0, 1.0, 60.0)
    assert why is None
    assert _close(box.width, 350.0)
    assert _close(box.height, 150.0)
    assert _close(box.depth, 200.0)
    assert _close(box.thickness, 200.0)
    assert _close(abs(box.angle()), math.pi / 2)
    assert box.origin(True) == (0, 0, 3000 - 75.0)
    assert box.origin(False) == (0, 0, 3000)


def test_wall_box_oblique_widens_along_wall():
    a = math.radians(30)
    d = (math.cos(a), math.sin(a), 0.0)
    # длина оси внутри стены 200 мм толщины — 200 / cos30
    box, why = wall_box((0, 0, 0), d, (0, 1, 0), 200.0 / math.cos(a), 300.0, 100.0,
                        50.0, 10.0, 1.0, 60.0)
    assert why is None
    assert _close(box.thickness, 200.0, 1e-6)
    assert _close(box.depth, 210.0, 1e-6)
    assert _close(box.width, 300.0 / math.cos(a) + 200.0 * math.tan(a) + 50.0, 1e-6)


def test_wall_box_skips():
    assert wall_box((0, 0, 0), (1, 0, 0.5), (0, 1, 0), 200, 300, 100, 50, 0, 1, 60)[1] == SKIP_SLOPED
    assert wall_box((0, 0, 0), (0, 0, 1), (0, 1, 0), 200, 300, 100, 50, 0, 1, 60)[1] == SKIP_SLOPED
    # почти вдоль стены
    d = (math.cos(math.radians(80)), math.sin(math.radians(80)), 0)
    assert wall_box((0, 0, 0), d, (0, 1, 0), 200, 300, 100, 50, 0, 1, 60)[1] == SKIP_ANGLE


def test_floor_box():
    box, why = floor_box((1, 2, 3), (0, 0, -1), (0, 1, 0), 250.0, 400.0, 80.0,
                         50.0, 0.0, 1.0)
    assert why is None
    assert _close(box.width, 450.0)
    assert _close(box.depth, 130.0)
    assert _close(box.height, 250.0)
    assert _close(box.angle(), math.pi / 2)
    assert floor_box((0, 0, 0), (1, 0, 0), (0, 1, 0), 250, 400, 80, 50, 0, 1)[1] == SKIP_SLOPED


def test_names():
    assert sized_type_name(u"Временный", 350, 200.4, 150) == u"Временный 350x200x150"
    assert name_has(u"Бокс_прямоугольный", [u"бокс"])
    assert not name_has(u"Отверстие", [u"бокс"])
    assert name_has(u"что угодно", [])
    assert split_words(u" бокс, , box ") == [u"бокс", u"box"]
