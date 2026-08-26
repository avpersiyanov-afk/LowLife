# -*- coding: utf-8 -*-
"""Тесты для lowlife.scs_addressing — классификация точек, Дейкстра/DFS,
выбор корней обхода. Логика используется RenumberAddresses (СКС) и, через
route_addressing.py, RenumberSkudAddresses (СКУД)."""

import pytest

from lowlife import scs_addressing as sa


def test_dist2():
    assert sa.dist2((0, 0), (3, 4)) == pytest.approx(5.0)


def test_matches_keywords_basic():
    assert sa.matches_keywords(u"Панель ШКАФ 1", [u"панель", u"шкаф"])
    assert not sa.matches_keywords(u"Розетка", [u"панель"])
    assert sa.matches_keywords(u"ПАНЕЛЬ", [u"панель"])  # регистронезависимо


def test_matches_keywords_exclude_wins():
    # exclude_keywords проверяются раньше include — совпадение по exclude
    # отсекает элемент, даже если он также подходит под keywords.
    assert not sa.matches_keywords(
        u"Панель управления", [u"панель"], [u"управления"]
    )


def test_point_to_segment_distance_xy_on_segment():
    dist, t = sa.point_to_segment_distance_xy((1, 1), (0, 0), (2, 2))
    assert dist == pytest.approx(0.0)
    assert t == pytest.approx(0.5)


def test_point_to_segment_distance_xy_beyond_endpoint_returns_raw_t():
    # t, который возвращает функция, НЕ клампится в [0,1] — это сырое
    # значение параметра вдоль прямой, используется вызывающим кодом
    # отдельно от расстояния (которое посчитано от клампнутой проекции).
    dist, t = sa.point_to_segment_distance_xy((3, 3), (0, 0), (1, 1))
    assert dist == pytest.approx(2 * (2 ** 0.5))
    assert t == pytest.approx(3.0)


def test_point_to_segment_distance_xy_degenerate_segment():
    dist, t = sa.point_to_segment_distance_xy((3, 4), (0, 0), (0, 0))
    assert dist == pytest.approx(5.0)
    assert t == pytest.approx(0.0)


def test_line_parameter_xy():
    assert sa.line_parameter_xy((1, 0), (0, 0), (2, 0)) == pytest.approx(0.5)


def test_line_parameter_xy_degenerate_segment():
    assert sa.line_parameter_xy((1, 1), (5, 5), (5, 5)) == pytest.approx(0.0)


def test_add_neighbor_is_bidirectional_and_idempotent():
    a = {"id": "a", "neighbor_ids": []}
    b = {"id": "b", "neighbor_ids": []}

    sa.add_neighbor(a, b, line_id="L1")
    sa.add_neighbor(a, b, line_id="L1")  # повторный вызов не плодит дублей

    assert a["neighbor_ids"] == ["b"]
    assert b["neighbor_ids"] == ["a"]
    assert a["neighbor_line_by_id"]["b"] == "L1"
    assert b["neighbor_line_by_id"]["a"] == "L1"


LINE = {"id": "L1", "p1": (0, 0), "p2": (10, 0)}
TOLS = dict(strict_tol=0.1, offset_tol=1.0, marked_tol=2.0, end_tol=0.5)


@pytest.mark.parametrize(
    "point,is_riser,is_panel,expected",
    [
        ((5, 0), False, False, "NODE_ON_LINE"),          # строго на линии, не у конца
        ((0.05, 0), False, False, "NODE_STRICT"),         # строго на линии и у конца
        ((0, 0.5), False, False, "NODE_NEAR_ENDPOINT"),   # рядом (offset_tol) и у конца
        ((5, 0.5), False, False, "OFFSET_MARKER"),        # рядом, но не у конца
        ((5, 5), False, False, "UNCONNECTED"),            # далеко
        ((5, 1.5), False, True, "OFFSET_MARKER"),         # панель в пределах marked_tol
        ((5, 5), False, True, "UNCONNECTED"),             # панель дальше marked_tol
    ],
)
def test_classify_point(point, is_riser, is_panel, expected):
    node = {"point": point, "is_riser": is_riser, "is_panel": is_panel}
    sa.classify_point(node, [LINE], **TOLS)
    assert node["classification"] == expected
    assert node["nearest_line_id"] == "L1"


def test_find_nearest_real_node():
    nodes = [
        {"id": "n1", "point": (0, 0)},
        {"id": "n2", "point": (10, 0)},
    ]
    source = {"point": (1, 0)}
    best, dist = sa.find_nearest_real_node(source, nodes)
    assert best["id"] == "n1"
    assert dist == pytest.approx(1.0)


def test_build_shortest_path_tree_reaches_disconnected_component_as_local_root():
    nodes_by_id = {
        "A": {"id": "A", "point": (0, 0), "neighbor_ids": ["B"]},
        "B": {"id": "B", "point": (1, 0), "neighbor_ids": ["A", "C"]},
        "C": {"id": "C", "point": (2, 0), "neighbor_ids": ["B"]},
        "D": {"id": "D", "point": (10, 10), "neighbor_ids": []},  # отдельная компонента
    }
    roots = [nodes_by_id["A"]]
    all_nodes = list(nodes_by_id.values())

    visited, effective_roots = sa.build_shortest_path_tree(nodes_by_id, roots, all_nodes)

    assert visited == set(["A", "B", "C", "D"])
    assert nodes_by_id["B"]["parent_id"] == "A"
    assert nodes_by_id["C"]["parent_id"] == "B"
    assert nodes_by_id["D"].get("parent_id") is None
    assert set(r["id"] for r in effective_roots) == set(["A", "D"])


