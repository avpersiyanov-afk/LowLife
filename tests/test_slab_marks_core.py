# -*- coding: utf-8 -*-
from lowlife import slab_marks_core as core


def test_probe_slab_and_floor():
    # точка на 1500 над уровнем 0: перекрытие в 1800 выше, пол 50 ниже уровня точки отсчёта
    up = [(1800.0, core.SLAB), (2000.0, core.SLAB), (5000.0, core.SLAB)]
    down = [(1550.0, core.SLAB)]
    found = core.probe(1500.0, up, down, 0.0)
    assert found.slab_z_mm == 3300.0
    assert found.floor_z_mm == -50.0
    assert found.slab_mm == 3350.0
    assert found.ceiling_mm is None


def test_probe_ceiling_below_slab():
    up = [(1200.0, core.CEILING), (1800.0, core.SLAB), (1210.0, core.CEILING)]
    found = core.probe(1500.0, up, [], 0.0)
    assert found.floor_z_mm == 0.0           # пола нет — уровень
    assert found.ceiling_mm == 2700.0
    assert found.slab_mm == 3300.0


def test_probe_ceiling_above_slab_ignored_and_no_slab():
    found = core.probe(1500.0, [(1800.0, core.SLAB), (2500.0, core.CEILING)], [], 0.0)
    assert found.ceiling_mm is None
    assert core.probe(1500.0, [(1000.0, core.CEILING), (500.0, None)], [], 0.0) is None


def test_format_height():
    assert core.format_height(3300) == u"+3,300"
    assert core.format_height(-450) == u"-0,450"
    assert core.format_height(0) == u"±0,000"
    assert core.format_height(3300, signed=False) == u"3,300"


def test_heights_rounding_and_range():
    assert core.height_range_text([3301.0, 3299.0], 10) == u"+3,300"
    assert core.height_range_text([3300.0, 3750.0, None], 10) == u"+3,300…+3,750"
    assert core.height_range_text([None], 10) == u""


def test_main_and_typical_height():
    assert core.main_height([3300, 3300, 3750], 10) == 3300
    assert core.main_height([3750, 3300], 10) == 3300   # при равенстве — меньшая
    assert core.main_height([None], 10) is None
    assert core.typical_height([3300, 3300, 3600, None], 10) == 3300


def test_room_label():
    text = core.room_label([3750.0], [2700.0], 3300.0, 10,
                           u"Пер. {h}", u"ПП {h}", u"Δ {d}")
    assert text == u"Пер. +3,750\nΔ +0,450\nПП +2,700"
    same = core.room_label([3300.0], [None], 3300.0, 10, u"Пер. {h}", u"ПП {h}", u"Δ {d}")
    assert same == u"Пер. +3,300"
    lower = core.room_label([3000.0], [], 3300.0, 10, u"{h}", u"ПП {h}", u"Δ {d}")
    assert lower == u"+3,000\nΔ -0,300"


def test_room_label_bad_template_falls_back():
    assert core.room_label([3300.0], [], None, 10, u"Пер. {x}", u"", u"") == u"Пер. {x} +3,300"


def test_is_detector():
    include = core.split_words(u"дым, тепл; ИП 212")
    exclude = core.split_words(u"ручн, ИПР")
    assert core.is_detector([u"Извещатель пожарный дымовой", u"ИП 212-64"], include, exclude)
    assert not core.is_detector([u"Извещатель пожарный ручной", u"ИПР 513"], include, exclude)
    assert not core.is_detector([u"Оповещатель", u"Табло"], include, exclude)
    assert core.is_detector([u"Что угодно"], [], exclude)
    assert core.is_detector([u"Извещатель тепловой (Ё)"], core.split_words(u"тЕпл"), [])


def test_move_delta_and_grid():
    assert core.move_delta(2500.0, 3300.0, 0) == 800.0
    assert core.move_delta(3400.0, 3300.0, 50) == -150.0
    assert core.grid_steps(2000) == 1
    assert core.grid_steps(7000) == 3
    assert core.grid_steps(50000) == 3


def test_step_segments_adjacent_slabs():
    # плита A (низ 3300) до x=5000, плита B (низ 3750) от x=5000; края граней совпадают
    edges = [
        (0, 0, 5000, 0, 3300), (5000, 0, 5000, 4000, 3300),
        (5000, 4000, 0, 4000, 3300), (0, 4000, 0, 0, 3300),
        (5000, 1000, 9000, 1000, 3750), (9000, 1000, 9000, 6000, 3750),
        (9000, 6000, 5000, 6000, 3750), (5000, 6000, 5000, 1000, 3750),
    ]
    steps = core.step_segments(edges, 300, 20)
    assert len(steps) == 1
    x1, y1, x2, y2, dz = steps[0]
    assert abs(x1 - 5000) < 1e-6 and abs(x2 - 5000) < 1e-6
    assert sorted([y1, y2]) == [1000, 4000]
    assert abs(dz) == 450


