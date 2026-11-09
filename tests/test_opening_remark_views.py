"""Run annotation reconciliation with a minimal view/document API adapter."""
import ast
import copy
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from lowlife import opening_tasks_core as core
from lowlife.tag_layout import TagItem, find_clusters, layout, rect_union


class Point:
    def __init__(self,x=0,y=0,z=0):self.X,self.Y,self.Z=x,y,z
    def Add(self,p):return Point(self.X+p.X,self.Y+p.Y,self.Z+p.Z)
    def Subtract(self,p):return Point(self.X-p.X,self.Y-p.Y,self.Z-p.Z)
    def Multiply(self,a):return Point(self.X*a,self.Y*a,self.Z*a)
    def DotProduct(self,p):return self.X*p.X+self.Y*p.Y+self.Z*p.Z


class View:
    def __init__(self,uid):
        self.UniqueId=self.Id=uid
        self.IsTemplate=False;self.IsPerspective=False;self.IsLocked=False
        self.Origin=Point();self.RightDirection=Point(1,0,0);self.UpDirection=Point(0,1,0)
        self.Scale=100;self.overrides={};self.locked=0
    def SetElementOverrides(self,eid,override):self.overrides[eid]=override
    def SaveOrientationAndLock(self):self.IsLocked=True;self.locked+=1
class View3D(View):pass
class Schedule(View):pass
class Graphics:
    def SetProjectionLineColor(self,color):self.color=color;return self
    def SetCutLineColor(self,color):return self
    def SetSurfaceTransparency(self,value):return self
    def SetSurfaceForegroundPatternId(self,value):return self
    def SetSurfaceForegroundPatternColor(self,value):return self
    def SetCutForegroundPatternId(self,value):return self
    def SetCutForegroundPatternColor(self,value):return self
class Transaction:
    def __init__(self,*args,**kw):pass
    def __enter__(self):return self
    def __exit__(self,*args):return False


@pytest.mark.parametrize('separation,expected_notes',[(2,1),(100,2)])
def test_labels_are_grouped_idempotent_and_removed_only_after_closure(separation,expected_notes):
    path=Path(__file__).parents[1]/'lib/lowlife/opening_tasks_remark_views.py'
    tree=ast.parse(path.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='sync')
    view=View3D('view');foreign=View3D('foreign')
    elements={'view':view,'foreign':foreign,'user-note':NS(metadata={'role':'user'})}
    for name,x in [('box1',0),('box2',separation)]:
        elements[name]=NS(Id=name,UniqueId=name,get_BoundingBox=lambda view,x=x:[Point(x,0,0),Point(x+1,1,1)])
    registry={'control_views':{'P/view':view.UniqueId,'OTHER/view':foreign.UniqueId}}
    doc=NS(GetElement=lambda uid:elements.get(uid),GetDefaultElementTypeId=lambda group:'text-type')
    doc.registry=registry
    deleted=[];created=[]
    def delete(uid):deleted.append(uid);elements.pop(uid)
    doc.Delete=delete
    def create(doc,view_id,pos,text,type_id):
        uid='note'+str(len(created))
        note=NS(Id=uid,UniqueId=uid,text=text,leaders=[])
        def leader(kind):
            value=NS();note.leaders.append(value);return value
        note.AddLeader=leader;elements[uid]=note;created.append(note);return note
    store=NS(read=lambda el:getattr(el,'metadata',{}),write=lambda el,value:setattr(el,'metadata',value),
             save_registry=lambda doc,value:setattr(doc,'registry',value))
    ns=dict(copy=copy,core=core,store=store,boxes=NS(ft=lambda v:v/304.8,_box_points=lambda bbox:bbox),
            TagItem=TagItem,find_clusters=find_clusters,layout=layout,rect_union=rect_union,View=View,View3D=View3D,ViewSchedule=Schedule,
            FillPatternElement=object,FilteredElementCollector=lambda doc,view_id=None:NS(OfClass=lambda cls:[NS(Id=1,GetFillPattern=lambda:NS(IsSolidFill=True))],WhereElementIsNotElementType=lambda:NS(ToElementIds=lambda:['box1','box2'])),
            ElementTypeGroup=NS(TextNoteType='text'),ElementId=NS(InvalidElementId=-1),
            revit=NS(Transaction=Transaction),TextNote=NS(Create=create),TextNoteLeaderTypes=NS(TNLT_STRAIGHT_R=1,TNLT_STRAIGHT_L=2),
            OverrideGraphicSettings=Graphics,Color=lambda *args:args,tr=lambda ru,en=None:en or ru)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    rows=[dict(uid=name,remark_group_id='group',remark_number='KR-001',remark_state='correction',feedback_available=True)
          for name in ['box1','box2']]
    ns['sync'](doc,'P',rows,doc.registry)
    assert len(created)==expected_notes and sum(len(n.leaders) for n in created)==2
    assert view.locked==1 and not foreign.overrides
    assert all('На исправление' in note.text for note in created)
    ns['sync'](doc,'P',rows,doc.registry)
    assert len(created)==expected_notes and not deleted
    # View creation and window refresh use different presentation fields, but
    # unchanged box geometry/stage must not recreate the same labels.
    formatted=[dict(row,sizes='500 x 300',displacement='0 / 0 / 0',status='Issued') for row in rows]
    ns['sync'](doc,'P',formatted,doc.registry)
    assert len(created)==expected_notes and not deleted
    offline=[dict(row,feedback_available=False) for row in rows]
    ns['sync'](doc,'P',offline,doc.registry)
    assert not deleted
    reviewed=[dict(row,remark_state='review') for row in rows]
    ns['sync'](doc,'P',reviewed,doc.registry)
    assert all('Исправлено' in note.text for note in created[expected_notes:])
    closed=[dict(row,remark_state='closed') for row in rows]
    ns['sync'](doc,'P',closed,doc.registry)
    assert doc.registry['remark_view_states']['P']['notes']==[]
    assert 'user-note' in elements
    assert all(uid.startswith('note') for uid in deleted)
