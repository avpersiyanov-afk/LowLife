# -*- coding: utf-8 -*-
"""Тесты для lowlife.fire_alarm_loops — построение дерева шлейфа СПС/СОУЭ
(включая ветви от изоляторов) и расчёт его длины. Требует Python 2
(build_route_text использует встроенную unicode())."""

import pytest

from lowlife import fire_alarm_loops as fal
from helpers import FakeXYZ


def test_manhattan_ft():
    assert fal.manhattan_ft(FakeXYZ(0, 0, 0), FakeXYZ(3, -4, 5)) == pytest.approx(12.0)


def test_build_loop_tree_linear_chain_sorts_by_index():
    nodes = [
        {"id": 3, "index": 3, "pt": FakeXYZ(2, 0, 0), "is_isolator": False},
        {"id": 1, "index": 1, "pt": FakeXYZ(0, 0, 0), "is_isolator": False},
        {"id": 2, "index": 2, "pt": FakeXYZ(1, 0, 0), "is_isolator": False},
    ]

    ordered = fal.build_loop_tree(nodes)

    assert [n["id"] for n in ordered] == [1, 2, 3]
    assert ordered[0]["parent_id"] is None
    assert ordered[1]["parent_id"] == 1
    assert ordered[2]["parent_id"] == 2


def _isolator_branch_nodes():
    # 1 -> 2(изолятор) -> 3 (продолжение магистрали)
    #             `-----> 4 (ветвь: физически ближе к изолятору 2, чем к
    #                        последнему по номеру устройству 3)
    return [
        {"id": 1, "index": 1, "pt": FakeXYZ(0, 0, 0), "is_isolator": False},
        {"id": 2, "index": 2, "pt": FakeXYZ(1, 0, 0), "is_isolator": True},
        {"id": 3, "index": 3, "pt": FakeXYZ(2, 0, 0), "is_isolator": False},
        {"id": 4, "index": 4, "pt": FakeXYZ(1, 5, 0), "is_isolator": False},
    ]


def test_build_loop_tree_branch_attaches_to_isolator_not_previous_device():
    ordered = fal.build_loop_tree(_isolator_branch_nodes())
    by_id = dict((n["id"], n) for n in ordered)

    assert by_id[2]["parent_id"] == 1
    assert by_id[3]["parent_id"] == 2
    assert by_id[4]["parent_id"] == 2  # не 3 — ветвь цепляется за изолятор


def test_calc_loop_length_ft_sums_tree_edges():
    ordered = fal.build_loop_tree(_isolator_branch_nodes())
    # рёбра: 1-2 (=1ft), 2-3 (=1ft), 2-4 (=5ft) => 7ft
    assert fal.calc_loop_length_ft(ordered) == pytest.approx(7.0)


def test_calc_loop_length_ft_includes_panel_segment():
    ordered = fal.build_loop_tree(_isolator_branch_nodes())
    panel_point = FakeXYZ(-1, 0, 0)
    # + участок панель -> первое устройство (id=1, на (0,0,0)) = 1ft
    assert fal.calc_loop_length_ft(ordered, panel_point) == pytest.approx(8.0)


def test_previous_address_by_id_reflects_branch_topology():
    ordered = fal.build_loop_tree(_isolator_branch_nodes())
    address_text_by_id = {
        1: u"ARK1.1.1",
        2: u"ARK1.1.2",
        3: u"ARK1.1.3",
        4: u"ARK1.1.4",
    }

    result = fal.previous_address_by_id(ordered, address_text_by_id)

    assert result[1] == u""
    assert result[2] == u"ARK1.1.1"
    assert result[3] == u"ARK1.1.2"
    assert result[4] == u"ARK1.1.2"  # не ARK1.1.3 — устройство 4 висит на изоляторе 2


def test_build_route_text_shows_branch_from_isolator():
    ordered = fal.build_loop_tree(_isolator_branch_nodes())
    address_text_by_id = {
        1: u"ARK1.1.1",
        2: u"ARK1.1.2",
        3: u"ARK1.1.3",
        4: u"ARK1.1.4",
    }

    text = fal.build_route_text(ordered, address_text_by_id)

    assert text == (
        u"ARK1.1.1; "
        u"ARK1.1.1 -> ARK1.1.2; "
        u"ARK1.1.2 -> ARK1.1.3; "
        u"ARK1.1.2 -> ARK1.1.4"
    )