def test_step_segments_gap_midline_and_filters():
    # края на расстоянии 200 мм (стена между плитами) — линия посередине
    steps = core.step_segments([(0, 0, 0, 3000, 3300), (200, 3000, 200, 0, 3600)], 300, 20)
    assert len(steps) == 1
    assert abs(steps[0][0] - 100) < 1e-6 and abs(steps[0][2] - 100) < 1e-6
    # одинаковая отметка, слишком далеко, не параллельны — не перепад
    assert core.step_segments([(0, 0, 0, 3000, 3300), (100, 0, 100, 3000, 3305)], 300, 20) == []
    assert core.step_segments([(0, 0, 0, 3000, 3300), (500, 0, 500, 3000, 3600)], 300, 20) == []
    assert core.step_segments([(0, 0, 0, 3000, 3300), (0, 0, 3000, 3000, 3600)], 300, 20) == []


def test_step_segments_many_edges_angle_buckets():
    # сетка параллельных краёв: перепад находится только между соседями с разной отметкой
    edges = []
    for i in range(50):
        z = 3300 if i < 25 else 3750
        edges.append((i * 1000.0, 0.0, i * 1000.0, 3000.0, z))
        edges.append((0.0, 10000.0 + i * 1000.0, 3000.0, 10000.0 + i * 1000.0, 3300))
    # край почти по оси (наклон <1°) рядом с краем другой отметки
    edges.append((24100.0, 0.0, 24110.0, 3000.0, 3750))
    steps = core.step_segments(edges, 300, 20)
    assert len(steps) == 1
    assert 24000 <= steps[0][0] <= 24110


def test_group_by_height():
    changed = [(u"Кладовая", 7010), (u"Помещение", 7010), (u"Кладовая", 7010), (u"ГРЩ", 3600)]
    assert core.group_by_height(changed) == [
        (3600, [(u"ГРЩ", 1)]),
        (7010, [(u"Кладовая", 2), (u"Помещение", 1)]),
    ]


def test_mount_surface():
    with_ceiling = core.probe(1500.0, [(1200.0, core.CEILING), (1800.0, core.SLAB)], [(1550.0, core.SLAB)], 0.0)
    assert with_ceiling.ceiling_z_mm == 2700.0
    assert core.mount_surface(with_ceiling, False) == (3300.0, None)
    assert core.mount_surface(with_ceiling, True) == (2700.0, None)
    no_ceiling = core.probe(1500.0, [(1800.0, core.SLAB)], [], 0.0)
    surface, reason = core.mount_surface(no_ceiling, True)
    assert surface is None and u"потолка" in reason
    words = core.split_words(u"встраив")
    assert core.is_detector([u"ИП 212", u"Дымовой встраиваемый"], words, [])
    assert not core.is_detector([u"ИП 212", u"Дымовой"], words, [])


def test_opening_slab_z():
    # точка над шахтой: сверху плита через этаж, вокруг — плита этажа
    assert core.opening_slab_z(9600.0, [3300.0, 3300.0, 3310.0, 3300.0]) == 3310.0
    # высокая зона: хотя бы с одной стороны та же высота — не отверстие
    assert core.opening_slab_z(7650.0, [7650.0, 4800.0, 4800.0, 4800.0]) is None
    # край здания: перекрытие найдено меньше чем в двух точках
    assert core.opening_slab_z(9600.0, [None, None, None, 3300.0]) is None
    assert core.opening_slab_z(9600.0, [None, 3300.0, None, 3300.0]) == 3300.0


def test_replace_slab():
    found = core.probe(1500.0, [(1200.0, core.CEILING), (8000.0, core.SLAB)], [], 0.0)
    fixed = core.replace_slab(found, 3300.0)
    assert fixed.slab_mm == 3300.0 and fixed.through_opening
    assert fixed.ceiling_mm == 2700.0
    # потолок выше плиты вокруг отверстия — это потолок другого этажа
    high = core.probe(1500.0, [(5000.0, core.CEILING), (8000.0, core.SLAB)], [], 0.0)
    assert core.replace_slab(high, 3300.0).ceiling_mm is None


def test_probe_floor_found_flag():
    assert core.probe(1500.0, [(1800.0, core.SLAB)], [(1550.0, core.SLAB)], 0.0).floor_found
    found = core.probe(1500.0, [(1800.0, core.SLAB)], [], 0.0)
    assert not found.floor_found
    assert not core.replace_slab(found, 3000.0).floor_found


