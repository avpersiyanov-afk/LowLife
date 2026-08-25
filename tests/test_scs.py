# -*- coding: utf-8 -*-
"""Тесты для lowlife.scs.merge_nodes — кластеризация узлов трассы по
близости при расстановке маркеров (PlaceRouteNodes/route_nodes.py).

Остальной scs.py (classify_element, get_workset_name, ...) использует
Autodesk.Revit.DB внутри тела функций и вне Revit не тестируется (см.
tests/README.md) — merge_nodes/_pick_cluster_point этого не делают,
работают с обычными dict/точками, поэтому проверяются здесь напрямую."""

import random

import pytest

from lowlife import scs
from helpers import FakeXYZ


def points_close(p1, p2, tol):
    return p1.DistanceTo(p2) <= tol


def _node(x, y, z=0.0, **extra):
    data = {
        "point": FakeXYZ(x, y, z),
        "node_key": None,
        "source_type": "graph_node",
        "category": "route",
        "segment_ids": [],
        "device": None
    }
    data.update(extra)
    return data


def test_merge_nodes_merges_two_close_points():
    nodes = [_node(0, 0), _node(0.05, 0)]
    result = scs.merge_nodes(nodes, 0.1, points_close)
    assert len(result) == 1
    assert len(result[0]["source_types"]) == 2


def test_merge_nodes_keeps_far_points_separate():
    nodes = [_node(0, 0), _node(1, 0)]
    result = scs.merge_nodes(nodes, 0.1, points_close)
    assert len(result) == 2


def test_merge_nodes_transitive_chain_merges_into_one_cluster():
    # A-B ближе tol, B-C ближе tol, но A-C дальше tol — раньше (сравнение
    # только с первым узлом кластера) B и C могли оказаться в разных
    # кластерах, если C сравнивался с A, а не с B. Транзитивно это один
    # физический узел (стык/пересечение с небольшим разбросом координат).
    tol = 0.06
    a = _node(0.00, 0)
    b = _node(0.05, 0)
    c = _node(0.10, 0)

    assert points_close(a["point"], b["point"], tol)
    assert points_close(b["point"], c["point"], tol)
    assert not points_close(a["point"], c["point"], tol)

    result = scs.merge_nodes([a, b, c], tol, points_close)

    assert len(result) == 1
    assert len(result[0]["source_types"]) == 3


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_merge_nodes_chain_result_is_order_independent(seed):
    tol = 0.06
    nodes = [_node(0.00, 0), _node(0.05, 0), _node(0.10, 0)]

    rng = random.Random(seed)
    shuffled = list(nodes)
    rng.shuffle(shuffled)

    result = scs.merge_nodes(shuffled, tol, points_close)

    assert len(result) == 1
    assert len(result[0]["source_types"]) == 3


def test_merge_nodes_aggregates_segment_ids_and_device():
    marked = _node(0, 0, device={"element": "riser_el"}, category="riser", segment_ids=[1])
    plain = _node(0.02, 0, segment_ids=[1, 2])

    result = scs.merge_nodes([marked, plain], 0.1, points_close)

    assert len(result) == 1
    cluster = result[0]
    assert cluster["device"] == {"element": "riser_el"}
    assert sorted(cluster["segment_ids"]) == [1, 2]


def test_merge_nodes_snaps_to_existing_point_within_tolerance():
    existing = FakeXYZ(10, 10, 0)
    nodes = [_node(10.02, 10, device={"element": "dev"})]

    result = scs.merge_nodes(nodes, 0.1, points_close, existing_points=[existing])

    assert result[0]["point"] is existing
