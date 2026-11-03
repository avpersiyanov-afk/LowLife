# -*- coding: utf-8 -*-
"""Тесты для lowlife.tray_boxes_core — размеры и положение боксов кнопки
«Боксы на лотки» (Tools.panel/TrayOpeningBoxes)."""

import math
import pytest
from datetime import datetime

from lowlife.tray_boxes_core import (merge_intervals, wall_box, floor_box, sized_type_name,
                                     name_has, split_words, creation_comment,
                                     SKIP_SLOPED, SKIP_ANGLE)
from lowlife.tray_boxes_core import (Box, WALL, FLOOR, opening_sides,
                                     recommended_increase_mm, enlarge_opening)


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
    assert _close(box.width, 400.0)
    assert _close(box.height, 200.0)
    assert _close(box.depth, 200.0)
    assert _close(box.thickness, 200.0)
    assert _close(abs(box.angle()), math.pi / 2)
    assert box.origin(True) == (0, 0, 3000 - 100.0)
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
    assert _close(box.width, 300.0 / math.cos(a) + 200.0 * math.tan(a) + 100.0, 1e-6)


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
    assert _close(box.width, 500.0)
    assert _close(box.depth, 180.0)
    assert _close(box.height, 250.0)
    assert _close(box.angle(), math.pi / 2)
    assert floor_box((0, 0, 0), (1, 0, 0), (0, 1, 0), 250, 400, 80, 50, 0, 1)[1] == SKIP_SLOPED


def test_creation_comment():
    when = datetime(2026, 3, 5, 9, 7)
    assert creation_comment(u"ivanov", when) == u"ivanov 05.03.2026 09:07"
    assert creation_comment(u"", when) == u"05.03.2026 09:07"


def test_names():
    assert sized_type_name(u"Временный", 350, 200.4, 150) == u"Временный 350x200x150"
    assert name_has(u"Бокс_прямоугольный", [u"бокс"])
    assert not name_has(u"Отверстие", [u"бокс"])
    assert name_has(u"что угодно", [])
    assert split_words(u" бокс, , box ") == [u"бокс", u"box"]


@pytest.mark.parametrize("side, expected", [(100, 50), (300, 50), (300.001, 100),
                                            (600, 100), (600.001, 150), (1200, 150)])
def test_recommended_increase_boundaries(side, expected):
    assert recommended_increase_mm(side) == expected
    # Размер проходит перевод мм → футы → мм.
    assert recommended_increase_mm(side / 304.8 * 304.8) == expected


@pytest.mark.parametrize("kind, dimensions, expected", [
    (WALL, (400, 900, 200), (500, 900, 300)),
    (WALL, (200, 900, 400), (300, 900, 500)),
    (FLOOR, (400, 200, 900), (500, 300, 900)),
    (FLOOR, (200, 400, 900), (300, 500, 900)),
    (WALL, (400, 900, 400), (500, 900, 500)),
])
def test_enlarge_both_opening_sides(kind, dimensions, expected):
    original = Box(kind, (10, 20, 30), (0, 1, 0), *dimensions, thickness=900)
    enlarged = enlarge_opening(original, 100)
    assert (enlarged.width, enlarged.depth, enlarged.height) == expected
    assert (original.width, original.depth, original.height) == dimensions
    assert enlarged.center == original.center
    assert enlarged.x_dir == original.x_dir
    assert enlarged.thickness == original.thickness
    assert enlarge_opening(original, 0).origin(True) == original.origin(True)


def test_auto_uses_opening_after_clearances_and_preserves_center():
    box, _ = wall_box((0, 0, 1000), (1, 0, 0), (0, 1, 0), 900, 100, 250,
                      50, 0, 1, 60)
    assert opening_sides(box) == (200, 350)
    amount = recommended_increase_mm(max(opening_sides(box)))
    enlarged = enlarge_opening(box, amount)
    assert opening_sides(enlarged) == (300, 450)
    assert enlarged.depth == 900  # Толщина стены не считается стороной отверстия.
    assert enlarged.origin(True)[2] - box.origin(True)[2] == -50
    assert enlarged.origin(True)[2] + enlarged.height / 2 == box.center[2]
    with pytest.raises(ValueError):
        enlarge_opening(box, -1)
