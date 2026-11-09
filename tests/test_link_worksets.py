# -*- coding: utf-8 -*-
"""Link reload boundaries: no-op, partial failures, paths and restrictions."""
import sys
from types import SimpleNamespace as Obj

import pytest

from lowlife import link_worksets as lw


@pytest.fixture
def model(monkeypatch):
    calls, configs = [], []

    class Config(object):
        def __init__(self, option):
            assert option == 'close-all'
            self.opened = []
            self.disposed = False
            configs.append(self)

        def Open(self, ids):
            self.opened = list(ids)

        def Dispose(self):
            self.disposed = True

    class Link(object):
        IsNestedLink = False
        def __init__(self, key):
            self.Id = key
            self.Name = 'model{}'.format(key)
            self.result = 'loaded'
            self.local = True
            self.loaded = True
            self.shared_positions = False
            self.multiple = False

        def IsNotLoadedIntoMultipleOpenDocuments(self):
            return not self.multiple

        def HasSaveablePositions(self):
            return self.shared_positions

        def IsExternalFileReference(self):
            return self.local

        def GetExternalFileReference(self):
            return Obj(GetAbsolutePath=lambda: 'absolute-source')

        def GetExternalResourceReference(self, kind):
            assert kind == 'rvt'
            return 'external-resource'

        def LoadFrom(self, path, config):
            assert not doc.IsModifiable
            calls.append((self.Id, path, config.opened))
            if self.result == 'exception':
                raise RuntimeError('reload error')
            return Obj(LoadResult=self.result, Dispose=lambda: None)

    links = {key: Link(key) for key in (1, 2, 3)}
    doc = Obj(IsModifiable=False, IsReadOnly=False, IsFamilyDocument=False,
              GetElement=links.get)
    db = Obj(WorksetConfiguration=Config,
             LinkLoadResultType=Obj(LinkLoaded='loaded'),
             WorksetConfigurationOption=Obj(CloseAllWorksets='close-all'), WorksetId=int,
             RevitLinkType=Obj(IsLoaded=lambda doc, key: links[key].loaded),
             ExternalResourceTypes=Obj(BuiltInExternalResourceTypes=Obj(RevitLink='rvt')))
    monkeypatch.setitem(sys.modules, 'Autodesk.Revit', Obj(DB=db))
    monkeypatch.setitem(sys.modules, 'System.Collections.Generic', Obj(List=list))
    monkeypatch.setattr(lw, 'safe_name', lambda element: element.Name)
    rows = [dict(type_id=key, name=links[key].Name, reason=None,
                 worksets=[dict(id=10, name='A', opened=True),
                           dict(id=20, name='B', opened=False)]) for key in links]
    return Obj(doc=doc, rows=rows, links=links, calls=calls, configs=configs)


def test_unchanged_links_do_not_reload_or_clear_undo(model):
    assert lw.apply(model.doc, [(model.rows[0], [10])]) == ([], [])
    assert model.calls == model.configs == []


def test_close_and_reopen_specific_worksets_with_original_path(model):
    changed, errors = lw.apply(model.doc, [(model.rows[0], [20])])
    assert changed == ['model1'] and not errors
    assert model.calls == [(1, 'absolute-source', [20])]
    assert model.configs[0].disposed


def test_close_all_keeps_link_loaded(model):
    assert lw.apply(model.doc, [(model.rows[0], [])]) == (['model1'], [])
    assert model.calls == [(1, 'absolute-source', [])]


def test_external_resource_keeps_its_reference(model):
    model.links[1].local = False
    lw.apply(model.doc, [(model.rows[0], [10, 20])])
    assert model.calls == [(1, 'external-resource', [10, 20])]


@pytest.mark.parametrize('failure', ['failed', 'exception'])
def test_partial_failure_reports_and_continues_without_rollback(model, failure):
    model.links[2].result = failure
    changed, errors = lw.apply(model.doc, [(row, [20]) for row in model.rows])
    assert changed == ['model1', 'model3']
    assert len(errors) == 1 and 'model2' in errors[0]
    assert all(config.disposed for config in model.configs)


@pytest.mark.parametrize('flag', ['IsModifiable', 'IsReadOnly', 'IsFamilyDocument'])
def test_document_guards_run_before_any_reload(model, flag):
    setattr(model.doc, flag, True)
    with pytest.raises(ValueError):
        lw.apply(model.doc, [(model.rows[0], [20])])
    assert not model.calls


@pytest.mark.parametrize('flag', ['IsNestedLink', 'multiple', 'shared_positions'])
def test_restrictions_rechecked_before_reload(model, flag):
    setattr(model.links[1], flag, True)
    changed, errors = lw.apply(model.doc, [(model.rows[0], [20])])
    assert not changed and len(errors) == 1 and not model.calls


def test_unknown_ids_and_unloaded_links_are_not_reloaded(model):
    model.links[2].loaded = False
    changed, errors = lw.apply(model.doc, [(model.rows[0], [99]), (model.rows[1], [20])])
    assert not changed and len(errors) == 2 and not model.calls


def test_collection_groups_instances_and_includes_closed_worksets(model, monkeypatch):
    worksets = [Obj(Id=10, Name='A', IsOpen=True), Obj(Id=20, Name='B', IsOpen=False)]
    linked = Obj(IsWorkshared=True)
    instances = [Obj(GetTypeId=lambda key=key: key, GetLinkDocument=lambda: linked)
                 for key in (1, 1, 2)]
    monkeypatch.setitem(sys.modules, 'lowlife.linked_elements',
                        Obj(loaded_links=lambda doc: instances))
    monkeypatch.setitem(sys.modules, 'lowlife.cable_tray',
                        Obj(find_worksets=lambda doc, name: worksets))
    model.links[2].IsNestedLink = True
    rows = lw.collect_rows(model.doc)
    assert len(rows) == 2 and rows[0]['instances'] == 2
    assert [w['opened'] for w in rows[0]['worksets']] == [True, False]
    assert rows[0]['reason'] is None and rows[1]['reason']
    linked.IsWorkshared = False
    assert all(r['reason'] and not r['worksets'] for r in lw.collect_rows(model.doc))