def test_merge_collinear():
    pieces = [(0, 0, 1000, 0, 450), (900, 5, 2500, 5, -450), (2520, 0, 4000, 0, 450),
              (0, 3000, 1000, 3000, 450), (0, 0, 0, 1000, 450)]
    merged = core.merge_collinear(pieces)
    assert len(merged) == 3
    long_line = [m for m in merged if abs(m[1]) < 10 and abs(m[3]) < 10 and abs(m[2] - m[0]) > 3000][0]
    assert abs(min(long_line[0], long_line[2])) < 1e-6
    assert abs(max(long_line[0], long_line[2]) - 4000) < 1e-6
    assert abs(long_line[4]) == 450


def test_split_segment():
    assert len(core.split_segment((0, 0, 1000, 0, 1))) == 1
    parts = core.split_segment((0, 0, 9000, 0, 1))
    assert len(parts) == 3 and parts[0][2] == 3000 and parts[-1][2] == 9000
    assert len(core.split_segment((0, 0, 100000, 0, 1))) == 8


def test_polygons_and_interior_point():
    square = [(0, 0), (1000, 0), (1000, 1000), (0, 1000)]
    hole = [(400, 400), (600, 400), (600, 600), (400, 600)]
    assert core.polygon_area(square) == 1000000
    outer, holes = core.split_outer([hole, square])
    assert outer == square and holes == [hole]
    assert core.region_area(outer, holes) == 1000000 - 40000
    x, y = core.interior_point(outer, holes)
    assert core.point_in_polygon(x, y, square) and not core.point_in_polygon(x, y, hole)
    # Г-образный контур: центр тяжести снаружи — берётся узел сетки внутри
    l_shape = [(0, 0), (3000, 0), (3000, 300), (300, 300), (300, 3000), (0, 3000)]
    x, y = core.interior_point(l_shape, [])
    assert core.point_in_polygon(x, y, l_shape)


def test_loop_edges_and_typical_by_area():
    edges = core.loop_edges([[(0, 0), (10, 0), (10, 10)]], 3300)
    assert len(edges) == 3 and edges[-1] == (10, 10, 0, 0, 3300)
    assert core.typical_by_area([(4400, 500.0), (5050, 900.0), (4401, 600.0)], 10) == 4400
    assert core.typical_by_area([], 10) is None


def test_slab_and_ceiling_labels():
    assert core.slab_label(5050, 4400, 10, u"Пер. {h}", u"Δ {d}") == u"Пер. +5,050\nΔ +0,650"
    assert core.slab_label(4402, 4400, 10, u"Пер. {h}", u"Δ {d}") == u"Пер. +4,400"
    assert core.ceiling_label([2700.0, None], 10, u"ПП {h}") == u"ПП +2,700"
    assert core.ceiling_label([None], 10, u"ПП {h}") == u""
    words = core.split_words(u"лестнич, машиномест")
    assert core.has_word(u"Лестничная клетка Л1", words)
    assert core.has_word(u"Машиноместо 12", words)
    assert not core.has_word(u"Кладовая", words)


def test_lowest_face_at():
    slab = [(0, 0), (10000, 0), (10000, 10000), (0, 10000)]
    capital = [(4000, 4000), (6000, 4000), (6000, 6000), (4000, 6000)]
    upper = [(8000, 0), (20000, 0), (20000, 5000), (8000, 5000)]
    regions = [
        (-1200, slab, [capital], core.polygon_bbox(slab)),   # плита с вырезом под капитель
        (-1550, capital, [], core.polygon_bbox(capital)),
        (3000, upper, [], core.polygon_bbox(upper)),          # плита этажом выше
    ]
    assert core.lowest_face_at(5000, 5000, regions) == 1
    assert core.lowest_face_at(1000, 1000, regions) == 0
    assert core.lowest_face_at(9000, 1000, regions) == 0      # над плитой — нижняя
    assert core.lowest_face_at(15000, 1000, regions) == 2
    assert core.lowest_face_at(-5, -5, regions) is None


def test_interior_points_median_duplicates():
    square = [(0, 0), (1000, 0), (1000, 1000), (0, 1000)]
    points = core.interior_points(square, [], count=5)
    assert len(points) == 5 and points[0] == (500.0, 500.0)
    assert len(set(points)) == 5
    assert all(core.point_in_polygon(x, y, square) for x, y in points)
    assert core.median([3, None, 1, 2]) == 2
    assert core.median([1, 2, 3, 10]) == 2.5
    assert core.median([None]) is None
    box = (0, 0, 1000, 1000)
    faces = [(3400, box, 1e6), (3402, (10, 0, 1000, 1000), 1.005e6), (3400, (0, 0, 2000, 1000), 2e6),
             (3800, box, 1e6)]
    assert core.duplicate_faces(faces) == {1}
