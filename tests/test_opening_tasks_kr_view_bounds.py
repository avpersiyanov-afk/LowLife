# -*- coding: utf-8 -*-
"""Section crop must be calculated in the view frame, including rotated walls."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import pytest


def load_bounds():
    path=Path(__file__).parents[1]/'lib/lowlife/opening_tasks_kr_views.py'
    tree=ast.parse(path.read_text(encoding='utf-8'))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='projected_box')
    ns=dict(XYZ=lambda x,y,z:NS(X=x,Y=y,Z=z),BoundingBoxXYZ=lambda:NS(),tr=lambda ru,en=None:ru)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    return ns['projected_box']


def test_crop_uses_inverse_view_transform_and_padding():
    fn=load_bounds()
    frame=NS(Inverse=NS(OfPoint=lambda p:NS(X=p.Y-20,Y=p.Z-5,Z=-(p.X-10))))
    points=[NS(X=10,Y=20,Z=5),NS(X=12,Y=25,Z=9)]
    result=fn(points,frame,1)
    assert (result.Min.X,result.Min.Y,result.Min.Z)==(-1,-1,-3)
    assert (result.Max.X,result.Max.Y,result.Max.Z)==(6,5,1)
    assert result.Transform is frame


def test_empty_host_bounds_are_rejected():
    with pytest.raises(ValueError):
        load_bounds()([],NS(Inverse=NS(OfPoint=lambda p:p)),1)
