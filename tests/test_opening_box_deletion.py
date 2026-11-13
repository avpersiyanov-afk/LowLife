"""Atomic validated deletion; no registry/history writes and no foreign boxes."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import pytest

ROOT=Path(__file__).parents[1]


def test_only_original_local_boxes_are_deleted_as_one_batch():
    path=ROOT/'lib/lowlife/opening_tasks_revit.py'
    fn=next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='delete_boxes')
    fn.body=[n for n in fn.body if not isinstance(n,ast.ImportFrom)]
    deleted=[]
    doc=NS(Delete=lambda ids:deleted.append(ids))
    class Generic:
        def __class_getitem__(cls,t):return list
    ns=dict(List=Generic,ElementId=int,metadata=lambda el:el.data,tr=lambda ru,en=None:en or ru)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'delete', 'exec'),ns)
    delete=ns['delete_boxes']
    a=NS(Id=1,UniqueId='a',Document=doc,data=dict(owner_uid='a'))
    b=NS(Id=2,UniqueId='b',Document=doc,data=dict(owner_uid='b'))
    assert delete(doc,[a,a,b])==2
    assert deleted==[[1,2]]
    assert delete(doc,[])==0
    for invalid in [NS(Id=3,UniqueId='copy',Document=doc,data=dict(owner_uid='a')),
                    NS(Id=4,UniqueId='foreign',Document=object(),data=dict(owner_uid='foreign')),
                    NS(Id=5,UniqueId='other',Document=doc,data=None)]:
        with pytest.raises(ValueError):delete(doc,[a,invalid])
    assert deleted==[[1,2]]  # validation of whole selection precedes mutation


def test_cancelled_deletion_does_not_start_a_transaction():
    path=ROOT/'lib/lowlife/opening_tasks_ui.py'
    fn=next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='delete_boxes_from_list')
    inst=NS(Id=1,UniqueId='box')
    doc=NS(GetElement=lambda uid:inst)
    def unexpected(*args):
        raise AssertionError('cancelled deletion must not write')
    selected=[inst]
    scope=dict(api=NS(metadata=lambda el:dict(owner_uid='box',task_id='task'),delete_boxes=unexpected),
               boxes=NS(_id_int=int),choose=lambda *args:selected,
               forms=NS(alert=lambda *args,**kw:False),revit=NS(Transaction=unexpected),
               tr=lambda ru,en=None:en or ru,unicode=str)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'delete-ui','exec'),scope)
    scope['delete_boxes_from_list'](NS(Document=doc),[dict(uid='box')])
    selected[:]=[]
    scope['delete_boxes_from_list'](NS(Document=doc),[dict(uid='box')])


def test_preselected_table_rows_skip_picker_and_model_wide_scan():
    path=ROOT/'lib/lowlife/opening_tasks_ui.py'
    fn=next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='delete_boxes_from_list')
    boxes=[NS(Id=1,UniqueId='a'),NS(Id=2,UniqueId='b')]
    doc=NS(GetElement=lambda uid:next(b for b in boxes if b.UniqueId==uid))
    calls=[]
    def unexpected(*args):raise AssertionError('preselected rows need no second picker/collector')
    class Tx:
        def __init__(self,title):pass
        def __enter__(self):calls.append('transaction')
        def __exit__(self,*args):pass
    scope=dict(api=NS(metadata=lambda el:dict(owner_uid=el.UniqueId,task_id=el.UniqueId),
                      delete_boxes=lambda doc,selected:calls.append([b.Id for b in selected])),
               boxes=NS(_id_int=int),choose=unexpected,FilteredElementCollector=unexpected,
               forms=NS(alert=lambda message,**kw:calls.append(message) or True),
               revit=NS(Transaction=Tx),tr=lambda ru,en=None:en or ru,unicode=str)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'delete-selected','exec'),scope)
    scope['delete_boxes_from_list'](NS(Document=doc),[dict(uid='a'),dict(uid='b')])
    assert 'IDs: 1, 2' in calls[0]
    assert calls[1:]==['transaction',[1,2]]


def test_empty_table_selection_still_opens_box_picker():
    path=ROOT/'lib/lowlife/opening_tasks_ui.py'
    fn=next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='delete_boxes_from_list')
    el=NS(Id=1,UniqueId='a')
    calls=[]
    scope=dict(api=NS(FamilyInstance=object,metadata=lambda inst:dict(owner_uid='a',task_id='task')),
               boxes=NS(_id_int=int),FilteredElementCollector=lambda doc:NS(OfClass=lambda cls:[el]),
               choose=lambda *args:calls.append('picker') or [],tr=lambda ru,en=None:en or ru)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'delete-unselected','exec'),scope)
    scope['delete_boxes_from_list'](NS(Document=None),[])
    assert calls==['picker']
