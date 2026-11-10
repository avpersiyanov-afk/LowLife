# -*- coding: utf-8 -*-
"""Text destinations with an API substitute; no Revit model is modified."""
import ast
import base64
import json
import re
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from lowlife import spellcheck_core as core
from lowlife.cloud_io import dumps_ascii


class Parameter:
    def __init__(self, text, name='Description', readonly=False, storage='string'):
        self.text = text
        self.Definition = NS(Name=name)
        self.StorageType = storage
        self.IsReadOnly = readonly
        self.HasValue = bool(text)
        self.writes = []

    def AsString(self):
        return self.text

    def Set(self, text):
        self.writes.append(text)
        self.text = text
        return True


class Element:
    def __init__(self, eid, parameters=(), type_id=None, group=-1, category='annotation'):
        self.Id, self.Parameters, self.GroupId = eid, list(parameters), group
        self.type_id = type_id
        self.Category = NS(Id=category)

    def GetTypeId(self):
        return self.type_id

    def get_Parameter(self, key):
        assert key == 'sheet_name'
        return self.Parameters[0]


class Note(Element):
    Text = 'Text note'


class FamilyInstance(Element):
    pass


class Sheet(Element):
    pass


class Schedule(Element):
    IsTemplate = False
    IsTitleblockRevisionSchedule = False

    def __init__(self, eid, text='Manual text', rows=2):
        Element.__init__(self, eid)
        self.UniqueId = 'schedule-' + str(eid)
        self.Definition = NS()
        self.texts = {(0, 0): text, (1, 0): 'Other text'}
        self.span = NS(Top=0, Left=0, Bottom=0, Right=0)
        self.header = NS(NumberOfRows=rows, NumberOfColumns=1,
                         FirstRowNumber=0, LastRowNumber=rows-1,
                         FirstColumnNumber=0, LastColumnNumber=0,
                         GetMergedCell=self.merged, SetCellText=self.write)

    def merged(self, r, c):
        return self.span if r == 0 else NS(Top=r, Left=c, Bottom=r, Right=c)

    def write(self, r, c, text):
        self.texts[r, c] = text

    def GetTableData(self):
        return NS(GetSectionData=lambda section: self.header)

    def GetCellText(self, section, r, c):
        return self.texts[r, c]


class ScheduleInstance(Element):
    pass


@pytest.fixture
def api():
    root = Path(__file__).parents[1] / 'lib/lowlife'
    storage = NS(String='string', Integer='int', Double='double', ElementId='id')
    ns = dict(core=core, tr=lambda ru, en=None: ru, unicode=str,
              TextNote=Note, FamilyInstance=FamilyInstance, ViewSheet=Sheet,
              StorageType=storage, BuiltInParameter=NS(SHEET_NAME='sheet_name'),
              BuiltInCategory=NS(OST_TitleBlocks='titleblock', OST_GenericAnnotation='annotation'),
              ViewSchedule=Schedule, ScheduleSheetInstance=ScheduleInstance,
              SectionType=NS(Header='header'),
              safe_name=lambda el: 'element '+str(el.Id), base64=base64, json=json, re=re,
              dumps_ascii=dumps_ascii)
    class ElementId:
        InvalidElementId = -1
        def __new__(cls, value):
            return value
    ns['ElementId'] = ElementId
    schedule_ns = dict(ns)
    tree = ast.parse((root / 'schedule_excel.py').read_text(encoding='utf-8'))
    body = [node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Assign))]
    exec(compile(ast.Module(body=body, type_ignores=[]), 'schedule_excel.py', 'exec'), schedule_ns)
    ns['schedule_excel'] = NS(**schedule_ns)
    for filename in ('params.py', 'spellcheck.py'):
        tree = ast.parse((root / filename).read_text(encoding='utf-8'))
        body = [node for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Assign))]
        exec(compile(ast.Module(body=body, type_ignores=[]), filename, 'exec'), ns)

    def model(elements, visible=()):
        doc = NS(IsWorkshared=False)
        doc.GetElement = lambda eid: next((e for e in elements
                                          if eid is not None and (e.Id == eid or getattr(e, 'UniqueId', None) == eid)), None)
        for e in elements:
            e.Document = doc

        class Collector:
            def __init__(self, document, view_id=None):
                assert document is doc
                self.elements = [e for e in elements if view_id is None or e.Id in visible]

            def OfClass(self, cls):
                self.elements = [e for e in self.elements if isinstance(e, cls)]
                return self

            def WhereElementIsNotElementType(self):
                return self

            def OfCategory(self, category):
                self.elements = [e for e in self.elements if e.Category.Id == category]
                return self

            def __iter__(self):
                return iter(self.elements)

        ns['FilteredElementCollector'] = Collector
        schedule_ns['FilteredElementCollector'] = Collector
        schedule_ns['schedule_name'] = lambda el: str(el.Id)
        return doc

    return NS(**ns), model, ns


