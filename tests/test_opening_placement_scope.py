import ast
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace as NS
from lowlife import tray_boxes_core as core

ROOT=Path(__file__).parents[1]


def test_preflight_cancel_stops_before_selection_or_model_operations():
    tree=ast.parse((ROOT/'lib/lowlife/opening_tasks_ui.py').read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='place')
    fn.body=[n for n in fn.body if not isinstance(n,ast.ImportFrom)]
    def fail(*args):raise AssertionError('must not proceed after cancelling the scheme')
    scope=dict(parts=NS(require_choice=lambda *a:None),revit=NS(doc=None,uidoc=None),
               tray_boxes_result=NS(show=lambda *a,**kw:(False,0)),pick_routes=fail)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'place','exec'),scope)
    scope['place'](dict(opening_project='P',opening_increase='auto',size_extra_mm=50))


def test_shared_scheme_preflight_example_uses_eir_per_side_and_znp_rule():
    tree=ast.parse((ROOT/'lib/lowlife/tray_boxes_result.py').read_text())
    assignment=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='example')
    scope=dict(core=core,preflight=True,clearance_mm=50)
    exec(compile(ast.Module(body=[assignment],type_ignores=[]),'scheme','exec'),scope)
    box=scope['example']
    assert round(box.width*304.8)==500
    assert round(box.height*304.8)==300
    assert core.recommended_increase_mm(max(core.opening_sides(box))*304.8)==100


def test_scope_check_excludes_crossings_outside_selected_area():
    tree=ast.parse((ROOT/'lib/lowlife/opening_tasks_revit.py').read_text())
    assignment=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='scope_bounds')
    condition=next(n for n in ast.walk(tree) if isinstance(n,ast.If) and isinstance(n.test,ast.BoolOp)
                   and isinstance(n.test.values[0],ast.Name) and n.test.values[0].id=='scope_bounds')
    append=ast.parse('accepted.append(box.center)').body[0]
    loop=ast.For(target=ast.Name(id='box',ctx=ast.Store()),iter=ast.Name(id='boxes_to_test',ctx=ast.Load()),
                 body=[assignment,condition,append],orelse=[])
    loop=ast.fix_missing_locations(loop)
    class Outline:
        def __init__(self,lo,hi):self.lo,self.hi=lo,hi
        def Contains(self,p,tol):return all(a-tol<=v<=b+tol for a,v,b in zip(self.lo,p,self.hi))
    bound=NS(Min=(0,0,0),Max=(10,10,10),Transform=NS(Inverse=NS(OfPoint=lambda p:p)))
    scope=dict(settings={'_opening_scope_bounds':[bound]},Outline=Outline,boxes=NS(_xyz=lambda p:p),
               boxes_to_test=[NS(center=(5,5,5)),NS(center=(50,5,5))],accepted=[])
    exec(compile(ast.Module(body=[loop],type_ignores=[]),'scope','exec'),scope)
    assert scope['accepted']==[(5,5,5)]


def test_scope_picker_offers_existing_areas_and_filters_eligible_routes():
    tree=ast.parse((ROOT/'lib/lowlife/opening_tasks_ui.py').read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='pick_routes')
    fn.body=[n for n in fn.body if not isinstance(n,ast.ImportFrom)]
    bounds=object()
    area=NS(Id=5,get_BoundingBox=lambda _:bounds)
    areas=[area]
    routes=[NS(valid=True),NS(valid=False)]
    class Collector(list):
        def OfCategory(self,category):return Collector(areas)
        def WhereElementIsNotElementType(self):return self
        def WherePasses(self,flt):return self
    class Generic:
        def __class_getitem__(cls,t):return list
    mode=['all'];offered=[]
    def choose(options,title,multiple=False):
        if multiple:return [area]
        offered.append(list(options.values()));return mode[0]
    scope=dict(OrderedDict=OrderedDict,List=Generic,ElementId=int,ElementFilter=object,
               BuiltInCategory=NS(OST_VolumeOfInterest=9,route=1),revit=NS(doc=None),
               FilteredElementCollector=lambda doc:Collector(routes),
               ElementMulticategoryFilter=lambda cats:cats,BoundingBoxIntersectsFilter=lambda bounds:bounds,
               LogicalOrFilter=lambda regions:regions,choose=choose,tr=lambda ru,en=None:en or ru,
               mep=NS(CATEGORY_NAMES=['route'],RouteSelectionFilter=lambda settings:NS(AllowElement=lambda el:el.valid)),
               boxes=NS(safe_element_name=lambda scope:'Scope',_id_int=int,_outline=lambda b:b,_box_points=lambda b:b),
               selected_elements=lambda filt:['manually selected'])
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'pick','exec'),scope)
    settings={}
    assert scope['pick_routes'](settings)==[routes[0]]
    assert 'scopes' in offered[-1]
    mode[0]='scopes'
    assert scope['pick_routes'](settings)==[routes[0]]
    assert settings['_opening_scope_bounds']==[bounds]
    mode[0]='manual';areas[:]=[]
    assert scope['pick_routes']({})==['manually selected']
    assert 'scopes' not in offered[-1]
    mode[0]=None
    assert scope['pick_routes']({})==[]
