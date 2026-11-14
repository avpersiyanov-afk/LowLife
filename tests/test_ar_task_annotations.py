# -*- coding: utf-8 -*-
"""Contracts at the TextNote/equipment-layout boundary; no native Revit calls."""
import ast
import sys
from pathlib import Path
from types import SimpleNamespace as Obj

import pytest
from lowlife import ar_task_annotations_settings as config, tag_layout

ROOT = Path(__file__).parents[1]


def definitions(path, names, scope):
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
    tree.body = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                 and node.name in names]
    exec(compile(tree, str(path), 'exec'), scope)
    return scope


@pytest.fixture
def type_api(monkeypatch):
    monkeypatch.setitem(sys.modules, 'lowlife.equipment_tags', Obj(
        id_int=int, _safe_name=lambda symbol: symbol.name))


def symbol(family='Family', name='Type', category=10, element_id=1):
    return Obj(FamilyName=family, name=name, Category=Obj(Id=category), Id=element_id)


def test_type_mapping_survives_different_project_ids_and_distinguishes_types(type_api):
    a = symbol(family=u'Семейство : "А"', name=u'Тип 1')
    b = symbol(family=a.FamilyName, name=a.name, element_id=200)
    assert config.type_key(a) == config.type_key(b)
    assert config.type_key(a) != config.type_key(symbol(family=a.FamilyName, name='Other'))
    assert config.type_key(a) != config.type_key(symbol(family=a.FamilyName, name=a.name, category=11))


@pytest.mark.parametrize('category', [-2000170, 2 ** 40])
def test_type_key_normalizes_native_id_before_json_and_keeps_saved_keys(monkeypatch, category):
    import json
    class NativeInteger(object):
        def __int__(self):
            return category
    native_id = NativeInteger()
    # Like System.Int64 under IronPython: convertible to int, rejected by JSON.
    with pytest.raises(TypeError):
        json.dumps(native_id)
    monkeypatch.setitem(sys.modules, 'lowlife.equipment_tags', Obj(
        id_int=lambda value: value, _safe_name=lambda obj: obj.name))
    item = symbol(family=u'Семейство "А"', name=u'Тип\\1', category=native_id)
    expected = 'text:' + json.dumps([category, item.FamilyName, item.name], ensure_ascii=True)
    assert config.type_key(item) == expected
    assert config.text_for(item, {'selected_types': [expected], expected: u'Задание АР'}) == u'Задание АР'


def test_only_enabled_types_produce_text_and_line_breaks_are_preserved(type_api):
    sym = symbol()
    key = config.type_key(sym)
    settings = {key: u'Первая\\nВторая\r\nТретья'}
    assert config.text_for(sym, settings) == ''
    settings['selected_types'] = [key]
    assert config.text_for(sym, settings) == u'Первая\rВторая\rТретья'
    settings[key] = ''
    assert config.text_for(sym, settings) == ''


@pytest.mark.parametrize('categories,expected', [(None, [1, 2]), ([10], [1]), ([], [])])
def test_shared_type_collector_preserves_category_filter_and_includes_unplaced(categories, expected):
    families = [Obj(FamilyCategory=Obj(Id=10), GetFamilySymbolIds=lambda: [1]),
                Obj(FamilyCategory=Obj(Id=20), GetFamilySymbolIds=lambda: [2]),
                Obj(FamilyCategory=None)]
    scope = dict(ElementId=int, Family='family',
                 FilteredElementCollector=lambda doc: Obj(OfClass=lambda cls: families))
    definitions('lib/lowlife/scs_settings.py', ['list_symbols_by_categories'], scope)
    result = scope['list_symbols_by_categories'](Obj(GetElement=lambda eid: eid), categories)
    assert result == expected


def test_settings_are_isolated_and_invalid_distances_use_common_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    config.STORE.write({'offset_mm': -3, 'gap_mm': 'bad', 'selected_types': []})
    saved = config.load()
    assert saved['offset_mm'] == 3
    assert saved['gap_mm'] == 1
    assert saved['selected_types'] == []