def test_model_excludes_equipment_before_reading_parameters(api):
    sc, model, ns = api
    typ = Element(10, [Parameter('Type text'), Parameter('Read only', readonly=True),
                       Parameter('42'), Parameter('23', storage='int')])
    unplaced = Element(11, [Parameter('Unplaced text')])
    equipment = FamilyInstance(20, category='equipment')
    del equipment.Parameters  # Reading equipment parameters must never happen.
    doc = model([Note(1), Sheet(2, [Parameter('Sheet name')]),
                 FamilyInstance(3, [Parameter('Instance text')], 10),
                 FamilyInstance(4, [], 10), typ, unplaced, equipment])
    targets = sc.collect_targets(doc, sc.SCOPE_MODEL, kinds=['note', 'sheet', 'annotation'])
    assert [(t.kind, t.Id) for t in targets] == [
        ('note', 1), ('sheet', 2), ('instance', 3), ('type', 10)]
    assert [sc.plain_text(t) for t in targets] == [
        'Text note', 'Sheet name', 'Instance text', 'Type text']


def test_selection_and_view_do_not_expand_to_other_instances(api):
    sc, model, ns = api
    typ = Element(10, [Parameter('Shared type text')])
    first = FamilyInstance(1, [Parameter('Visible text')], 10)
    second = FamilyInstance(2, [Parameter('Hidden text')], 10)
    doc = model([first, second, typ], visible=[1])
    for scope, selected in [(sc.SCOPE_SELECTION, [first]), (sc.SCOPE_VIEW, [])]:
        targets = sc.collect_targets(doc, scope, NS(Id=99), selected, ['annotation'])
        assert [(t.kind, t.Id) for t in targets] == [('instance', 1), ('type', 10)]
    assert sc.collect_targets(doc, sc.SCOPE_SELECTION, selected=[], kinds=['annotation']) == []


def test_sheet_scope_uses_active_sheet_only(api):
    sc, model, ns = api
    sheets = [Sheet(1, [Parameter('First sheet')]), Sheet(2, [Parameter('Second sheet')])]
    doc = model(sheets)
    assert [t.Id for t in sc.collect_targets(doc, sc.SCOPE_VIEW, sheets[1], kinds=['sheet'])] == [2]
    assert sc.collect_targets(doc, sc.SCOPE_VIEW, NS(Id=99), kinds=['sheet']) == []
    assert [t.Id for t in sc.collect_targets(doc, sc.SCOPE_SELECTION,
            selected=[sheets[0]], kinds=['sheet'])] == [1]


def test_titleblocks_filter_selection_and_model(api):
    sc, model, ns = api
    stamp = FamilyInstance(1, [Parameter('Stamp text')], category='titleblock')
    annotation = FamilyInstance(2, [Parameter('Annotation text')])
    doc = model([stamp, annotation])
    for scope in [sc.SCOPE_MODEL, sc.SCOPE_SELECTION]:
        targets = sc.collect_targets(doc, scope, selected=[stamp, annotation], kinds=['titleblock'])
        assert [t.Id for t in targets] == [1]


def test_manual_header_uses_existing_snapshot_import(api):
    sc, model, ns = api
    schedule = Schedule(1)
    ordinary = Schedule(2, rows=1)
    doc = model([schedule, ordinary])
    targets = sc.collect_targets(doc, sc.SCOPE_MODEL, kinds=['schedule'])
    assert [sc.plain_text(t) for t in targets] == ['Manual text', 'Other text']
    assert sc.apply_fix(targets[0], 'Manual text', 'Corrected text') == sc.APPLIED_PARAMETER
    assert schedule.texts == {(0, 0): 'Corrected text', (1, 0): 'Other text'}