def test_depth_first_order_finishes_branch_before_next_sibling():
    # R
    # |-- P1 (visited first: меньшие координаты идут раньше)
    # |    `-- P1a
    # `-- P2
    nodes_by_id = {
        "R": {"id": "R", "point": (0, 0)},
        "P1": {"id": "P1", "point": (0, 1), "parent_id": "R"},
        "P2": {"id": "P2", "point": (0, 2), "parent_id": "R"},
        "P1a": {"id": "P1a", "point": (0, 1.5), "parent_id": "P1"},
    }
    order = sa.depth_first_order(nodes_by_id, [nodes_by_id["R"]])
    assert [n["id"] for n in order] == ["R", "P1", "P1a", "P2"]


def test_select_root_sources_prefers_near_panels():
    real_nodes = [{"id": "n1", "point": (0, 0)}, {"id": "n2", "point": (10, 0)}]
    near_panel = {"id": "p1", "point": (5, 0)}

    roots, far, fallback = sa.select_root_sources([near_panel], [], real_nodes, margin=1)

    assert roots == [near_panel]
    assert far == []
    assert fallback == []


def test_select_root_sources_falls_back_to_risers_when_panels_are_far():
    real_nodes = [{"id": "n1", "point": (0, 0)}, {"id": "n2", "point": (10, 0)}]
    far_panel = {"id": "p1", "point": (100, 100)}
    near_riser = {"id": "r1", "point": (5, 0.5)}

    roots, far, fallback = sa.select_root_sources([far_panel], [near_riser], real_nodes, margin=1)

    assert roots == [near_riser]
    assert far == [far_panel]
    assert fallback == []


def test_select_root_sources_returns_near_risers_as_fallback_when_panel_present():
    # Баг: этаж с панелью и двумя стояками, где один стояк ведёт по СВОЕЙ,
    # физически не связанной с сетью панели ветке. near_riser не должен
    # пропадать совсем — он идёт третьим элементом (fallback), а не в
    # основные roots (иначе Дейкстра могла бы разорвать единую сеть,
    # где стояк просто стоит на уже связанной с панелью линии).
    real_nodes = [{"id": "n1", "point": (0, 0)}]
    near_panel = {"id": "p1", "point": (1, 0)}
    near_riser = {"id": "r1", "point": (2, 0)}

    roots, far, fallback = sa.select_root_sources([near_panel], [near_riser], real_nodes, margin=5)

    assert roots == [near_panel]
    assert far == []
    assert fallback == [near_riser]


def test_build_shortest_path_tree_fallback_root_rescues_disconnected_branch():
    # На этаже панель (корень A) и отдельная, физически НЕ связанная линиями
    # ветка D-E, у которой есть свой стояк — E должен присоединиться к
    # стояку (fallback-корню), а не остаться безымянным "локальным корнем"
    # (что и было багом: устройства через D/E не находили путь до панели).
    nodes_by_id = {
        "A": {"id": "A", "point": (0, 0), "neighbor_ids": ["B"]},
        "B": {"id": "B", "point": (1, 0), "neighbor_ids": ["A"]},
        "D": {"id": "D", "point": (10, 0), "neighbor_ids": ["E"]},
        "E": {"id": "E", "point": (11, 0), "neighbor_ids": ["D"]},
    }
    roots = [nodes_by_id["A"]]
    fallback_roots = [nodes_by_id["E"]]
    all_nodes = list(nodes_by_id.values())

    visited, effective_roots = sa.build_shortest_path_tree(
        nodes_by_id, roots, all_nodes, fallback_roots=fallback_roots
    )

    assert visited == set(["A", "B", "D", "E"])
    assert nodes_by_id["B"]["parent_id"] == "A"
    assert nodes_by_id["D"]["parent_id"] == "E"
    assert nodes_by_id["E"].get("parent_id") is None
    assert set(r["id"] for r in effective_roots) == set(["A", "E"])


def test_build_shortest_path_tree_fallback_root_not_used_when_component_already_reached():
    # Стояк C стоит НА уже связанной с панелью A линии (A-B-C) — обычный
    # промежуточный узел, а не отдельная ветка. fallback-корень не должен
    # "перетягивать" на себя уже достижимые узлы и разрывать дерево: C
    # остаётся ребёнком B, а не отдельным корнем.
    nodes_by_id = {
        "A": {"id": "A", "point": (0, 0), "neighbor_ids": ["B"]},
        "B": {"id": "B", "point": (1, 0), "neighbor_ids": ["A", "C"]},
        "C": {"id": "C", "point": (2, 0), "neighbor_ids": ["B"]},
    }
    roots = [nodes_by_id["A"]]
    fallback_roots = [nodes_by_id["C"]]
    all_nodes = list(nodes_by_id.values())

    visited, effective_roots = sa.build_shortest_path_tree(
        nodes_by_id, roots, all_nodes, fallback_roots=fallback_roots
    )

    assert nodes_by_id["B"]["parent_id"] == "A"
    assert nodes_by_id["C"]["parent_id"] == "B"
    assert set(r["id"] for r in effective_roots) == set(["A"])


def test_attach_roots_skips_real_node_already_claimed():
    real_nodes = [
        {"id": "n1", "point": (0, 0), "parent_id": None},
        {"id": "n2", "point": (10, 0), "parent_id": None},
    ]
    panel = {"id": "p1", "point": (0.1, 0)}
    riser = {"id": "r1", "point": (0.2, 0)}  # тоже ближе всего к n1

    primary = sa.attach_roots([panel], {}, real_nodes, offset_tol=0.5)
    fallback = sa.attach_roots([riser], {}, real_nodes, offset_tol=0.5)

    assert [n["id"] for n in primary] == ["n1"]
    assert real_nodes[0]["parent_id"] == "p1"
    assert fallback == []  # n1 уже занят панелью, riser не получает корня
