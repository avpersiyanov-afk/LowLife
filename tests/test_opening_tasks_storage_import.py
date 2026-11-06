# -*- coding: utf-8 -*-
"""Import smoke check with the Revit API namespace boundary reproduced explicitly."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType


def test_storage_imports_datastorage_from_extensible_storage(monkeypatch):
    system=ModuleType('System')
    system.Guid=lambda value:value
    system.String=str
    db=ModuleType('Autodesk.Revit.DB')
    db.FilteredElementCollector=object
    db.StorageType=object
    ext=ModuleType('Autodesk.Revit.DB.ExtensibleStorage')
    class DataStorage:
        pass
    ext.DataStorage=DataStorage
    for name in ('Schema','SchemaBuilder','AccessLevel','Entity'):
        setattr(ext,name,object)
    monkeypatch.setitem(sys.modules,'System',system)
    monkeypatch.setitem(sys.modules,'Autodesk.Revit.DB',db)
    monkeypatch.setitem(sys.modules,'Autodesk.Revit.DB.ExtensibleStorage',ext)
    path=Path(__file__).parents[1]/'lib/lowlife/opening_tasks_storage.py'
    spec=importlib.util.spec_from_file_location('_opening_storage_import_check',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.DataStorage is DataStorage
