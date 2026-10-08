# -*- coding: utf-8 -*-
"""Тесты для lowlife.tag_layout — раскладка марок оборудования без
пересечений (кнопка «Марки оборудования», Tools.panel/TagEquipment)."""

from lowlife.tag_layout import TagItem, layout, count_conflicts, rect_overlap_area, exit_point


def _box(key, x, y, s=1.0, tw=4.0, th=1.2):
    return TagItem(key, (x, y), (x - s / 2.0, y - s / 2.0, x + s / 2.0, y + s / 2.0), (tw, th))


PARAMS = dict(offset=1.2, gap=0.25, shelf=0.8, cluster_dist=1.5)


def _clean(items, obstacles=None):
    pl = layout(items, obstacles, **PARAMS)
    assert len(pl) == len(items)
    assert count_conflicts(pl, items) == (0, 0)
    return pl


def test_pair_side_by_side_is_stacked_above_with_square_leaders():
    a, b = _clean([_box(1, 0, 0), _box(2, 1.6, 0)])
    assert abs(a.tag_rect[0] - b.tag_rect[0]) < 1e-9
    assert min(a.tag_rect[1], b.tag_rect[1]) > 0.5
    for p in (a, b):
        assert abs(p.end[0] - p.elbow[0]) < 1e-9     # вертикаль от элемента
        assert abs(p.end[1] - 0.5) < 1e-9            # ...от верхнего края УГО
        assert abs(p.elbow[1] - p.attach[1]) < 1e-9  # горизонтальная полка


def test_vertical_column_gets_tags_at_one_offset():
    pl = _clean([_box(i, 0, i * 1.3) for i in range(6)])
    assert len(set(round(p.tag_rect[0], 9) for p in pl)) == 1


def test_mixed_scene_and_grid_have_no_conflicts():
    _clean([_box('a', 0, 0), _box('b', 1.5, 0.2), _box('c', 3.0, -0.1),
            _box('d', 10, 0), _box('e', 10, 1.5), _box('f', 10.3, 3),
            _box('g', 10, 4.5), _box('h', 5, 6), _box('i', 20, 0)])
    _clean([_box((i, j), i * 2.2, j * 2.2) for i in range(4) for j in range(3)])


def test_tag_avoids_obstacle():
    obstacle = (0.0, 0.5, 10.0, 5.0)  # над-справа всё занято
    p, = _clean([_box(1, 0, 0)], [obstacle])
    assert rect_overlap_area(p.tag_rect, obstacle) == 0


def test_leader_starts_at_symbol_edge():
    r = (-1.0, -1.0, 1.0, 1.0)
    assert exit_point((0.0, 0.0), (0.0, 5.0), r) == (0.0, 1.0)
    assert exit_point((0.0, 0.0), (4.0, 2.0), r) == (1.0, 0.5)
    assert exit_point((0.0, 0.0), (0.5, 0.5), r) == (0.0, 0.0)   # излом внутри — не трогаем
    assert exit_point((3.0, 3.0), (5.0, 5.0), r) == (3.0, 3.0)   # старт снаружи


def test_side_column_leaders_start_on_symbol_edge():
    items = [_box(i, 0, i * 1.3) for i in range(4)]
    for it, p in zip(items, layout(items, **PARAMS)):
        r = it.elem_rect
        on_edge = (abs(p.end[0] - r[0]) < 1e-9 or abs(p.end[0] - r[2]) < 1e-9 or
                   abs(p.end[1] - r[1]) < 1e-9 or abs(p.end[1] - r[3]) < 1e-9)
        assert on_edge


def test_dense_column_splits_to_both_sides_without_steep_leaders():
    # элементы чаще, чем высота марки: одна колонка дала бы «веер»
    items = [_box(i, 0, i * 0.9) for i in range(12)]
    pl = _clean(items)
    assert any(p.tag_rect[0] > 0 for p in pl) and any(p.tag_rect[2] < 0 for p in pl)
    for p in pl:
        du = abs(p.elbow[0] - p.end[0])
        dv = abs(p.elbow[1] - p.end[1])
        assert dv <= du + 1e-9


def test_dense_grid_has_no_conflicts_and_square_outer_rows():
    # сетка 5×5 вплотную (марка шире шага сетки): раньше средние ряды
    # давали пересечения и «веер» наклонных выносок через всю сетку
    items = [TagItem((i, j), (i * 8.0, j * 8.0),
                     (i * 8.0 - 2, j * 8.0 - 2, i * 8.0 + 2, j * 8.0 + 2), (15.0, 3.5))
             for i in range(5) for j in range(5)]
    pl = layout(items, offset=3.0, gap=1.0, shelf=3.0, cluster_dist=8.0)
    assert count_conflicts(pl, items) == (0, 0)
    for it, p in zip(items, pl):
        if it.key[1] in (0, 4):  # верхний/нижний ряд — наружу, вертикаль + полка
            assert abs(p.end[0] - p.elbow[0]) < 1e-9
            assert abs(p.elbow[1] - p.attach[1]) < 1e-9
        for a, b in p.leader_segments():
            assert abs(b[1] - a[1]) <= abs(b[0] - a[0]) + 1e-9 or abs(b[0] - a[0]) < 1e-9
