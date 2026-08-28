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
    # Отступ отсчитывается от НИЖНЕЙ ГРАНИЦЫ РАМКИ ПОМЕЩЕНИЯ
    # (level_y - ROOM_BOTTOM_MM), а не от level_y напрямую — иначе линия
    # попадает поверх/внутрь самой рамки помещения.
    y0 = scs_schematic.panel_collector_y(0, 100.0)
    expected = 100.0 - (
        scs_schematic.ROOM_BOTTOM_MM + scs_schematic.BOUNDARY_MARGIN_MM
    ) * scs_schematic.MM_TO_FT
    assert y0 == pytest.approx(expected)


def test_first_panel_collector_clears_the_room_frame_bottom_edge():
    # Сама граница рамки помещения (у СОТ/СКС) — level_y - ROOM_BOTTOM_MM;
    # первая линия кабеля должна быть строго дальше (ниже) неё, а не
    # выше/на ней (иначе линия рисуется поверх/внутри блока помещения).
    level_y = 100.0
    room_bottom_y = level_y - scs_schematic.ROOM_BOTTOM_MM * scs_schematic.MM_TO_FT
    y0 = scs_schematic.panel_collector_y(0, level_y)
    assert y0 < room_bottom_y


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


def test_trunk_drop_is_exactly_one_spacing_step_past_the_last_real_panel_collector():
    # panel_count реальных панелей занимают индексы 0..panel_count-1 —
    # отвод магистрали должен быть дальше от этажа, чем самый глубокий
    # из них, ровно на один обычный шаг BUS_DROP_SPACING_MM — без
    # отдельного увеличенного зазора: между всеми линиями кабелей на
    # этаже одно и то же расстояние (4мм), магистраль не исключение.
    panel_count = 3
    level_y = 100.0
    deepest_collector_y = scs_schematic.panel_collector_y(panel_count - 1, level_y)
    drop_y = scs_schematic.trunk_drop_y(panel_count, level_y)
    spacing_ft = scs_schematic.BUS_DROP_SPACING_MM * scs_schematic.MM_TO_FT
    assert deepest_collector_y - drop_y == pytest.approx(spacing_ft)


def test_trunk_drop_matches_virtual_next_panel_slot():
    panel_count = 2
    level_y = 100.0
    expected = scs_schematic.panel_collector_y(panel_count, level_y)
    assert scs_schematic.trunk_drop_y(panel_count, level_y) == pytest.approx(expected)


def test_trunk_lane_does_not_collide_with_any_panel_riser():
    panel_count = 3
    panel_xs = [scs_schematic.panel_riser_x(i) for i in range(panel_count)]

    lane0 = scs_schematic.trunk_lane_x(0, panel_count)
    lane1 = scs_schematic.trunk_lane_x(1, panel_count)

    assert lane0 not in panel_xs
    assert lane1 not in panel_xs
    assert lane0 != lane1
    # Дорожки магистралей — продолжение той же последовательности, левее
    # (дальше от рамок), чем любой стояк панели.
    assert lane0 < min(panel_xs)
    assert lane1 < lane0


def test_trunk_lane_is_exactly_boundary_margin_past_the_last_riser():
    # Зазор от последнего стояка до первой дорожки — то же число, что и
    # везде (BOUNDARY_MARGIN_MM), не отдельный увеличенный зазор.
    panel_count = 3
    last_riser_x = scs_schematic.panel_riser_x(panel_count - 1)
    lane0 = scs_schematic.trunk_lane_x(0, panel_count)
    margin_ft = scs_schematic.BOUNDARY_MARGIN_MM * scs_schematic.MM_TO_FT
    assert last_riser_x - lane0 == pytest.approx(margin_ft)


def test_first_riser_is_boundary_margin_short_of_the_level_frame_width():
    # Первый стояк не должен совпадать с самой правой линией рамки этажа
    # (LEVEL_FRAME_WIDTH_MM отсчитывает от левой границы содержимого
    # помещений, RISER_BASE_OFFSET_MM должен оставлять BOUNDARY_MARGIN_MM
    # запаса до неё же с внутренней стороны, а не сидеть прямо на ней).
    assert scs_schematic.RISER_BASE_OFFSET_MM > scs_schematic.BOUNDARY_MARGIN_MM


def test_group_trunk_components_merges_a_chain_sharing_a_panel():
    # A-B и B-C делят панель B -> одна цепочка из трёх панелей.
    components = scs_schematic.group_trunk_components([("A", "B"), ("B", "C")])
    assert len(components) == 1
    assert set(components[0]) == set(["A", "B", "C"])


def test_group_trunk_components_keeps_independent_pairs_separate():
    components = scs_schematic.group_trunk_components([("A", "B"), ("C", "D")])
    assert len(components) == 2
    groups = [set(c) for c in components]
    assert set(["A", "B"]) in groups
    assert set(["C", "D"]) in groups


def test_group_trunk_components_order_is_deterministic_by_first_appearance():
    # Порядок компонент/членов внутри них определяется порядком первого
    # появления панели в trunk_links — стабильно между запусками, пока
    # список магистралей не меняется.
    components = scs_schematic.group_trunk_components([("B", "C"), ("A", "B")])
    assert components == [["B", "C", "A"]]


def test_trunk_component_segments_two_member_chain():
    # Двухчленная цепочка — по сути та же пара, что раньше у
    # trunk_link_segments, но собрана через компонентный API.
    segments = scs_schematic.trunk_component_segments(
        [(-5.0, 10.0), (-13.0, 50.0)], lane_x=-40.0
    )
    assert len(segments) == 3
    seg_a, seg_b, seg_lane = segments
    assert seg_a == (-5.0, 10.0, -40.0, 10.0)
    assert seg_b == (-13.0, 50.0, -40.0, 50.0)
    assert seg_lane == (-40.0, 10.0, -40.0, 50.0)


def test_trunk_component_segments_three_member_chain_shares_one_lane_segment():
    # Три панели в одной цепочке -> три отвода до дорожки + ОДИН общий
    # вертикальный участок дорожки (не по одному на каждую пару).
    segments = scs_schematic.trunk_component_segments(
        [(-5.0, 10.0), (-13.0, 50.0), (-21.0, 30.0)], lane_x=-40.0
    )
    hops = segments[:-1]
    lane_segment = segments[-1]
    assert hops == [
        (-5.0, 10.0, -40.0, 10.0),
        (-13.0, 50.0, -40.0, 50.0),
        (-21.0, 30.0, -40.0, 30.0),
    ]
    # Вертикальный участок дорожки покрывает весь диапазон Y цепочки.
    assert lane_segment == (-40.0, 10.0, -40.0, 50.0)


def test_trunk_component_segments_skips_degenerate_hop():
    # Один из членов цепочки уже стоит ровно на дорожке -> его отвод
    # вырожден и не должен попасть в результат.
    segments = scs_schematic.trunk_component_segments(
        [(-40.0, 20.0), (-13.0, 20.0)], lane_x=-40.0
    )
    # x_a совпадает с lane_x -> первый отвод пропущен; y совпадают у
    # обоих членов -> общий вертикальный участок дорожки тоже вырожден.
    assert segments == [(-13.0, 20.0, -40.0, 20.0)]


def test_trunk_component_segments_single_member_has_no_lane_segment():
    # Один член (например второй участник связи не размещён на схеме) —
    # только отвод, вертикального участка дорожки быть не должно.
    segments = scs_schematic.trunk_component_segments([(-5.0, 10.0)], lane_x=-40.0)
    assert segments == [(-5.0, 10.0, -40.0, 10.0)]
