"""Final-envelope neighbor-wall check without Revit assemblies."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS

ROOT=Path(__file__).parents[1]


def function(name,scope):
    tree=ast.parse((ROOT/'lib/lowlife/opening_tasks_neighbors.py').read_text(encoding='utf-8'))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'neighbors','exec'),scope)
    return scope[name]


def test_neighbor_wall_check_excludes_own_host_and_touching_and_caches_solids():
    bodies,disposed,loaded=[],[],[]
    walls=[NS(UniqueId=name) for name in ('host','neighbor','touch')]
    class Collector(list):
        def OfCategory(self, category):return self
        def WhereElementIsNotElementType(self):return self
        def WherePasses(self, region):
            assert region=='bounds'
            return self
    link=NS(UniqueId='selected-link',GetLinkDocument=lambda:'KR')
    doc=NS(GetElement=lambda uid:link)
    def body(g):
        assert g=='actual final enlarged geometry in link coordinates'
        value=NS(GetBoundingBox=lambda:'bounds',Dispose=lambda:disposed.append('body'))
        bodies.append(value);return value
    def solids(wall,options):
        loaded.append(wall.UniqueId)
        return [wall.UniqueId]
    def intersect(body,solid,operation):
        return NS(Volume=2 if solid=='neighbor' else 0,Dispose=lambda:disposed.append(solid))
    scope=dict(Options=lambda:None, api=NS(metadata=lambda el:dict(owner_uid=el.UniqueId,host_link_uid='link',host_uid='host'),
                  host_geometry=lambda *a:'actual final enlarged geometry in link coordinates'),
               boxes=NS(_outline=lambda b:b,_box_points=lambda b:b,_solids=solids,ft=lambda n:n),
               envelope_solid=body, BoundingBoxIntersectsFilter=lambda b:b,
               FilteredElementCollector=lambda doc:Collector(walls),BuiltInCategory=NS(OST_Walls='walls'),
               BooleanOperationsUtils=NS(ExecuteBooleanOperation=intersect),
               BooleanOperationsType=NS(Intersect='intersection'),unicode=str,tr=lambda ru,en=None:en or ru)
    check=function('check',scope)
    boxes=[NS(UniqueId='box1'),NS(UniqueId='box2')]
    matches,errors=check(doc,boxes)
    assert not errors
    assert [wall.UniqueId for inst,link,group in matches for wall in group]==['neighbor','neighbor']
    assert loaded==['neighbor','touch']  # cached across boxes; own host never loaded
    assert disposed.count('body')==2 and disposed.count('neighbor')==2 and disposed.count('touch')==2
    # Unloaded links are explicitly unchecked, not reported as no collisions.
    link.GetLinkDocument=lambda:None
    matches,errors=check(doc,boxes)
    assert matches==[] and len(errors)==2


def test_logical_envelope_respects_rotation_and_final_dimensions():
    class Point:
        def __init__(self,x,y,z):self.X,self.Y,self.Z=x,y,z
        def Add(self,p):return Point(self.X+p.X,self.Y+p.Y,self.Z+p.Z)
        def Subtract(self,p):return Point(self.X-p.X,self.Y-p.Y,self.Z-p.Z)
        def Multiply(self,n):return Point(self.X*n,self.Y*n,self.Z*n)
    Point.BasisZ=Point(0,0,1)
    class Loop(list):
        def Append(self,line):self.append(line)
    class Generic:
        def __class_getitem__(cls,t):return list
    scope=dict(XYZ=Point,CurveLoop=Loop,List=Generic,
               boxes=NS(_xyz=lambda values:Point(*values),ft=lambda n:n),
               Line=NS(CreateBound=lambda a,b:(a,b)),
               GeometryCreationUtilities=NS(CreateExtrusionGeometry=lambda loops,axis,height:(loops,axis,height)))
    solid=function('envelope_solid',scope)
    loops,axis,height=solid(dict(center_mm=[10,20,30],x_dir=[0,1,0],size_mm=[400,200,300]))
    points=[a for a,b in loops[0]]
    assert (min(p.X for p in points),max(p.X for p in points))==(-90,110)
    assert (min(p.Y for p in points),max(p.Y for p in points))==(-180,220)
    assert {p.Z for p in points}=={-120}
    assert height==300 and axis is Point.BasisZ
