# -*- coding: utf-8 -*-
"""Workset lookup and assignment guards without loading the Revit adapter."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from lowlife import fire_boxes_settings as cfg


def adapter(workshared=True):
    source = Path(__file__).parents[1] / 'lib/lowlife/fire_boxes.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    names = {'eid', 'workset_options', 'resolve_workset', 'assign_workset'}
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    first = SimpleNamespace(Name='Trays', Id=SimpleNamespace(IntegerValue=12))
    second = SimpleNamespace(Name='Enclosures', Id=SimpleNamespace(IntegerValue=23))

    class Collector:
        def OfKind(self, kind):
            return [first, second]

    db = SimpleNamespace(FilteredWorksetCollector=lambda doc: Collector(),
                         WorksetKind=SimpleNamespace(UserWorkset='user'),
                         BuiltInParameter=SimpleNamespace(ELEM_PARTITION_PARAM='partition'))
    scope = {'DB': db, 'unicode': str, 'tr': lambda ru, en: en}
    exec(compile(tree, str(source), 'exec'), scope)
    doc = SimpleNamespace(IsWorkshared=workshared,
                          GetWorksetTable=lambda: SimpleNamespace(GetActiveWorksetId=lambda: first.Id))
    return scope, doc


def test_workset_settings_migrate_and_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    old = cfg.normalize({'box_type_uid': 'example'})
    assert old['box_workset_name'] == old['tray_workset_name'] == ''
    old.update(box_workset_name='Enclosures', tray_workset_name='Trays')
    cfg.save(old)
    assert cfg.load() == old


def test_explicit_workset_and_active_default_are_distinct():
    api, doc = adapter()
    assert api['resolve_workset'](doc, 'Enclosures').IntegerValue == 23
    assert api['resolve_workset'](doc, '').IntegerValue == 12
    with pytest.raises(ValueError, match='was not found'):
        api['resolve_workset'](doc, 'Deleted set')


def test_non_workshared_model_ignores_saved_workset():
    api, doc = adapter(False)
    assert api['workset_options'](doc) == {}
    assert api['resolve_workset'](doc, 'Set from another model') is None
    api['assign_workset'](None, None)


@pytest.mark.parametrize('readonly,success', [(True, True), (False, False), (False, True)])
def test_assignment_failure_is_reported(readonly, success):
    api, doc = adapter()
    writes = []
    parameter = SimpleNamespace(IsReadOnly=readonly, Set=lambda value: writes.append(value) or success)
    element = SimpleNamespace(Id=SimpleNamespace(IntegerValue=99), get_Parameter=lambda key: parameter)
    workset = api['resolve_workset'](doc, 'Enclosures')
    if readonly or not success:
        with pytest.raises(ValueError, match='Could not assign'):
            api['assign_workset'](element, workset)
    else:
        api['assign_workset'](element, workset)
        assert writes == [23]


def test_missing_workset_parameter_is_reported():
    api, doc = adapter()
    element = SimpleNamespace(Id=SimpleNamespace(IntegerValue=99), get_Parameter=lambda key: None)
    with pytest.raises(ValueError, match='Could not assign'):
        api['assign_workset'](element, api['resolve_workset'](doc, 'Trays'))