def test_type_selection_uses_checked_rows_from_active_plan(type_api):
    # Execute the real settings flow against the list/window boundary.
    scope = dict(config.__dict__)
    a, b = symbol(name='A'), symbol(name='B', element_id=2)
    for item in (a, b):
        item.Category.CategoryType = 'model'
        item.Category.Name = 'Category'
    class Option(object):
        def __init__(self, label, checked=False):
            self.name, self.state = label, checked
    saved = {'selected_types': []}
    class Editor(object):
        last = None
        def __init__(self, *args, **kwargs):
            Editor.last = self
            self.fields = args[4]
        def load_saved_values(self):
            return {}
        def show_settings_form(self, values):
            keys = [field.key for field in self.fields if field.key.startswith('text:')]
            assert keys == [config.type_key(b)]
            return {keys[0]: 'Task', 'text_type_name': 'Text'}
    def show(options, **kwargs):
        assert kwargs['return_all'] is True
        options[1].state = True
        return options
    # Imports are scoped so no API substitutes leak into the remaining suite.
    db = Obj(CategoryType=Obj(Model='model'), TextNoteType=object,
             FilteredElementCollector=lambda doc: Obj(OfClass=lambda cls: [Obj(name='Text')]))
    from unittest.mock import patch
    with patch.dict(sys.modules, {
            'Autodesk': Obj(), 'Autodesk.Revit': Obj(), 'Autodesk.Revit.DB': db,
            'pyrevit': Obj(forms=Obj(TemplateListItem=Option)),
            'lowlife.equipment_tags': Obj(id_int=int, _safe_name=lambda obj: obj.name),
            'lowlife.select_list': Obj(SelectFromList=Obj(show=show)),
            'lowlife.settings_transfer': Obj(RELOAD='reload')}):
        saved_store = Obj(update=saved.update)
        scope.update(load=lambda: saved, STORE=saved_store,
                     symbols_on_view=lambda doc, view: [a, b],
                     settings_core=Obj(TextSettings=Editor,
                                       ChoiceField=config.settings_core.ChoiceField,
                                       TextField=config.settings_core.TextField))
        definitions('lib/lowlife/ar_task_annotations_settings.py', ['edit'], scope)
        scope['edit'](Obj(), Obj(Id=1))
    assert saved['selected_types'] == [config.type_key(b)]
    assert Editor.last.store is saved_store


def test_symbols_on_view_returns_unique_equipment_types(type_api):
    first = symbol(name='A', element_id=1)
    duplicate = symbol(name='A', element_id=2)
    second = symbol(name='B', element_id=3)
    instances = [Obj(Symbol=first), Obj(Symbol=duplicate), Obj(Symbol=second)]
    db = Obj(FamilyInstance='family',
             FilteredElementCollector=lambda doc, view_id: Obj(
                 OfClass=lambda cls: instances))
    from unittest.mock import patch
    with patch.dict(sys.modules, {
            'Autodesk': Obj(), 'Autodesk.Revit': Obj(), 'Autodesk.Revit.DB': db,
            'lowlife.equipment_tags': Obj(
                id_int=int, _safe_name=lambda obj: obj.name,
                is_equipment=lambda element: True)}):
        assert config.symbols_on_view(Obj(), Obj(Id=10)) == [first, second]


@pytest.mark.parametrize('text_mode,fail_stage', [(False, None), (True, None),
                                                  (True, 'create'), (True, 'prepare'),
                                                  (True, 'place')])
def test_shared_layout_supports_native_tags_and_text_notes(text_mode, fail_stage):
    element = Obj(Id=1, Category=Obj(Id=10), get_BoundingBox=lambda view: Obj(Min=(0, 0)))
    note = Obj(Id=100, TagHeadPosition=(0, 0), HasLeader=True,
               get_BoundingBox=lambda view: (-1, -.5, 1, .5))
    events = []
    frame = Obj(rect=lambda box: box, depth=lambda point: 0,
                uv=lambda point: point, xyz=lambda uv, depth: uv)
    adapter = Obj(create=lambda *args: note,
                  prepare=lambda note, el: events.append('prepare'),
                  head=lambda note: (0, 0),
                  place=lambda *args: events.append('place'))
    scope = dict(
        MM_TO_FT=1 / 304.8, ViewFrame=lambda view: frame, equipment_key=lambda el: el.Id,
        id_int=int, LinkedEquipment=type('Linked', (), {}), tag_layout=tag_layout,
        _other_equipment=lambda *args: [], probe_annotation_rects=lambda *args: {},
        symbol_info=lambda *args: ((-1, -1, 1, 1), True),
        _create_tag=lambda *args: note, upper_floor_only=lambda *args: False,
        _obstacle_rects=lambda *args: [], _tag_reference=lambda *args: None,
        _set_leader=lambda *args, **kwargs: events.append('leader'),
        tag_leader_follow=Obj(remember=lambda *args: events.append('follow')))
    definitions('lib/lowlife/equipment_tags.py', ['run'], scope)
    if fail_stage:
        def fail(*args):
            raise ValueError('native API failure')
        setattr(adapter, fail_stage, fail)
        with pytest.raises(ValueError, match='native API failure'):
            scope['run'](Obj(Application=Obj(VersionNumber='2023'), Regenerate=lambda: None),
                         Obj(Scale=100), [(element, None, None)],
                         dict(offset_mm=3, gap_mm=1, shelf_mm=3, cluster_mm=8), annotation=adapter)
        return
    stats = scope['run'](Obj(Application=Obj(VersionNumber='2023'), Regenerate=lambda: None),
                         Obj(Scale=100), [(element, None, None)],
                         dict(offset_mm=3, gap_mm=1, shelf_mm=3, cluster_mm=8),
                         annotation=adapter if text_mode else None)
    assert stats['created'] == stats['moved'] == 1
    assert stats['failed'] == 0
    assert events == (['prepare', 'place'] if text_mode else ['leader', 'follow'])