@pytest.mark.parametrize('change', ['rows', 'merge', 'text'])
def test_manual_cell_changes_are_rejected(api, change):
    sc, model, ns = api
    schedule = Schedule(1)
    doc = model([schedule])
    target = sc.collect_targets(doc, sc.SCOPE_MODEL, kinds=['schedule'])[0]
    if change == 'rows':
        schedule.header.NumberOfRows += 1
    elif change == 'merge':
        schedule.span.Bottom = 1
    else:
        schedule.texts[0, 0] = 'Changed externally'
    with pytest.raises(ValueError):
        sc.apply_fix(target, 'Manual text', 'Corrected text')
    assert schedule.texts[0, 0] != 'Corrected text'


def test_current_sheet_collects_each_placed_schedule_once(api):
    sc, model, ns = api
    sheet = Sheet(1)
    schedule = Schedule(2)
    first, second = ScheduleInstance(3), ScheduleInstance(4)
    first.ScheduleId = second.ScheduleId = 2
    doc = model([sheet, schedule, first, second], visible=[3, 4])
    targets = sc.collect_targets(doc, sc.SCOPE_VIEW, sheet, kinds=['schedule'])
    assert len(targets) == 2
    assert all(t.Id == 2 for t in targets)


def test_writes_exact_parameter_even_when_names_are_equal(api):
    sc, model, ns = api
    first, second = Parameter('Old text'), Parameter('Old text')
    owner = FamilyInstance(1, [first, second])
    model([owner])
    target = sc.TextTarget(owner, 'instance', second)
    assert sc.apply_fix(target, 'Old text', 'New text') == sc.APPLIED_PARAMETER
    assert first.writes == []
    assert second.writes == ['New text']


@pytest.mark.parametrize('block', ['changed', 'readonly', 'group', 'owned', 'central'])
def test_rechecks_destinations_before_writing(api, block):
    sc, model, ns = api
    p = Parameter('Old text')
    owner = FamilyInstance(1, [p])
    doc = model([owner])
    target = sc.TextTarget(owner, 'instance', p)
    if block == 'changed':
        p.text = 'Changed text'
    elif block == 'readonly':
        p.IsReadOnly = True
    elif block == 'group':
        owner.GroupId = 77
    else:
        doc.IsWorkshared = True
        ns.update(CheckoutStatus=NS(OwnedByOtherUser='owned'),
                  ModelUpdatesStatus=NS(UpdatedInCentral='central', DeletedInCentral='deleted'),
                  WorksharingUtils=NS(GetCheckoutStatus=lambda *args: block,
                                      GetModelUpdatesStatus=lambda *args: block))
    with pytest.raises(ValueError):
        sc.apply_fix(target, 'Old text', 'New text')
    assert p.writes == []


def test_shared_ai_item_keeps_distinct_destinations(api):
    sc, model, ns = api
    doc = model([Sheet(1, [Parameter('Same text')]),
                 FamilyInstance(2, [Parameter('Same text')])])
    targets = sc.collect_targets(doc, sc.SCOPE_MODEL, kinds=['sheet', 'annotation'])
    items = core.collect_items([(i, sc.plain_text(t)) for i, t in enumerate(targets)])
    assert len(items) == 1 and len(items[0]['notes']) == 2
    for i, old in items[0]['notes']:
        sc.apply_fix(targets[i], old, 'Fixed text')
    assert [sc.plain_text(t) for t in targets] == ['Fixed text', 'Fixed text']


@pytest.mark.parametrize('wrapped', [False, True])
def test_notes_keep_formatted_replacement_path(api, wrapped):
    sc, model, ns = api
    note = Note(1)
    model([note])
    state = {'text': 'Some typo text\r', 'writes': 0}
    formatted = NS(GetPlainText=lambda: state['text'])

    def replace(span, text):
        start, length = span
        state['text'] = state['text'][:start] + text + state['text'][start+length:]

    def write(value):
        assert value is formatted
        state['writes'] += 1

    formatted.SetPlainText = replace
    note.GetFormattedText = lambda: formatted
    note.SetFormattedText = write
    ns['TextRange'] = lambda start, length: (start, length)
    target = sc.TextTarget(note, 'note') if wrapped else note
    assert sc.apply_fix(target, 'Some typo text\r', 'Some type text\r') == sc.APPLIED_FORMATTED
    assert state == {'text': 'Some type text\r', 'writes': 1}
    assert note.Text == 'Text note'  # Whole-note fallback was not used.
