"""Vertical roof-volume fitting: API contract plus analytic clipped-body adapters."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from lowlife import tray_boxes_core as core
from lowlife import opening_tasks_core as tasks

ROOT=Path(__file__).parents[1]


def function(path,name,ns):
    tree=ast.parse((ROOT/path).read_text())
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),ns)
    return ns[name]


class Point:
    def __init__(self,x=0,y=0,z=0):self.X,self.Y,self.Z=x,y,z
    def Add(self,p):return Point(self.X+p.X,self.Y+p.Y,self.Z+p.Z)
    def Multiply(self,a):return Point(self.X*a,self.Y*a,self.Z*a)
Point.BasisZ=Point(0,0,1)


def bbox(low,high):return NS(Min=Point(*low),Max=Point(*high),Transform=NS(OfPoint=lambda p:p))


def points(bounds):
    return [bounds.Transform.OfPoint(Point(x,y,z)) for x in (bounds.Min.X,bounds.Max.X)
            for y in (bounds.Min.Y,bounds.Max.Y) for z in (bounds.Min.Z,bounds.Max.Z)]


class Loop(list):
    def Append(self,x):self.append(x)


class GenericList:
    def __class_getitem__(cls,item):return list


def fitting(shape='plane',offset=0,empty=False,failed=False):
    created=[]
    def extrusion(loops,direction,height):
        prism=NS(footprint=[line[0] for line in loops[0]],direction=direction,height=height,disposed=False)
        prism.Dispose=lambda:setattr(prism,'disposed',True)
        created.append(prism);return prism
    def intersect(solid,prism,operation):
        assert operation=='intersect'
        if failed:raise RuntimeError('Boolean failure')
        xs=[p.X for p in prism.footprint]
        if shape=='plane':low,high=.5*min(xs),.5*max(xs)+1
        else:
            low=0 if min(xs)<=0<=max(xs) else .5*min(abs(x) for x in xs)
            high=.5*max(abs(x) for x in xs)+1
        clipped=NS(Volume=0 if empty else 1,GetBoundingBox=lambda:bbox((-1,-1,low),(1,1,high)),disposed=False)
        clipped.Dispose=lambda:setattr(clipped,'disposed',True)
        return clipped
    ns=dict(core=core,ft=lambda mm:mm/304.8,_box_points=points,XYZ=Point,CurveLoop=Loop,List=GenericList,
            Line=NS(CreateBound=lambda a,b:(a,b)),GeometryCreationUtilities=NS(CreateExtrusionGeometry=extrusion),
            BooleanOperationsUtils=NS(ExecuteBooleanOperation=intersect),BooleanOperationsType=NS(Intersect='intersect'),
            tr=lambda ru,en=None:en or ru)
    fit=function('lib/lowlife/tray_boxes.py','fit_vertical_host',ns)
    host=NS(get_BoundingBox=lambda view:bbox((-20,-20,-11),(20,20,12)))
    source=NS(horizontal_host=lambda host,options:False,
              inverse=NS(OfVector=lambda p:p),solids=lambda host,options:['roof-solid'],
              to_model=lambda p:Point(p.X,p.Y,p.Z+offset),to_local=lambda p:Point(p.X,p.Y,p.Z-offset))
    crossing=NS(host=host)
    return fit,source,crossing,created


@pytest.mark.parametrize('offset',[0,100])
def test_sloped_roof_height_covers_full_final_footprint_and_link_offset(offset):
    fit,source,crossing,created=fitting(offset=offset)
    box=core.Box(core.FLOOR,(0,0,offset+.5),(1,0,0),10,4,1,1)
    fitted=fit(box,crossing,source,None,(0,0,1),.2)
    assert fitted.width==10 and fitted.depth==4
    assert fitted.height==pytest.approx(6.2)  # 10 * slope .5 + vertical thickness 1 + allowance .2
    assert fitted.center==pytest.approx((0,0,offset+.5))
    assert created[0].disposed
    enlarged=core.enlarge_opening(box,2)
    fitted=fit(enlarged,crossing,source,None,(0,0,-1),.2)
    assert fitted.height==pytest.approx(7.2)
    assert fitted.width==12 and fitted.depth==6


def test_valley_inside_footprint_is_included_not_just_axis_or_corner_rays():
    fit,source,crossing,created=fitting(shape='valley')
    box=core.Box(core.FLOOR,(0,0,.5),(1,0,0),10,4,1,1)
    fitted=fit(box,crossing,source,None,(0,0,1),0)
    assert fitted.height==pytest.approx(3.5)
    assert fitted.center[2]==pytest.approx(1.75)


def test_rotated_footprint_uses_all_four_corners():
    fit,source,crossing,created=fitting()
    s=math.sqrt(.5)
    box=core.Box(core.FLOOR,(0,0,.5),(s,s,0),10,4,1,1)
    fitted=fit(box,crossing,source,None,(0,0,1),0)
    assert fitted.height==pytest.approx((10+4)*s*.5+1)


def test_flat_slab_fast_path_does_not_create_boolean_geometry():
    fit,source,crossing,created=fitting()
    source.horizontal_host=lambda *args:True
    box=core.Box(core.FLOOR,(0,0,0),(1,0,0),10,4,1,1)
    assert fit(box,crossing,source,None,(.7,0,.7),0) is box
    assert created==[]


@pytest.mark.parametrize('empty,failed',[(True,False),(False,True)])
def test_bad_geometry_reports_failure_and_disposes_transient_volume(empty,failed):
    fit,source,crossing,created=fitting(empty=empty,failed=failed)
    box=core.Box(core.FLOOR,(0,0,0),(1,0,0),10,4,1,1)
    with pytest.raises(ValueError):fit(box,crossing,source,None,(0,0,1),0)
    assert created[0].disposed


def test_nonvertical_route_through_sloped_host_is_explicitly_rejected():
    fit,source,crossing,created=fitting()
    box=core.Box(core.FLOOR,(0,0,0),(1,0,0),10,4,1,1)
    with pytest.raises(ValueError):fit(box,crossing,source,None,(.1,0,.995),0)
    assert not created


@pytest.mark.parametrize('kind',['floor','roof'])
def test_native_opening_is_vertical_for_floor_and_roof(kind):
    class Floor:pass
    class Roof:pass
    host=Floor() if kind=='floor' else Roof()
    host.get_BoundingBox=lambda view:bbox((-20,-20,-10),(20,20,10))
    calls=[]
    doc=NS(GetElement=lambda uid:host,Create=NS(NewOpening=lambda *args:calls.append(args) or 'opening'))
    ns=dict(core=tasks,store=NS(model_id=lambda doc:'KR'),boxes=NS(_xyz=lambda p:Point(*p),ft=lambda mm:mm/304.8),
            Floor=Floor,RoofBase=Roof,CurveArray=Loop,Line=NS(CreateBound=lambda a,b:(a,b)),XYZ=Point,
            tr=lambda ru,en=None:en or ru)
    create=function('lib/lowlife/opening_tasks_revit.py','create_native_opening',ns)
    g=dict(kind='floor',host_model='KR',host_uid='host',center_mm=[0,0,0],x_dir=[1,0,0],size_mm=[1000,400,1000])
    assert create(doc,g)=='opening'
    assert calls[0][0] is host and calls[0][2] is False
    assert len(calls[0][1])==4


def test_roof_categories_are_opt_in_without_changing_legacy_tray_selection():
    ns=dict(cfg=NS(HOSTS_ALL='all',HOSTS_WALLS='walls',HOSTS_FLOORS='floors'),
            BuiltInCategory=NS(OST_Walls=1,OST_Floors=2,OST_Roofs=3))
    categories=function('lib/lowlife/tray_boxes.py','_host_categories',ns)
    assert categories({'box_hosts':'all'})==[1,2]
    assert categories({'box_hosts':'all'},include_roofs=True)==[1,2,3]
    assert categories({'box_hosts':'floors'},include_roofs=True)==[2,3]
    assert categories({'box_hosts':'walls'},include_roofs=True)==[1]


def test_roof_base_level_uses_builtin_without_parameter_names():
    ns=dict(ElementId=NS(InvalidElementId=-1),BuiltInParameter=NS(ROOF_BASE_LEVEL_PARAM='base',ROOF_CONSTRAINT_LEVEL_PARAM='reference'))
    read=function('lib/lowlife/geometry.py','get_element_level',ns)
    levels={'roof-level':object(),'normal-level':object()}
    calls=[]
    roof=NS(LevelId=-1,get_Parameter=lambda key:calls.append(key) or NS(AsElementId=lambda:'roof-level'))
    assert read(NS(GetElement=levels.get),roof) is levels['roof-level'] and calls==['base']
    calls[:]=[];roof.LevelId='normal-level'
    assert read(NS(GetElement=levels.get),roof) is levels['normal-level'] and not calls
    roof.LevelId=-1
    roof.get_Parameter=lambda key:NS(AsElementId=lambda:'roof-level') if key=='reference' else None
    assert read(NS(GetElement=levels.get),roof) is levels['roof-level']


def test_flat_host_detection_is_cached_and_accepts_vertical_cylindrical_sides():
    class Plane:
        def __init__(self,z,n):self.Origin=Point(0,0,z);self.FaceNormal=Point(*n)
    class Cylinder:
        Axis=Point(0,0,1)
    path=ROOT/'lib/lowlife/tray_boxes.py'
    tree=ast.parse(path.read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='_Source')
    fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='horizontal_host')
    ns=dict(_id_int=lambda x:x,PlanarFace=Plane,CylindricalFace=Cylinder)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    reads=[]
    faces=[Plane(0,(0,0,-1)),Plane(1,(0,0,1)),Plane(0,(1,0,0)),Cylinder()]
    def solids(*args):reads.append(True);return [NS(Faces=faces)]
    source=NS(_horizontal={},solids=solids,to_model=lambda p:p,to_model_vector=lambda p:p)
    host=NS(Id=1)
    assert ns['horizontal_host'](source,host,None)
    faces[1]=Plane(1,(0,.5,math.sqrt(.75)))
    assert ns['horizontal_host'](source,host,None)
    assert len(reads)==1
    assert not ns['horizontal_host'](source,NS(Id=2),None)


    faces[1]=Plane(1,(1e-5,0,math.sqrt(1-1e-10)))
    assert not ns['horizontal_host'](source,NS(Id=3),None)
