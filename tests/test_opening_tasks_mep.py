# -*- coding: utf-8 -*-
"""Adapter checks with a tiny connector API substitute (no Revit installed)."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import pytest


class Vector:
    def __init__(self, x=0,y=0,z=0):
        self.X,self.Y,self.Z=x,y,z
    def DotProduct(self,other):
        return self.X*other.X+self.Y*other.Y+self.Z*other.Z


class Line:
    Direction=Vector(1,0,0)


class LocationCurve:
    Curve=Line()


@pytest.fixture
def adapter():
    path=Path(__file__).parents[1]/'lib/lowlife/opening_tasks_mep.py'
    tree=ast.parse(path.read_text())
    body=[n for n in tree.body if isinstance(n,(ast.Assign,ast.FunctionDef,ast.ClassDef))]
    bic=NS(OST_CableTray=1,OST_DuctCurves=2,OST_PipeCurves=3,OST_Conduit=4)
    calls=[]
    def insulation(doc,eid):
        calls.append(eid)
        return ['insulation']
    ns=dict(tr=lambda ru,en=None:ru,BuiltInCategory=bic,ConnectorProfileType=NS(Round=1,Rectangular=2,Oval=3),
            InsulationLiningBase=NS(GetInsulationIds=insulation),Line=Line,LocationCurve=LocationCurve,
            boxes=NS(_id_int=lambda v:v))
    exec(compile(ast.Module(body=body,type_ignores=[]),str(path),'exec'),ns)
    return ns['Route'],calls


def element(category=1,shape=2,roll=0):
    c=NS(Shape=shape,Radius=50,Width=300,Height=100,
         CoordinateSystem=NS(BasisZ=Vector(1,0,0),BasisX=Vector(0,1,roll)))
    return NS(Category=NS(Id=category),Location=LocationCurve(),Id='route',
              ConnectorManager=NS(Connectors=[c]),Document=NS(GetElement=lambda eid:NS(Thickness=10)))


@pytest.mark.parametrize('category',[1,4])
def test_tray_and_conduit_do_not_query_unsupported_insulation_api(adapter,category):
    Route,calls=adapter
    route=Route(element(category))
    assert (route.Width,route.Height)==(300,100)
    assert not calls


@pytest.mark.parametrize('category',[2,3])
def test_round_pipe_duct_envelope_includes_insulation_on_each_side(adapter,category):
    Route,calls=adapter
    route=Route(element(category,shape=1))
    assert (route.Width,route.Height)==(120,120)
    assert calls==['route']


def test_rectangular_duct_envelope_includes_insulation(adapter):
    Route,_=adapter
    route=Route(element(2))
    assert (route.Width,route.Height)==(320,120)


def test_rolled_and_fitting_routes_are_explicitly_rejected(adapter):
    Route,_=adapter
    with pytest.raises(ValueError):
        Route(element(2,roll=.5))
    with pytest.raises(ValueError):
        Route(element(99))
    el=element();el.Location=NS(Curve=Line())
    with pytest.raises(ValueError):
        Route(el)