def test_rerun_updates_owned_notes_skips_pinned_and_ignores_blank_types():
    visible = [Obj(UniqueId=uid, Symbol=uid) for uid in ('old', 'new', 'pinned', 'blank')]
    old, pinned = Obj(Pinned=False), Obj(Pinned=True)
    entries_seen = []
    def layout(doc, view, entries, settings, annotation=None):
        entries_seen.extend(entries)
        return {'created': sum(note is None for _, note, _ in entries)}
    collector = lambda doc, *args: Obj(OfClass=lambda cls: [Obj(name='Text', Id=99)] if cls == 'type' else visible)
    scope = dict(FilteredElementCollector=collector, FamilyInstance='instance', TextNoteType='type',
                 equipment_tags=Obj(_safe_name=lambda obj: obj.name, is_equipment=lambda el: True, run=layout),
                 settings_module=Obj(text_for=lambda sym, settings: '' if sym == 'blank' else 'Task'),
                 owned_notes=lambda *args: {'old': [old], 'pinned': [pinned]},
                 TextAnnotation=lambda *args: object(), tr=lambda ru, en: en)
    definitions('lib/lowlife/ar_task_annotations.py', ['run'], scope)
    stats = scope['run'](Obj(), Obj(Id=1), {'text_type_name': 'Text'})
    assert entries_seen == [(visible[0], old, None), (visible[1], None, None)]
    assert stats == {'created': 1, 'pinned': 1}


def test_owned_notes_include_hidden_notes_but_exclude_other_views_and_user_text():
    definition = Obj(GetField=lambda name: name)
    notes = []
    for view_id, owned, uid in [(10, True, 'a'), (10, True, 'a'),
                                 (11, True, 'b'), (10, False, '')]:
        entity = Obj(IsValid=lambda owned=owned: owned,
                     Get={str: lambda field, uid=uid: uid})
        notes.append(Obj(OwnerViewId=view_id, GetEntity=lambda schema, entity=entity: entity))
    calls = []
    def collector(*args):
        calls.append(args)
        return Obj(OfClass=lambda cls: notes)
    scope = dict(Schema=Obj(Lookup=lambda guid: definition), SCHEMA_ID='schema',
                 String=str, TextNote='text', FilteredElementCollector=collector)
    definitions('lib/lowlife/ar_task_annotations.py', ['owned_notes'], scope)
    doc = Obj()
    assert scope['owned_notes'](doc, Obj(Id=10)) == {'a': notes[:2]}
    assert calls == [(doc,)]  # No visibility filter: hidden owned notes must be found.


@pytest.mark.parametrize('attach,left', [(0, True), (4, False)])
def test_text_adapter_updates_style_text_and_creates_one_leader(attach, left):
    calls = []
    leader = Obj()
    note = Obj(Coord=(0, 0), GetTypeId=lambda: 1,
               RemoveLeaders=lambda: calls.append('remove'),
               ChangeTypeId=lambda tid: calls.append(('type', tid)),
               AddLeader=lambda kind: calls.append(kind) or leader)
    scope = dict(settings_module=Obj(text_for=lambda sym, settings: 'New text'),
                 LeaderAtachement=Obj(MidPoint='mid'),
                 TextNoteLeaderTypes=Obj(TNLT_STRAIGHT_L='left', TNLT_STRAIGHT_R='right'))
    definitions('lib/lowlife/ar_task_annotations.py', ['TextAnnotation'], scope)
    adapter = scope['TextAnnotation']({}, 2)
    adapter.prepare(note, Obj(Symbol='type'))
    assert note.Text == 'New text'
    assert note.LeaderLeftAttachment == note.LeaderRightAttachment == 'mid'
    placement = Obj(tag_rect=(0, 0, 4, 2), attach=(attach, 1), end=(7, 1), elbow=(6, 1))
    adapter.place(note, Obj(xyz=lambda uv, depth: uv + (depth,)), (2, 1), 3, placement)
    assert note.Coord == (2, 1, 3)
    assert leader.End == (7, 1, 3) and leader.Elbow == (6, 1, 3)
    assert calls == ['remove', ('type', 2), 'left' if left else 'right']
