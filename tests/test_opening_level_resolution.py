"""Execute the actual resolver with model/solid adapters; no live Revit needed."""
import ast
import sys
import types
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from lowlife import opening_levels_core as core


class XYZ:
    def __init__(self,x,y,z):self.X,self.Y,self.Z=x,y,z
    def DistanceTo(self,other):
        return ((self.X-other.X)**2+(self.Y-other.Y)**2+(self.Z-other.Z)**2)**0.5
XYZ.BasisZ=XYZ(0,0,1)


class Level:
    def __init__(self,uid,name,z):
        self.UniqueId,self.Name,self.ProjectElevation=uid,name,z


class Floor:
    def __init__(self,uid,level,z,hole=False):
        self.UniqueId,self.LevelId,self.z,self.hole=uid,level,z,hole
    def get_BoundingBox(self,view):
        return NS(Min=XYZ(0,0,self.z-0.5),Max=XYZ(10,10,self.z))


class Intersection:
    def __init__(self,floor,ray):
        self.SegmentCount=0 if floor.hole else 1
        self.points=[XYZ(5,5,min(floor.z,ray[0].Z)),XYZ(5,5,floor.z-0.5)]
    def GetCurveSegment(self,index):return NS(GetEndPoint=lambda i:self.points[i])
    def Dispose(self):pass


class Source:
    def __init__(self,doc,link):
        self.doc,self.link=doc,link
        self.transform=link.transform if link else None
        self.offset=link.offset if link else 0
    def to_local(self,p):return XYZ(p.X,p.Y,p.Z-self.offset)
    def to_model(self,p):return XYZ(p.X,p.Y,p.Z+self.offset)
    def solids(self,floor,options):
        self.doc.checked.append(floor.UniqueId)
        return [NS(IntersectWithCurve=lambda ray,options:Intersection(floor,ray))]


class Collector:
    def __init__(self,doc):self.doc=doc
    def OfCategory(self,category):
        assert category=='floors'
        return self
    def WhereElementIsNotElementType(self):return self.doc.floors


def document(levels,floors,uid):
    index={lv.UniqueId:lv for lv in levels}
    return NS(GetElement=lambda eid:index.get(eid),floors=floors,checked=[],
              ProjectInformation=NS(UniqueId=uid))


