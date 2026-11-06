# -*- coding: utf-8 -*-
"""Snapshot coordinates are converted exactly once, into the target link frame."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from lowlife import opening_tasks_core as core


class XYZ:
    def __init__(self,x,y,z):
        self.X,self.Y,self.Z=x,y,z
    def Add(self,p):
        return XYZ(self.X+p.X,self.Y+p.Y,self.Z+p.Z)


XYZ.BasisZ=XYZ(0,0,1)


def geometry_reader():
    path=Path(__file__).parents[1]/'lib/lowlife/opening_tasks_revit.py'
    tree=ast.parse(path.read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='host_geometry')
    ns=dict(tr=lambda ru,en=None:ru,XYZ=XYZ,math=math,core=core,
            boxes=NS(_t=lambda v:(v.X,v.Y,v.Z),mm=lambda v:v*304.8),
            read_size=lambda inst,name:inst.sizes[name])
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    return ns['host_geometry']


class Inverse:
    def __init__(self,tilt=False):
        self.tilt=tilt
    def OfPoint(self,p):
        # Target link was translated (10,20) and rotated +90 degrees in VIS.
        return XYZ(p.Y-20,-(p.X-10),p.Z)
    def OfVector(self,p):
        return XYZ(p.Y,-p.X,p.Z) if not self.tilt else XYZ(p.X,p.Z,p.Y)


def test_bottom_origin_and_rotated_link_snapshot():
    read=geometry_reader()
    data=dict(origin_bottom=True,kind='wall',size_params=['w','d','h'],host_uid='wall',host_model='kr')
    inst=NS(sizes=dict(w=2,d=1,h=1),Location=NS(Point=XYZ(12,23,5),Rotation=math.pi/2))
    link=NS(GetTotalTransform=lambda:NS(Inverse=Inverse()))
    g=read(inst,data,link)
    assert g['center_mm']==pytest.approx([3*304.8,-2*304.8,5.5*304.8])
    assert g['x_dir']==pytest.approx([1,0,0],abs=1e-8)
    assert g['size_mm']==pytest.approx([609.6,304.8,304.8])
    assert g['host_uid']=='wall' and g['host_model']=='kr'
    data['origin_bottom']=False
    assert read(inst,data,link)['center_mm'][2]==pytest.approx(5*304.8)


def test_tilted_link_cannot_publish_a_wrong_horizontal_opening():
    read=geometry_reader()
    data=dict(origin_bottom=False,kind='wall',size_params=['w','d','h'],host_uid='wall',host_model='kr')
    inst=NS(sizes=dict(w=2,d=1,h=1),Location=NS(Point=XYZ(12,23,5),Rotation=0))
    with pytest.raises(ValueError):
        read(inst,data,NS(GetTotalTransform=lambda:NS(Inverse=Inverse(True))))
