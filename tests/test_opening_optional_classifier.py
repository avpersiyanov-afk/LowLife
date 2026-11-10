import ast
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from lowlife import tray_boxes_core as core

ROOT=Path(__file__).parents[1]


@pytest.mark.parametrize('parameter',[None,NS(IsReadOnly=True,StorageType='text'),NS(IsReadOnly=False,StorageType='number')])
def test_unavailable_optional_classification_does_not_warn_or_write(parameter):
    tree=ast.parse((ROOT/'lib/lowlife/tray_boxes.py').read_text())
    fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_set_host_filter')
    scope=dict(core=core,StorageType=NS(String='text'),tr=lambda ru,en=None:en or ru)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'classification','exec'),scope)
    placer=NS(settings={'box_host_filter_param':'Inherited unused name'},result=NS(filter_errors=[]))
    instance=NS(LookupParameter=lambda name:parameter)
    scope['_set_host_filter'](placer,instance,'wall',required=False)
    assert placer.result.filter_errors==[]
    # The old tray button's required/default path retains validation.
    scope['_set_host_filter'](placer,instance,'wall')
    assert len(placer.result.filter_errors)==1


def test_explicit_valid_classification_still_writes_wall_and_floor():
    tree=ast.parse((ROOT/'lib/lowlife/tray_boxes.py').read_text())
    fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_set_host_filter')
    scope=dict(core=core,StorageType=NS(String='text'),tr=lambda ru,en=None:en or ru)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'classification','exec'),scope)
    writes=[]
    param=NS(IsReadOnly=False,StorageType='text',Set=lambda value:writes.append(value) or True)
    placer=NS(settings={'box_host_filter_param':'Explicit classification'},result=NS(filter_errors=[]))
    for kind in ('wall','floor'):
        scope['_set_host_filter'](placer,NS(LookupParameter=lambda name:param),kind,required=False)
    assert writes==[u'стена',u'перекрытие'] and placer.result.filter_errors==[]
