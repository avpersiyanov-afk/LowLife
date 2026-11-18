# -*- coding: utf-8 -*-
"""Regression tests for merging selected parallel tray runs."""
import ast
from pathlib import Path
from types import SimpleNamespace

from lowlife import fire_boxes_core as core


class Point:
    def __init__(self, x, y, z=0):
        self.X, self.Y, self.Z = x, y, z


def _curve(start, end):
    line = SimpleNamespace(GetEndPoint=lambda index: (start, end)[index])
    return SimpleNamespace(Location=SimpleNamespace(Curve=line))


def _parallel_groups(components, curves):
    source = Path(__file__).parents[1] / 'lib/lowlife/fire_boxes.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    tree.body = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name == '_parallel_component_groups']
    scope = dict(core=core, coords=lambda point: (point.X, point.Y, point.Z),
                 _curve_components=lambda _curves, _fittings: components)
    exec(compile(tree, str(source), 'exec'), scope)
    return scope['_parallel_component_groups'](curves, {})


def test_parallel_runs_with_fittings_are_merged_into_one_group():
    curves = {
        1: _curve(Point(0, 0), Point(5, 0)),
        2: _curve(Point(5, 0), Point(10, 0)),
        3: _curve(Point(5, 5), Point(10, 5)),
        4: _curve(Point(10, 5), Point(15, 5)),
        5: _curve(Point(12, 10), Point(20, 10)),
    }
    groups = _parallel_groups([[1, 2], [3, 4], [5]], curves)
    assert len(groups) == 1
    assert set(groups[0]) == set(curves)


def test_bent_component_is_left_for_regular_route_creation():
    curves = {
        1: _curve(Point(0, 0), Point(10, 0)),
        2: _curve(Point(10, 0), Point(10, 5)),
        3: _curve(Point(0, 5), Point(10, 5)),
    }
    assert _parallel_groups([[1, 2], [3]], curves) == [[3]]
