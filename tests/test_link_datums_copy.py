# -*- coding: utf-8 -*-
"""Native monitoring guards and settings rollback with an API substitute."""
import sys
import types
import pytest
from lowlife import link_datums_copy as copy, link_datums_core as core


def row(status=core.MISSING_IN_MODEL, id_=2):
    return core.Row(None, dict(name='L2', id=id_, id_int=id_), status)


def test_candidates_exclude_existing_pairs():
    missing = row()
    assert copy.missing_rows([row(core.OK), row(core.MOVED), row(core.RENAMED), missing], []) == [('level', missing)]


@pytest.fixture
def api(monkeypatch):
    state = types.SimpleNamespace(transactions=[], monitored=True, links=[10], fail=False)

    class TargetType(object):
        Id = 25

    class Element(object):
        Id = 100
        Pinned = False
        type_id = 1
        workset_id = None

        def IsMonitoringLinkElement(self):
            return state.monitored

        def GetMonitoredLinkElementIds(self):
            return state.links

        def ChangeTypeId(self, id_):
            self.type_id = id_
            return -1

    state.element = Element()

    class Transaction(object):
        def __init__(self, doc, name):
            self.status = None
            state.transactions.append(self)

        def Start(self):
            self.status = 'started'
            self.snapshot = dict(state.element.__dict__)

        def Commit(self):
            self.status = 'committed'
            return self.status

        def GetStatus(self):
            return self.status

        def RollBack(self):
            self.status = 'rolled_back'
            state.element.__dict__.clear()
            state.element.__dict__.update(self.snapshot)

        def Dispose(self):
            pass

    db = types.SimpleNamespace(LevelType=TargetType, GridType=TargetType, Transaction=Transaction,
        ElementId=types.SimpleNamespace(InvalidElementId=-1),
        TransactionStatus=types.SimpleNamespace(Started='started', Committed='committed'))
    revit = types.ModuleType('Autodesk.Revit')
    revit.DB = db
    monkeypatch.setitem(sys.modules, 'Autodesk', types.ModuleType('Autodesk'))
    monkeypatch.setitem(sys.modules, 'Autodesk.Revit', revit)
    source = row()
    paired = core.Row(dict(name='L2', id=100, id_int=100), source.link, core.OK)
    collector = types.ModuleType('lowlife.link_datums')
    collector.compare = lambda doc, link, tolerance: ([paired], [])
    monkeypatch.setitem(sys.modules, 'lowlife.link_datums', collector)
    import lowlife
    monkeypatch.setattr(lowlife, 'link_datums', collector, raising=False)
    worksets = types.ModuleType('lowlife.fire_boxes')

    def assign(element, id_):
        if state.fail:
            raise ValueError('workset denied')
        element.workset_id = id_

    worksets.assign_workset = assign
    monkeypatch.setitem(sys.modules, 'lowlife.fire_boxes', worksets)
    state.doc = types.SimpleNamespace(GetElement=lambda id_: state.element)
    state.link = types.SimpleNamespace(Id=10)
    state.choices = [('level', source, TargetType(), 9)]
    return state


def test_configures_only_native_copy(api):
    ids, errors = copy.configure_copies(api.doc, api.link, api.choices, set(), 1)
    assert ids == [100] and not errors
    assert (api.element.type_id, api.element.workset_id, api.element.Pinned) == (25, 9, True)


@pytest.mark.parametrize('monitored,links,existing', [(False, [10], set()), (True, [99], set()), (True, [10], {100})])
def test_unmonitored_wrong_link_or_existing_elements_are_untouched(api, monitored, links, existing):
    api.monitored, api.links = monitored, links
    ids, errors = copy.configure_copies(api.doc, api.link, api.choices, existing, 1)
    assert not ids and errors
    assert not api.transactions and api.element.type_id == 1


def test_failed_settings_preserve_native_copy(api):
    api.fail = True
    ids, errors = copy.configure_copies(api.doc, api.link, api.choices, set(), 1)
    assert not ids and errors
    assert api.element.type_id == 1 and api.monitored
    assert api.transactions[0].status == 'rolled_back'
