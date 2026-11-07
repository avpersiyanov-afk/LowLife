"""Exercise additive SlabProbe API without importing Revit."""
import ast
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from lowlife import slab_marks_core as core


PATH=Path(__file__).parents[1]/'lib/lowlife/slab_marks.py'


def method(name,ns):
    tree=ast.parse(PATH.read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='SlabProbe')
    node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(PATH),'exec'),ns)
    return ns[name]


def test_existing_constructor_defaults_are_unchanged():
    init=method('__init__',dict(PROBE_DOWN_MM=30000,ft=lambda v:v/304.8))
    obj=NS()
    init(obj,'doc')
    assert obj._source_override is None and obj._category_override is None
    assert obj.down_range_mm==30000 and obj.opening_ft==0
    scoped=NS()
    init(scoped,'doc',sources={7:'AR'},categories=[1],down_range_mm=None)
    assert scoped._source_override=={7:'AR'} and scoped._category_override==[1]
    assert scoped.down_range_mm is None


def test_open_queries_only_explicit_sources_and_categories(monkeypatch):
    class GenericList:
        def __class_getitem__(cls,item):return list
    monkeypatch.setitem(sys.modules,'System.Collections.Generic',NS(List=GenericList))
    monkeypatch.setitem(sys.modules,'Autodesk.Revit.DB',NS(ElementMulticategoryFilter=lambda cats:cats))
    point=lambda x,y,z:NS(X=x,Y=y,Z=z)
    floor=NS(Id=NS(IntegerValue=42),get_BoundingBox=lambda view:NS(Min=point(0,0,0),Max=point(10,10,1)))
    selected_doc=object()
    queried=[]
    class Collector:
        def __init__(self,doc):
            queried.append(doc)
        def WherePasses(self,filter):
            assert filter==[1]
            return self
        def WhereElementIsNotElementType(self):return [floor]
    def forbidden(doc):
        raise AssertionError('Unselected model/link enumeration is forbidden')
    ns=dict(core=core,GRID_CELL_MM=5000,XYZ=point,mm=lambda v:v*304.8,
            BuiltInCategory=NS(OST_Floors=1,OST_Roofs=2,OST_Ceilings=3),
            FilteredElementCollector=Collector,model_sources=forbidden,_source_labels=forbidden,
            tr=lambda text:text)
    fn=method('_open',ns)
    transform=NS(BasisZ=point(0,0,1),Inverse='inverse',OfPoint=lambda p:p)
    obj=NS(doc='VIS',_source_override={7:(selected_doc,transform)},_category_override=[1],
           skipped_links=[],_kind_of=lambda key,el:core.SLAB,open_steps=[])
    fn(obj)
    assert queried==[selected_doc]
    assert list(obj._elements)==[(7,42)]
    assert len(obj._sources)==1 and obj._sources[0][0]==7


def test_downward_api_reuses_cached_hits_and_returns_only_floor_elements():
    floor=NS(Category=NS(Id=NS(IntegerValue=1)))
    roof=NS(Category=NS(Id=NS(IntegerValue=2)))
    ns=dict(core=core,ft=lambda value:value/304.8,mm=lambda value:value*304.8,BuiltInCategory=NS(OST_Floors=1))
    fn=method('floor_hits_below',ns)
    calls=[]
    def hits(x,y,z):
        calls.append((x,y,z))
        return [],[(1001,core.SLAB,'floor'),(501,core.SLAB,'roof')]
    obj=NS(_grid=NS(at=lambda x,y:[]),_hits=hits,_element=lambda key:{'floor':floor,'roof':roof}[key])
    result=fn(obj,1,2,10)
    assert calls==[(1,2,10+1/304.8)]
    assert result==[(1000/304.8,floor)]


def test_floor_probe_verifies_missed_solid_even_if_lower_floor_was_found():
    floor=NS(Category=NS(Id=NS(IntegerValue=1)))
    lower=NS(Category=NS(Id=NS(IntegerValue=1)))
    ns=dict(core=core,ft=lambda value:value/304.8,mm=lambda value:value*304.8,
            BuiltInCategory=NS(OST_Floors=1))
    fn=method('floor_hits_below',ns)
    calls=[]
    def solids(key,x,y,z,include_inside=False):
        calls.append((key,include_inside))
        return [],[501]
    obj=NS(_hits=lambda x,y,z:([],[(3001,core.SLAB,'lower')]),
           _grid=NS(at=lambda x,y:[('floor',0,2000),('lower',-3000,0)]),
           _element=lambda key:{'floor':floor,'lower':lower}[key],
           _kind_cache={'floor':core.SLAB,'lower':core.SLAB},down_range_mm=None,
           _sloped_hits=solids)
    hits=fn(obj,1,2,10)
    assert calls==[('floor',True)]
    assert hits==[(3000/304.8,lower),(500/304.8,floor)]


def test_floor_probe_does_not_invent_hit_when_solid_has_a_void():
    floor=NS(Category=NS(Id=NS(IntegerValue=1)))
    ns=dict(core=core,ft=lambda value:value/304.8,mm=lambda value:value*304.8,
            BuiltInCategory=NS(OST_Floors=1))
    fn=method('floor_hits_below',ns)
    obj=NS(_hits=lambda x,y,z:([],[]),_grid=NS(at=lambda x,y:[('floor',0,2000)]),
           _element=lambda key:floor,_kind_cache={'floor':core.SLAB},down_range_mm=None,
           _sloped_hits=lambda *args,**kwargs:([],[]))
    assert fn(obj,1,2,10)==[]


def test_solid_fallback_counts_origin_inside_slab_only_when_requested(monkeypatch):
    monkeypatch.setitem(sys.modules,'Autodesk.Revit.DB',NS(SolidCurveIntersectionOptions=lambda:None))
    point=lambda x,y,z:NS(X=x,Y=y,Z=z)
    segment=NS(GetEndPoint=lambda i:point(0,0,[9,11][i]))
    solid=NS(IntersectWithCurve=lambda ray,options:NS(SegmentCount=1,GetCurveSegment=lambda i:segment))
    transform=NS(Inverse=NS(OfPoint=lambda p:p),OfPoint=lambda p:p)
    ns=dict(XYZ=point,Line=NS(CreateBound=lambda a,b:(a,b)),_PROBE_RANGE_FT=1000,
            mm=lambda z:z*304.8)
    fn=method('_sloped_hits',ns)
    obj=NS(_elements={'floor':('floor',transform)},_local_solids=lambda key,element:[solid])
    assert fn(obj,'floor',0,0,10)==([],[])
    assert fn(obj,'floor',0,0,10,include_inside=True)==([],[0])


def test_foundation_hits_require_explicit_support_scope():
    foundation=NS(Category=NS(Id=NS(IntegerValue=2)))
    ns=dict(core=core,ft=lambda value:value/304.8,mm=lambda value:value*304.8,
            BuiltInCategory=NS(OST_Floors=1))
    fn=method('floor_hits_below',ns)
    obj=NS(_hits=lambda x,y,z:([],[(1001,core.SLAB,'foundation')]),
           _element=lambda key:foundation,_grid=NS(at=lambda x,y:[]))
    assert fn(obj,1,2,10)==[]
    assert fn(obj,1,2,10,support_categories=[1,2])==[(1000/304.8,foundation)]
