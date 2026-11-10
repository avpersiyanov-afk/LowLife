"""Atomic validated deletion; no registry/history writes and no foreign boxes."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import pytest

ROOT=Path(__file__).parents[1]


def test_only_original_local_boxes_are_deleted_as_one_batch():
    path=ROOT/'lib/lowlife/opening_tasks_revit.py'
    fn=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='delete_boxes')
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
    fn=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='delete_boxes_from_list')
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
