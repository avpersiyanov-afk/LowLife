# -*- coding: utf-8 -*-
"""Adapter checks with a tiny connector API substitute (no Revit installed)."""
import ast
import math
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
    tree=ast.parse(path.read_text(encoding='utf-8'))
    body=[n for n in tree.body if isinstance(n,(ast.Assign,ast.FunctionDef,ast.ClassDef))]
    bic=NS(OST_CableTray=1,OST_DuctCurves=2,OST_PipeCurves=3,OST_Conduit=4)
    calls=[]
    def insulation(doc,eid):
        calls.append(eid)
        return ['insulation']
    ns=dict(ISelectionFilter=object,math=math,tr=lambda ru,en=None:ru,BuiltInCategory=bic,ConnectorProfileType=NS(Round=1,Rectangular=2,Oval=3),
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


def test_rolled_section_keeps_its_frame_and_fittings_are_rejected(adapter):
    Route,_=adapter
    assert Route(element(2,roll=.5)).section_x==(0,1,.5)
    with pytest.raises(ValueError):
        Route(element(99))
    el=element();el.Location=NS(Curve=Line())
    with pytest.raises(ValueError):
        Route(el)


def test_selection_filter_accepts_inclined_routes_and_rejects_wrong_categories(adapter):
    # Load the filter with the same substitute API used by adapter tests.
    import ast
    path=Path(__file__).parents[1]/'lib/lowlife/opening_tasks_mep.py'
    tree=ast.parse(path.read_text(encoding='utf-8'))
    fn=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='RouteSelectionFilter')
    Route,calls=adapter
    ns=dict(ISelectionFilter=object,math=math,Route=Route,boxes=NS(_id_int=lambda v:v),
            supported=lambda el:el.Category.Id in (1,2,3,4))
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    Filter=ns['RouteSelectionFilter']
    f=Filter(dict(box_hosts='walls',max_slope_deg=1))
    assert f.AllowElement(element(1))
    assert not f.AllowElement(element(99))
    assert not f.AllowReference(None,None)
    tilted=element();tilted.Id='tilted'
    tilted.Location=LocationCurve();tilted.Location.Curve=Line()
    tilted.Location.Curve.Direction=Vector(math.sqrt(.5),0,math.sqrt(.5))
    tilted.ConnectorManager.Connectors[0].CoordinateSystem.BasisZ=tilted.Location.Curve.Direction
    assert f.AllowElement(tilted)
    floor_only=Filter(dict(box_hosts='floors',max_slope_deg=1))
    assert not floor_only.AllowElement(element(1))
    assert floor_only.AllowElement(tilted)
