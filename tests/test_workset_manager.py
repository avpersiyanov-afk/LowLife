# -*- coding: utf-8 -*-
"""Rule conflicts, chained mapping and transactional rollback without Revit."""
import copy
import sys
import types

import pytest
from lowlife import workset_manager_core as core
from lowlife import workset_manager as api


def rule(action, source='', target=''):
    return dict(action=action, source=source, target=target)


def test_rule_order_capture_masks_and_no_op_creates():
    ops = core.plan(['AR_1', 'AR_2'], [rule('rename', 'AR_{part}', 'Architecture_{2}'),
        rule('create', target='Architecture_1'), rule('map', 'Architecture_*', 'Merged')])
    assert [op['action'] for op in ops] == ['rename', 'rename', 'create', 'map', 'map']
    assert ops[0]['target'] == 'Architecture_1'
    assert ops[-1]['source'] == 'Architecture_2'
    assert ops[-1]['target'] == 'Merged'


def test_existing_target_requires_map_and_never_deletes_worksets():
    with pytest.raises(ValueError):
        core.plan(['A', 'B'], [rule('rename', 'A', 'B')])
    assert core.plan(['A', 'B'], [rule('map', 'A', 'b')]) == [rule('map', 'A', 'B')]
    assert core.plan(['A'], [rule('map', 'A', 'a')]) == []


@pytest.mark.parametrize('rules', [None, {}, [None], [rule('delete', 'A', 'B')],
    [rule('map', '', 'B')], [rule('create', target='')], [rule('rename', '{', 'B')],
    [rule('create', target='Bad|name')], [rule('create', target='{unknown}')],
    [rule('rename', 'Missing', 'B')]])
def test_invalid_rules_are_rejected_before_writing(rules):
    with pytest.raises(ValueError):
        core.plan(['A'], rules)


@pytest.fixture
def model(monkeypatch):
    import lowlife
    from lowlife import link_views
    doc = types.SimpleNamespace(IsFamilyDocument=False, IsWorkshared=True,
        IsReadOnly=False, IsModifiable=False, worksets={1: 'A', 2: 'B'},
        elements={11: 1, 12: 1, 21: 2}, readonly=set(), transactions=[], closed=set())

    class Workset:
        def __init__(self, number):
            self.Id = number

        @property
        def Name(self):
            return doc.worksets[self.Id]

        @property
        def IsOpen(self):
            return self.Id not in doc.closed

        @staticmethod
        def Create(source, name):
            number = max(doc.worksets) + 1
            doc.worksets[number] = name
            return Workset(number)

    class Element:
        def __init__(self, number):
            self.Id = number

        def get_Parameter(self, parameter):
            return types.SimpleNamespace(IsReadOnly=self.Id in doc.readonly)

    class Collector:
        def __init__(self, source):
            self.workset_id = None

        def WherePasses(self, number):
            self.workset_id = number
            return self

        def WhereElementIsNotElementType(self):
            return self

        def __iter__(self):
            return iter(Element(number) for number, workset in doc.elements.items()
                        if workset == self.workset_id)

    class Transaction:
        def __init__(self, source, title):
            self.status = 'new'
            doc.transactions.append(self)

        def Start(self):
            self.before = (copy.copy(doc.worksets), copy.copy(doc.elements))
            self.status = 'started'

        def Commit(self):
            self.status = 'committed'
            return self.status

        def GetStatus(self):
            return self.status

        def RollBack(self):
            doc.worksets, doc.elements = self.before
            self.status = 'rolled_back'

        def Dispose(self):
            pass

    def rename(source, number, name):
        doc.worksets[number] = name

    db = types.ModuleType('Autodesk.Revit.DB')
    db.Workset = Workset
    db.WorksetTable = types.SimpleNamespace(RenameWorkset=rename,
        IsWorksetNameUnique=lambda source, name: name.lower() not in
        [value.lower() for value in doc.worksets.values()] and name != 'System')
    db.FilteredElementCollector = Collector
    db.ElementWorksetFilter = lambda number: number
    db.BuiltInParameter = types.SimpleNamespace(ELEM_PARTITION_PARAM=1)
    db.Transaction = Transaction
    db.TransactionStatus = types.SimpleNamespace(Started='started', Committed='committed')
    revit = types.ModuleType('Autodesk.Revit')
    revit.DB = db
    monkeypatch.setitem(sys.modules, 'Autodesk.Revit', revit)
    monkeypatch.setitem(sys.modules, 'Autodesk.Revit.DB', db)
    monkeypatch.setattr(lowlife, 'cable_tray', types.SimpleNamespace(
        find_worksets=lambda source, mask: [Workset(number) for number in doc.worksets]), raising=False)
    def assign(element, number):
        doc.elements[element.Id] = number
    monkeypatch.setattr(lowlife, 'fire_boxes', types.SimpleNamespace(assign_workset=assign), raising=False)
    monkeypatch.setitem(sys.modules, 'lowlife.cable_tray', lowlife.cable_tray)
    monkeypatch.setitem(sys.modules, 'lowlife.fire_boxes', lowlife.fire_boxes)
    return doc


