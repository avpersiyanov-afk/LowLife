"""Highlight resolves saved view/element identities, including merged receipts."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from lowlife import opening_tasks_core as core


class View:
    def __init__(self,uid):
        self.UniqueId=self.Id=self.Name=uid
        self.IsTemplate=False


class Schedule(View):pass


class GenericList:
    def __class_getitem__(cls,item):return list


@pytest.mark.parametrize('role',['VIS','KR','AR'])
def test_highlight_uses_created_view_and_actual_current_model_element(role):
    path=Path(__file__).parents[1]/'lib/lowlife/opening_tasks_views.py'
    tree=ast.parse(path.read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='highlight')
    view=View('managed-view');schedule=Schedule('schedule');foreign=View('other-project')
    element=NS(Id='opening-id')
    registry={
        'control_views':{'P/view/0':view.UniqueId,'P/schedule':schedule.UniqueId,'OTHER/view/0':foreign.UniqueId},
        'kr_control_views':{'P/slab-plan/0':view.UniqueId},
        'receipts':{'source/task':{'opening_uid':'opening'}},
        'ar_receipts':{'source/task':{'opening_uid':'opening'}}}
    doc=NS(GetElement=lambda uid:{view.UniqueId:view,schedule.UniqueId:schedule,
                                 foreign.UniqueId:foreign,'opening':element}.get(uid))
    selected=[];shown=[];refreshed=[]
    uidoc=NS(Document=doc,ActiveView=View('old-view'),
             Selection=NS(SetElementIds=selected.append),ShowElements=shown.append,
             RefreshActiveView=lambda:refreshed.append(True))
    queried=[]
    def collector(doc,view_id):
        queried.append(view_id)
        return NS(WhereElementIsNotElementType=lambda:NS(ToElementIds=lambda:['opening-id']))
    ns=dict(store=NS(registry=lambda doc:registry),api=NS(core=core),
            View=View,ViewSchedule=Schedule,FilteredElementCollector=collector,List=GenericList,
            ElementId=str,tr=lambda ru,en=None:en or ru)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    rows=[{'uid':'opening','key':'source/task'}]
    ns['highlight'](uidoc,role,'P',rows)
    assert uidoc.ActiveView is view
    assert selected==shown==[['opening-id']] and refreshed==[True]
    assert queried==['managed-view']
    with pytest.raises(ValueError):ns['highlight'](uidoc,role,'P',[])
    with pytest.raises(ValueError):ns['highlight'](uidoc,role,'MISSING',rows)
