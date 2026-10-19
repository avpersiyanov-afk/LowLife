# -*- coding: utf-8 -*-
import math

from lowlife import detector_access_core as core


def _square(cx, cy, half):
    return [(cx - half, cy - half), (cx + half, cy - half), (cx + half, cy + half), (cx - half, cy + half)]


def test_convex_hull_drops_inner_and_duplicate_points():
    points = [(0, 0), (10, 0), (10, 10), (0, 10), (5, 5), (0, 0), (10, 10)]
    hull = core.convex_hull(points)
    assert sorted(hull) == [(0.0, 0.0), (0.0, 10.0), (10.0, 0.0), (10.0, 10.0)]


def test_segment_rect_along_and_degenerate():
    rect = core.segment_rect(0, 0, 1000, 0, 100)
    assert sorted(rect) == [(0, -100), (0, 100), (1000, -100), (1000, 100)]
    riser = core.segment_rect(50, 50, 50, 50, 25)
    assert sorted(riser) == [(25, 25), (25, 75), (75, 25), (75, 75)]


def test_polygon_distance_inside_outside_and_diagonal():
    square = _square(0, 0, 100)
    assert core.polygon_distance(0, 0, square) == 0.0
    assert core.polygon_distance(300, 0, square) == 200.0
    assert abs(core.polygon_distance(200, 200, square) - math.hypot(100, 100)) < 1e-9
    # наклонный воздуховод: габарит в плане — повёрнутый прямоугольник, а не вся коробка
    duct = core.segment_rect(0, 0, 1000, 1000, 100)
    assert core.polygon_distance(500, 500, duct) == 0.0
    assert core.polygon_distance(1000, 0, duct) > 500


def test_obstacle_height_and_circle():
    duct = core.Obstacle(u"Воздуховоды", _square(0, 0, 200), 2500, 2900)
    assert duct.touches_circle(500, 0, 400)       # край в 300 мм — заходит в круг 400
    assert not duct.touches_circle(700, 0, 400)
    assert core.blockers([duct], 500, 0, 400, 20, 3150) == [duct]
    # воздуховод выше проверяемого объёма (у самого перекрытия) — не мешает
    assert core.blockers([duct], 500, 0, 400, 20, 2400) == []
    assert core.blockers([duct], 500, 0, 400, 3000, 2000) == []


def test_obstacle_index_near():
    index = core.ObstacleIndex(cell_mm=1000)
    a = core.Obstacle(u"Трубы", _square(0, 0, 50), 0, 100)
    b = core.Obstacle(u"Лотки", _square(10000, 0, 50), 0, 100)
    long_duct = core.Obstacle(u"Воздуховоды", core.segment_rect(-5000, 3000, 5000, 3000, 100), 0, 100)
    for o in (a, b, long_duct):
        index.add(o)
    assert index.near(0, 0, 500) == [a]
    assert index.near(4000, 2500, 600) == [long_duct]
    assert len(index) == 3


def test_mount_kind_and_surface():
    assert core.mount_kind(3300, None) == "slab"
    assert core.mount_kind(2750, 2700) == "ceiling"
    assert core.mount_kind(3300, 2700) == "above"
    assert core.mount_z("slab", 3300, None) == 3300
    assert core.mount_z("slab", 3300, 2700) is None    # над потолком — не на плите
    assert core.mount_z("ceiling", 3300, 2700) == 2700
    assert core.same_surface("slab", 3300, 3350, None)
    assert not core.same_surface("slab", 3300, 3600, None)
    assert not core.same_surface("ceiling", 2700, 3300, None)


def test_has_floor_and_band():
    assert core.has_floor(True, -50, 0)
    assert not core.has_floor(False, 0, 0)
    assert not core.has_floor(True, -3300, 0)          # луч ушёл в шахту до нижнего этажа
    assert core.column_band(0, 3300, 150) == (20.0, 3150.0)


def test_classify_order():
    duct = core.Obstacle(u"Воздуховоды", _square(0, 0, 100), 2500, 2800)
    assert core.classify(True, "above", 3300, 0, [duct]) == core.ABOVE_CEILING
    assert core.classify(False, "slab", 3300, 0, []) == core.NO_FLOOR
    assert core.classify(True, "slab", 100, 0, []) == core.NOT_MOUNTED
    assert core.classify(True, "slab", 3300, 0, [duct]) == core.BLOCKED
    assert core.classify(True, "slab", 6000, 4500, []) == core.TOO_HIGH
    assert core.classify(True, "slab", 6000, 0, []) == core.OK


def test_ring_offsets_sorted_by_distance():
    offsets = list(core.ring_offsets(100, 300))
    distances = [round(math.hypot(dx, dy), 6) for dx, dy in offsets]
    assert distances == sorted(distances)
    assert abs(distances[0] - 100) < 1e-6 and abs(distances[-1] - 300) < 1e-6
    assert list(core.ring_offsets(100, 0)) == []


def test_find_spot_nearest_free_and_accept():
    # воздуховод шириной 400 над извещателем вдоль оси X
    duct = core.Obstacle(u"Воздуховоды", core.segment_rect(-5000, 0, 5000, 0, 200), 2500, 2900)
    spot = core.find_spot(0, 0, [duct], 500, 20, 3150, 100, 3000)
    assert spot is not None
    assert abs(core.polygon_distance(spot[0], spot[1], duct.polygon) - 500) <= 100
    # accept отбрасывает всё с y > 0 — место по другую сторону
    other = core.find_spot(0, 0, [duct], 500, 20, 3150, 100, 3000, accept=lambda x, y: y < 0)
    assert other[1] < 0
    # некуда: radius поиска меньше нужного смещения
    assert core.find_spot(0, 0, [duct], 500, 20, 3150, 100, 300) is None
    # accept вызывается не больше max_checks раз
    calls = []
    core.find_spot(0, 0, [], 500, 20, 3150, 100, 3000,
                   accept=lambda x, y: calls.append(1) and False, max_checks=5)
    assert len(calls) == 5


def test_texts():
    duct = core.Obstacle(u"Воздуховоды", _square(0, 0, 10), 0, 1)
    pipe = core.Obstacle(u"Трубы", _square(0, 0, 10), 0, 1)
    assert core.obstacle_names([pipe, duct, duct]) == u"Воздуховоды ×2, Трубы"
    assert core.reason_text(core.BLOCKED, [pipe, duct], [duct]) == u"перекрыт: Воздуховоды"
    assert core.reason_text(core.BLOCKED, [pipe], []) == u"зона доступа: Трубы"
    assert core.reason_text(core.NO_FLOOR, [], []) == core.STATUS_TEXT[core.NO_FLOOR]
    assert core.blocked_label(u"Нет доступа: {r}", u"x") == u"Нет доступа: x"
    assert core.move_label(u"Перенести ПИ на {d} мм", 300, 400) == u"Перенести ПИ на 500 мм"
    assert core.move_label(u"битый {шаблон", 300, 400).startswith(u"битый {шаблон")
