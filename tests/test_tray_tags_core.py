# -*- coding: utf-8 -*-
"""Тесты для lowlife.tray_tags_core — геометрия лотка на виде для кнопки
«Марки лотков» (Tools.panel/TagTrays)."""

from lowlife.tray_tags_core import (slope_deg, is_sloped, clip_segment, anchor_rect,
                                    strip_pieces, strip_exit, strip_rect, stagger_anchors,
                                    lerp)
from lowlife.tag_layout import TagItem, layout, count_conflicts


def _close(a, b, tol=1e-9):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def test_slope_horizontal_sloped_vertical():
    assert slope_deg((0, 0, 3), (10, 0, 3)) == 0.0
    assert abs(slope_deg((0, 0, 0), (10, 0, 10)) - 45.0) < 1e-9
    assert slope_deg((0, 0, 0), (0, 0, 5)) == 90.0
    assert not is_sloped((0, 0, 3), (10, 0, 3.0001), 0.5)
    assert is_sloped((0, 0, 0), (10, 0, 1), 0.5)
    assert is_sloped((1, 1, 0), (1, 1, 5), 0.5)


def test_clip_segment():
    assert clip_segment((-5, 0), (5, 0), (0, -1, 10, 1)) == (0.5, 1.0)
    assert clip_segment((-5, 5), (5, 5), (0, -1, 10, 1)) is None
    assert clip_segment((2, 0), (3, 0), (0, -1, 10, 1)) == (0.0, 1.0)


def test_anchor_rect_is_piece_at_middle():
    r = anchor_rect((0, 0), (100, 0), 1.0, 1.0)
    assert _close(r, (49, -1, 51, 1))
    # короткий лоток — не длиннее себя
    r = anchor_rect((0, 0), (1, 0), 2.0, 0.0)
    assert _close(r, (0, -2, 1, 2))


def test_strip_pieces_cover_diagonal_without_one_huge_box():
    pieces = strip_pieces((0, 0), (100, 100), 1.0)
    assert 1 < len(pieces) <= 40
    big = strip_rect((0, 0), (100, 100), 1.0)
    area = (big[2] - big[0]) * (big[3] - big[1])
    assert sum((p[2] - p[0]) * (p[3] - p[1]) for p in pieces) < area * 0.2


def test_strip_exit_on_tray_edge():
    # горизонтальный лоток шириной 2, выноска вертикально вверх
    assert _close(strip_exit((5, 0), (5, 10), (0, 0), (10, 0), 1.0), (5, 1))
    # косой лоток 45°, выноска вверх: край — на расстоянии 1 по нормали
    e = strip_exit((5, 5), (5, 20), (0, 0), (10, 10), 1.0)
    assert abs(e[0] - 5) < 1e-9 and abs(e[1] - (5 + 2 ** 0.5)) < 1e-9
    # излом внутри полосы — конец остаётся в середине
    assert strip_exit((5, 0), (6, 0.5), (0, 0), (10, 0), 1.0) == (5, 0)


def _lay(strips, half_w=0.5):
    ts, groups = stagger_anchors(strips, 3.0, 1.2)
    items, obstacles = [], []
    for key, a, b in strips:
        items.append(TagItem(key, lerp(a, b, ts[key]), anchor_rect(a, b, half_w, 0.5, ts[key]),
                             (4.0, 1.2), group=groups[key]))
        obstacles.extend(strip_pieces(a, b, half_w))
    pl = layout(items, obstacles, offset=1.2, gap=0.25, shelf=0.8, cluster_dist=3.0,
                start_at_edge=False)
    assert count_conflicts(pl, items) == (0, 0)
    return pl


def test_stagger_spreads_parallel_trays_along_route():
    ts, groups = stagger_anchors([(0, (0, 0), (40, 0)), (1, (40, 2), (0, 2)),
                                  (2, (0, 30), (40, 30))], 3.0, 1.2)
    assert ts[2] == 0.5 and groups[2] is None
    assert groups[0] == groups[1] is not None
    # точки марок разошлись вдоль трассы (ось лотка 1 развёрнута)
    u0, u1 = 40 * ts[0], 40 * (1 - ts[1])
    assert abs(u0 - u1) >= 2.0


def test_horizontal_parallel_trays_get_one_aligned_stack():
    pl = _lay([(i, (0.0, y), (40.0, y)) for i, y in enumerate((0.0, 2.0, 4.0))])
    assert len(set(round(p.tag_rect[0], 6) for p in pl)) == 1
    assert min(p.tag_rect[1] for p in pl) > 4.0          # над трассой
    for p in pl:
        assert abs(p.end[0] - p.elbow[0]) < 1e-9          # вертикаль от лотка


def test_vertical_parallel_trays_get_one_aligned_column():
    pl = _lay([(i, (x, 0.0), (x, 40.0)) for i, x in enumerate((0.0, 2.0, 4.0))])
    assert len(set(round(p.tag_rect[0], 6) for p in pl)) == 1
    for p in pl:
        assert abs(p.end[1] - p.elbow[1]) < 1e-9          # горизонталь от лотка
