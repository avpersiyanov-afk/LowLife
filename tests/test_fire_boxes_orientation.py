# -*- coding: utf-8 -*-
"""Adapter regression: never ask Revit to roll a horizontal tray."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace

import pytest
from lowlife import fire_boxes_core as core


class Vector:
    def __init__(self, values):
        self.X, self.Y, self.Z = values

    def __sub__(self, other):
        return Vector((self.X-other.X, self.Y-other.Y, self.Z-other.Z))

    def Normalize(self):
        return Vector(core.unit((self.X, self.Y, self.Z)))


def alignment(actual_up):
    source = Path(__file__).parents[1] / 'lib/lowlife/fire_boxes.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    tree.body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'align_tray_section']
    rotations = []
    db = SimpleNamespace(ElementTransformUtils=SimpleNamespace(RotateElement=lambda *args: rotations.append(args)),
                         Line=SimpleNamespace(CreateUnbound=lambda start, tangent: (start, tangent)))
    port = SimpleNamespace(CoordinateSystem=SimpleNamespace(BasisY=Vector(actual_up)))
    scope = {'core': core, 'DB': db, 'coords': lambda p: (p.X,p.Y,p.Z),
             'connectors': lambda el: [port], 'tr': lambda ru, en: en}
    exec(compile(tree, str(source), 'exec'), scope)
    return scope['align_tray_section'], rotations


def test_antiparallel_connector_does_not_rotate_horizontal_tray():
    align, rotations = alignment((0,0,-1))
    align(SimpleNamespace(Regenerate=lambda: None), SimpleNamespace(Id=1),
          Vector((0,0,0)), Vector((10,0,0)), (0,0,1))
    assert rotations == []


def test_real_horizontal_roll_is_rejected_before_revit_rotation():
    align, rotations = alignment((0,0,-1))
    with pytest.raises(ValueError, match='width horizontally'):
        align(SimpleNamespace(Regenerate=lambda: None), SimpleNamespace(Id=1),
              Vector((0,0,0)), Vector((10,0,0)), (0,1,0))
    assert rotations == []


def test_vertical_tray_can_still_rotate_to_match_section():
    align, rotations = alignment((1,0,0))
    align(SimpleNamespace(Regenerate=lambda: None), SimpleNamespace(Id=1),
          Vector((0,0,0)), Vector((0,0,10)), (0,1,0))
    assert len(rotations) == 1
    assert abs(rotations[0][-1]) == pytest.approx(math.pi/2)
