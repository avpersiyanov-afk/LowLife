"""Exercise actual storage roundtrip and narrowly scoped preview recovery."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from lowlife import opening_tasks_core as core

ROOT=Path(__file__).parents[1]


class GenericMethod:
    def __init__(self, fn):self.fn=fn
    def __getitem__(self, key):return self.fn


class Entity:
    def __init__(self, schema=None):
        self.text=None
        self.Get=GenericMethod(lambda field:self.text)
        self.Set=GenericMethod(lambda field,value:setattr(self,'text',value))
    def IsValid(self):return self.text is not None


def storage():
    tree=ast.parse((ROOT/'lib/lowlife/opening_tasks_storage.py').read_text(encoding='utf-8'))
    tree.body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('read','write')]
    ns=dict(core=core,json=json,String=str,unicode=str,Entity=Entity,
            schema=lambda:NS(GetField=lambda name:name))
    exec(compile(tree,'storage','exec'),ns)
    return ns


def configuration():
    tree=ast.parse((ROOT/'lib/lowlife/opening_tasks_focus.py').read_text(encoding='utf-8'))
    node=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='configuration')
    ns=dict(api=NS(core=core),inst=NS(UniqueId='box'),source=NS(UniqueId='route'),
            link=NS(UniqueId='link'),structure=None)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'focus-config','exec'),ns)
    return ns['configuration']


def test_preview_configuration_roundtrips_and_legacy_view_is_repaired():
    ns=storage()
    current=configuration()
    legacy=dict(current)
    del legacy['schema']
    entity=Entity();entity.text=json.dumps(legacy)
    element=NS(GetEntity=lambda schema:entity,SetEntity=lambda value:setattr(entity,'text',value.text))
    assert ns['read'](element) is None  # only view config is rebuilt, not the task
    ns['write'](element,current)
    assert ns['read'](element)==current
    assert current['schema']==core.VERSION and current['version']==2


@pytest.mark.parametrize('value',[{},dict(role='draft'),dict(schema=99,role='registry'),
    dict(schema=99,role='box_preview',version=2),dict(role='box_preview',version=3),[]])
def test_other_invalid_formats_still_raise_and_are_never_written(value):
    ns=storage()
    entity=Entity();entity.text=json.dumps(value)
    writes=[]
    element=NS(GetEntity=lambda schema:entity,SetEntity=writes.append)
    with pytest.raises(ValueError):ns['read'](element)
    with pytest.raises(ValueError):ns['write'](element,value)
    assert not writes