def resolver(monkeypatch,doc,local_levels):
    import lowlife
    boxes=NS(_Source=Source,_xyz=lambda p:XYZ(*p),mm=lambda z:z*304.8,
             _box_points=lambda bb:[bb.Min,bb.Max],safe_element_name=lambda lv:lv.Name)
    monkeypatch.setitem(sys.modules,'lowlife.tray_boxes',boxes)
    monkeypatch.setattr(lowlife,'tray_boxes',boxes,raising=False)
    def probe_factory(doc,sources,categories,down_range_mm):
        assert len(sources)==1 and categories==['floors','foundations','roofs'] and down_range_mm is None
        source_doc,transform=next(iter(sources.values()))
        def hits(x,y,z,support_categories=None):
            result=[]
            for floor in source_doc.floors:
                source_doc.checked.append(floor.UniqueId)
                top=transform.OfPoint(XYZ(x,y,floor.z)).Z
                if not floor.hole and top<=z:
                    result.append((z-top,floor))
            return result
        return NS(floor_hits_below=hits)
    monkeypatch.setitem(sys.modules,'lowlife.slab_marks',NS(SlabProbe=probe_factory))
    path=Path(__file__).parents[1]/'lib/lowlife/opening_levels.py'
    tree=ast.parse(path.read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Resolver')
    ns=dict(core=core,XYZ=XYZ,Level=Level,FilteredElementCollector=Collector,
            get_element_level=lambda source_doc,element:source_doc.GetElement(element.LevelId),
            BuiltInCategory=NS(OST_Floors='floors',OST_StructuralFoundation='foundations',OST_Roofs='roofs'),
            Line=NS(CreateBound=lambda a,b:(a,b)),SolidCurveIntersectionOptions=lambda:None,
            tr=lambda ru,en=None:ru)
    exec(compile(ast.Module(body=[cls],type_ignores=[]),str(path),'exec'),ns)
    obj=object.__new__(ns['Resolver'])
    obj.doc,obj.levels,obj.sources,obj.probes=doc,local_levels,{},{}
    return obj


def link(doc,z=0):
    return NS(UniqueId='link-'+doc.ProjectInformation.UniqueId,GetLinkDocument=lambda:doc,
              transform=NS(BasisZ=XYZ.BasisZ,OfPoint=lambda p:XYZ(p.X,p.Y,p.Z+z)),offset=z)


def test_pierced_floor_level_uses_selected_link_and_transformed_elevation(monkeypatch):
    source_level=Level('source-L','Building-1',10)
    floor=Floor('slab','source-L',12)
    linked=document([source_level],[floor],'KR')
    correct=Level('vis-L','Building-1',110)
    auxiliary=Level('aux','Auxiliary',111.5)
    local=document([correct,auxiliary],[],'VIS')
    r=resolver(monkeypatch,local,[correct,auxiliary])
    target,info=r.resolve(NS(link=link(linked,100),host=floor,kind='floor'))
    assert target is correct
    assert info['source_model']=='KR' and info['support_uid']=='slab'
    assert info['method']=='floor_host'
    assert info['elevation_mm']==pytest.approx(110*304.8)


def test_wall_ray_intersects_only_ar_floors_and_ignores_holes(monkeypatch):
    ar_level=Level('ar-L','AR-Level',8)
    deeper=Floor('ar-lower','ar-L',9)
    hole=Floor('ar-upper-hole','ar-L',11,hole=True)
    ar=document([ar_level],[hole,deeper],'AR')
    kr=document([Level('kr-L','KR-Level',9.5)],[Floor('kr-floor','kr-L',11.5)],'KR')
    target=Level('vis-ar','AR-Level',8)
    local=document([target],[Floor('local-foreign','foreign',11.8)],'VIS')
    r=resolver(monkeypatch,local,[target,Level('aux','Aux',11.9)])
    wall=NS(LevelId='wall-base')
    result,info=r.resolve(NS(link=link(ar),host=wall,kind='wall',center=lambda:(5,5,12)))
    assert result is target
    assert info['support_uid']=='ar-lower' and info['method']=='downward_ray'
    assert ar.checked==['ar-upper-hole','ar-lower']
    assert kr.checked==[] and local.checked==[]


def test_opening_wrapper_reuses_assigner_and_verifies_target_and_position(monkeypatch):
    import lowlife
    path=Path(__file__).parents[1]/'lib/lowlife/opening_levels.py'
    tree=ast.parse(path.read_text(encoding='utf-8'))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='assign_level')
    instance=NS(Id='box-id',LevelId='wrong',Location=NS(Point=XYZ(1,2,30)))
    before=instance.Location.Point
    calls=[]
    def assign(doc,inst,level):
        calls.append((inst.Id,level.Id))
        inst.LevelId=level.Id
        return True
    module=NS(assign_by_param=assign)
    geometry=NS(get_element_level=lambda doc,inst:NS(Id=inst.LevelId))
    monkeypatch.setattr(lowlife,'level_assign',module,raising=False)
    monkeypatch.setattr(lowlife,'geometry',geometry,raising=False)
    ns=dict(tr=lambda ru,en=None:ru)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    ns['assign_level'](None,instance,NS(Id='correct'))
    assert calls==[('box-id','correct')]
    assert instance.Id=='box-id' and instance.Location.Point.DistanceTo(before)==0
    ns['assign_level'](None,instance,NS(Id='correct'))
    assert len(calls)==1
    module.assign_by_param=lambda *args:True
    with pytest.raises(ValueError):ns['assign_level'](None,instance,NS(Id='other'))
    def moved(doc,inst,level):
        inst.LevelId=level.Id
        inst.Location.Point=XYZ(1,2,99)
        return True
    module.assign_by_param=moved
    with pytest.raises(ValueError):ns['assign_level'](None,instance,NS(Id='other'))


def test_wall_foundation_without_assigned_kr_level_uses_current_ar_elevation(monkeypatch):
    foundation=Floor('foundation','missing',0)
    kr=document([], [foundation], 'KR')
    target=Level('AR-0','AR ground',0)
    local=document([target],[],'VIS')
    r=resolver(monkeypatch,local,[target,Level('other','Other building',-1)])
    result,info=r.resolve(NS(link=link(kr),host=NS(LevelId='none'),kind='wall',center=lambda:(5,5,10)))
    assert result is target and info['support_uid']=='foundation'
    assert info['source_level_uid']==''


def test_link_level_with_different_ar_name_matches_by_transformed_elevation(monkeypatch):
    kr_level=Level('kr-level','KR ground',0)
    kr=document([kr_level],[Floor('slab','kr-level',1)],'KR')
    target=Level('AR-0','AR ground',100)
    local=document([target],[],'VIS')
    r=resolver(monkeypatch,local,[target])
    result,info=r.resolve(NS(link=link(kr,100),host=kr.floors[0],kind='floor'))
    assert result is target and info['elevation_mm']==pytest.approx(100*304.8)


def test_floor_kr_elevation_maps_to_nearest_ar_level_with_offset(monkeypatch):
    kr_level=Level('kr-level','KR structural',9.5)
    kr=document([kr_level],[Floor('slab','kr-level',10)],'KR')
    target=Level('AR-storey','AR storey',110)
    local=document([target],[],'VIS')
    r=resolver(monkeypatch,local,[target,Level('AR-other','AR other',100)])
    result,info=r.resolve(NS(link=link(kr,100),host=kr.floors[0],kind='floor'))
    assert result is target
    assert info['elevation_mm']==pytest.approx(109.5*304.8)
    assert info['support_uid']=='slab'