def test_parse_route_edges_is_the_inverse_of_build_route_text():
    ordered = fal.build_loop_tree(_isolator_branch_nodes())
    address_text_by_id = {
        1: u"ARK1.1.1",
        2: u"ARK1.1.2",
        3: u"ARK1.1.3",
        4: u"ARK1.1.4",
    }

    text = fal.build_route_text(ordered, address_text_by_id)
    edges = fal.parse_route_edges(text)

    assert edges == [
        (None, u"ARK1.1.1"),
        (u"ARK1.1.1", u"ARK1.1.2"),
        (u"ARK1.1.2", u"ARK1.1.3"),
        (u"ARK1.1.2", u"ARK1.1.4"),
    ]


def test_parse_route_edges_empty_text():
    assert fal.parse_route_edges(u"") == []
    assert fal.parse_route_edges(None) == []


def _two_floor_nodes():
    return [
        {"id": 1, "index": 1, "pt": FakeXYZ(0, 0, 0), "is_isolator": False, "floor": u"Этаж 1"},
        {"id": 2, "index": 2, "pt": FakeXYZ(0, 0, 10), "is_isolator": False, "floor": u"Этаж 2"},
    ]


def test_calc_loop_length_ft_routes_through_riser_between_floors():
    ordered = fal.build_loop_tree(_two_floor_nodes())
    risers_by_floor = {
        u"Этаж 1": [{"id": 100, "pt": FakeXYZ(5, 0, 0)}],
        u"Этаж 2": [{"id": 101, "pt": FakeXYZ(5, 0, 10)}],
    }

    # 1 -> стояк(этаж 1) = 5ft, стояк(этаж 1) -> стояк(этаж 2) = 10ft,
    # стояк(этаж 2) -> 2 = 5ft => 20ft, а не прямые 10ft.
    length = fal.calc_loop_length_ft(ordered, risers_by_floor=risers_by_floor)
    assert length == pytest.approx(20.0)

    # Без risers_by_floor — как раньше, напрямую по катетам.
    assert fal.calc_loop_length_ft(ordered) == pytest.approx(10.0)


def test_calc_loop_length_ft_falls_back_to_direct_when_riser_missing_on_one_floor():
    ordered = fal.build_loop_tree(_two_floor_nodes())
    # Стояк есть только на этаже 1 — этажа 2 в словаре нет.
    risers_by_floor = {u"Этаж 1": [{"id": 100, "pt": FakeXYZ(5, 0, 0)}]}

    length = fal.calc_loop_length_ft(ordered, risers_by_floor=risers_by_floor)
    assert length == pytest.approx(10.0)


def test_calc_loop_length_ft_ring_loop_closes_to_panel_without_riser():
    ordered = fal.build_loop_tree(_isolator_branch_nodes())
    panel_point = FakeXYZ(-1, 0, 0)

    # Магистраль (без кольца, см. test_calc_loop_length_ft_includes_panel_segment) = 8ft.
    # + обратный участок: от узла 3 (последний узел МАГИСТРАЛИ, не узел 4 —
    # он на ветви изолятора) до панели = |2-(-1)| = 3ft => 11ft.
    length = fal.calc_loop_length_ft(ordered, panel_point, ring_loop=True)
    assert length == pytest.approx(11.0)


def test_calc_loop_length_ft_ring_loop_closes_to_riser_when_available():
    nodes = _isolator_branch_nodes()
    for n in nodes:
        n["floor"] = u"Этаж 1"
    ordered = fal.build_loop_tree(nodes)
    panel_point = FakeXYZ(-1, 0, 0)
    # panel_floor не передан (None) — участок панель->1 остаётся прямым,
    # риск участвует только в обратном участке кольца.
    risers_by_floor = {u"Этаж 1": [{"id": 100, "pt": FakeXYZ(2, 5, 0)}]}

    # 8ft (как раньше) + узел 3 (2,0,0) -> стояк (2,5,0) = 5ft => 13ft.
    length = fal.calc_loop_length_ft(
        ordered, panel_point, risers_by_floor=risers_by_floor, ring_loop=True
    )
    assert length == pytest.approx(13.0)