def test_preview_is_read_only_and_chained_transfers_include_prior_members(model):
    before = copy.deepcopy((model.worksets, model.elements))
    preview = api.prepare(model, [rule('map', 'A', 'B'), rule('map', 'B', 'C')])
    maps = [op for op in preview['operations'] if op['action'] == 'map']
    assert [len(op['elements']) for op in maps] == [2, 3]
    assert (model.worksets, model.elements) == before
    assert model.transactions == []
    api.apply(model, preview)
    assert set(model.elements.values()) == {3}
    assert model.worksets == {1: 'A', 2: 'B', 3: 'C'}
    assert len(model.transactions) == 1


def test_rename_then_map_new_names_and_create_then_rename(model):
    preview = api.prepare(model, [rule('rename', 'A', 'AA'), rule('map', 'AA', 'C'),
        rule('create', target='D'), rule('rename', 'D', 'DD')])
    api.apply(model, preview)
    assert set(model.worksets.values()) == {'AA', 'B', 'C', 'DD'}


def test_readonly_member_closed_workset_and_reserved_names_block_preview(model):
    model.readonly.add(11)
    with pytest.raises(ValueError):
        api.prepare(model, [rule('map', 'A', 'B')])
    model.readonly.clear()
    model.closed.add(1)
    with pytest.raises(ValueError):
        api.prepare(model, [rule('rename', 'A', 'AA')])
    with pytest.raises(ValueError):
        api.prepare(model, [rule('create', target='System')])
    assert model.transactions == []


def test_stale_preview_rejected_before_transaction(model):
    preview = api.prepare(model, [rule('map', 'A', 'B')])
    model.elements[13] = 1
    with pytest.raises(ValueError):
        api.apply(model, preview)
    assert model.transactions == []


def test_recreated_workset_with_same_name_requires_new_preview(model):
    preview = api.prepare(model, [rule('rename', 'A', 'AA')])
    model.worksets[5] = model.worksets.pop(1)
    with pytest.raises(ValueError):
        api.apply(model, preview)
    assert model.transactions == []


def test_assignment_failure_rolls_back_creation_rename_and_all_moves(model, monkeypatch):
    import lowlife
    before = copy.deepcopy((model.worksets, model.elements))
    preview = api.prepare(model, [rule('rename', 'A', 'AA'), rule('map', 'AA', 'C')])
    def fail(element, number):
        model.elements[element.Id] = number
        raise ValueError('locked by another user')
    monkeypatch.setattr(lowlife.fire_boxes, 'assign_workset', fail)
    with pytest.raises(ValueError):
        api.apply(model, preview)
    assert (model.worksets, model.elements) == before
    assert model.transactions[0].status == 'rolled_back'
