# -*- coding: utf-8 -*-
import ast
from pathlib import Path
from types import SimpleNamespace


class Axis:
    def __init__(self, value):
        self.value = value

    def DotProduct(self, other):
        return self.value * other.value


def helpers():
    source = Path(__file__).parents[1] / 'lib' / 'lowlife' / 'fire_boxes.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    names = {'_connector_axis', '_connector_axis_dot'}
    tree.body = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
    scope = {}
    exec(compile(tree, str(source), 'exec'), scope)
    return scope


def test_join_axis_falls_back_to_owner_curve_when_coordinate_system_is_unavailable():
    class BrokenConnector:
        @property
        def CoordinateSystem(self):
            raise Exception('Coordinate system is inaccessible.')

    connector = BrokenConnector()
    connector.Owner = SimpleNamespace(Location=SimpleNamespace(Curve=SimpleNamespace(Direction=Axis(1))))
    scope = helpers()
    assert scope['_connector_axis'](connector).value == 1
    assert scope['_connector_axis_dot'](connector, connector) == 1
