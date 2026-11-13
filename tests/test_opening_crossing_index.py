"""Broad phase equivalence and batch-query counts without Revit assemblies."""
import ast
import random
from pathlib import Path
from types import SimpleNamespace as NS
from lowlife.slab_marks_core import BoxGrid

ROOT=Path(__file__).parents[1]


def test_boxgrid_rectangle_query_matches_brute_force_and_handles_giant_bounds():
    rng=random.Random(12)
    grid=BoxGrid(cell=7)
    bounds=[(-1e8,-1e8,1e8,1e8)]
    for _ in range(200):
        x,y=rng.uniform(-100,100),rng.uniform(-100,100)
        bounds.append((x,y,x+rng.uniform(0,30),y+rng.uniform(0,30)))
    for i,b in enumerate(bounds):grid.add(i,b)
    assert len(grid.large)==1 and len(grid.grid)<2000
    for _ in range(100):
        x,y=rng.uniform(-120,120),rng.uniform(-120,120)
        query=(x,y,x+rng.uniform(0,90),y+rng.uniform(0,90))
        expected=[i for i,b in enumerate(bounds) if b[0]<=query[2] and b[2]>=query[0] and b[1]<=query[3] and b[3]>=query[1]]
        assert grid.overlapping(query)==expected
        assert grid.at(x,y)==[i for i,b in enumerate(bounds) if b[0]<=x<=b[2] and b[1]<=y<=b[3]]
    assert grid.overlapping((-1e9,-1e9,1e9,1e9))==list(range(len(bounds)))


def source_adapter():
    counts=[]
    hosts=[NS(Id=i,cat=cat,get_BoundingBox=lambda _,b=b:NS(Min=NS(X=b[0],Y=b[1],Z=b[2]),Max=NS(X=b[3],Y=b[4],Z=b[5])))
           for i,cat,b in [(1,1,(-10,-10,0,0,0,5)),(2,1,(0,0,20,10,10,30)),(3,2,(0,0,0,10,10,10))]]
    class Collector(list):
        def WherePasses(self,f):
            if isinstance(f,tuple):return Collector([h for h in self if h.cat in f])
            a,b=f.MinimumPoint,f.MaximumPoint
            return Collector([h for h in self if all(lo<=qh and hi>=ql for lo,hi,ql,qh in zip(
                (h.get_BoundingBox(None).Min.X,h.get_BoundingBox(None).Min.Y,h.get_BoundingBox(None).Min.Z),
                (h.get_BoundingBox(None).Max.X,h.get_BoundingBox(None).Max.Y,h.get_BoundingBox(None).Max.Z),
                (a.X,a.Y,a.Z),(b.X,b.Y,b.Z)))])
        def WhereElementIsNotElementType(self):return self
    def collect(doc):
        counts.append(doc);return Collector(hosts)
    class Generic:
        def __class_getitem__(cls,t):return list
    tree=ast.parse((ROOT/'lib/lowlife/tray_boxes.py').read_text(encoding='utf-8'))
    node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='_Source')
    scope=dict(BoxGrid=BoxGrid,List=Generic,BuiltInCategory=int,ElementMulticategoryFilter=lambda cats:tuple(cats),
               BoundingBoxIntersectsFilter=lambda outline:outline,FilteredElementCollector=collect,
               ft=lambda n:n,XYZ=lambda x,y,z:NS(X=x,Y=y,Z=z),_box_points=lambda b:[b.Min,b.Max])
    exec(compile(ast.Module(body=[node],type_ignores=[]),'source','exec'),scope)
    return scope['_Source'],counts


def test_large_batch_reuses_index_and_keeps_category_height_and_boundary_checks():
    Source,calls=source_adapter()
    source=Source('KR')
    outline=NS(MinimumPoint=NS(X=0,Y=0,Z=0),MaximumPoint=NS(X=1,Y=1,Z=5))
    for _ in range(160):
        assert [h.Id for h in source.hosts([1],outline)]==[1]  # includes touching boundary; excludes upper floor
    assert len(calls)==128  # 127 quick queries + one build; remaining queries need no collector
    assert [h.Id for h in source.hosts([2],outline)]==[3]
    assert len(calls)==129  # different category set keeps its own index/query history
    fresh=Source('other KR')
    assert [h.Id for h in fresh.hosts([1],outline)]==[1]
    assert len(calls)==130  # no cache leaks into another command/source


def test_placement_reads_issue_registry_once_before_processing_routes():
    tree=ast.parse((ROOT/'lib/lowlife/opening_tasks_revit.py').read_text(encoding='utf-8'))
    place=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='place')
    route_loop=next(n for n in place.body if isinstance(n,ast.For) and isinstance(n.target,ast.Tuple))
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
                   and isinstance(n.func.value,ast.Name) and n.func.value.id=='store' and n.func.attr=='registry'
                   for n in ast.walk(route_loop))


def test_exact_solid_intersection_is_retained_and_transients_are_disposed():
    from lowlife import tray_boxes_core as core
    disposed=[]
    class P:
        def __init__(self,x,y=0,z=0):self.X,self.Y,self.Z=x,y,z
        def Add(self,p):return P(self.X+p.X,self.Y+p.Y,self.Z+p.Z)
        def Subtract(self,p):return P(self.X-p.X,self.Y-p.Y,self.Z-p.Z)
        def Multiply(self,n):return P(self.X*n,self.Y*n,self.Z*n)
        def Divide(self,n):return self.Multiply(1.0/n)
        def DotProduct(self,p):return self.X*p.X+self.Y*p.Y+self.Z*p.Z
    class Line:
        Direction=P(1)
        def __init__(self,lo,hi):self.ends=[P(lo),P(hi)]
        def GetEndPoint(self,i):return self.ends[i]
        def Dispose(self):disposed.append('segment')
    class Location:
        Curve=Line(0,4)
    options=[]
    def options_factory():
        o=NS(Dispose=lambda:disposed.append('options'));options.append(o);return o
    def intersect(axis,opts):
        assert opts is options[0] and axis is Location.Curve
        return NS(SegmentCount=1,GetCurveSegment=lambda i:Line(1,3),Dispose=lambda:disposed.append('hit'))
    host=NS(Category=NS(Id=2))
    source=NS(inverse=None,link='KR',to_local=lambda p:p,to_model=lambda p:p,
              hosts=lambda cats,outline:[host],solids=lambda host,opts:[NS(IntersectWithCurve=intersect)])
    tree=ast.parse((ROOT/'lib/lowlife/tray_boxes.py').read_text(encoding='utf-8'))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='tray_crossings')
    scope=dict(LocationCurve=Location,Line=Line,_box_points=lambda bbox:bbox,_outline=lambda p:p,
               ft=lambda n:n,MIN_CROSSING_MM=1,SolidCurveIntersectionOptions=options_factory,
               _id_int=int,BuiltInCategory=NS(OST_Walls=1),core=core,_t=lambda p:(p.X,p.Y,p.Z),
               Crossing=lambda *args:args)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'crossings','exec'),scope)
    tray=NS(Location=Location(),get_BoundingBox=lambda view:[P(0),P(4)])
    result=scope['tray_crossings'](tray,[source],[2],None)
    assert len(result)==1 and result[0][:3]==('floor',(1,0,0),(3,0,0))
    assert disposed==['segment','hit','options']
