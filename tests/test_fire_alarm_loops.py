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
