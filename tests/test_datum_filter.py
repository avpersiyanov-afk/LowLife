# -*- coding: utf-8 -*-
"""Mask boundaries, mixed visibility and safe restoration without Revit."""
import pytest
import ast
import sys
import types
from pathlib import Path
from lowlife import datum_filter_core as core
from lowlife import datum_filter_presets as presets
from lowlife import datum_filter_settings as cfg


def item(name, number=1, hidden=False, hideable=True):
    return dict(name=name, id=number, hidden=hidden, hideable=hideable)


def test_groups_by_building_and_section_and_preserves_unmatched():
    rows, unmatched = core.group_datums([
        item(u'B2_S1_01'), item(u'B2_S1_02', 2, True),
        item(u'B10_S1_01', 3, True), item(u'Other', 4)], u'{building}_{section}_*')
    assert [row['name'] for row in rows] == [u'B2 / S1', u'B10 / S1']
    assert [row['checked'] for row in rows] == [None, False]
    assert unmatched == 1
    assert core.visibility_changes(rows[0]['items'], False) == [1]
    assert core.visibility_changes(rows[0]['items'], True) == [2]


def test_mask_literals_whole_name_unicode_and_case():
    pattern, labels = core.compile_mask(u'*_{секция}_[?].*')
    assert labels == [u'секция']
    assert pattern.match(u'АР_2_[А].+3,100').groups() == (u'2',)
    assert pattern.match(u'АР_2_А.+3,100') is None
    pattern, _ = core.compile_mask(u'К{корпус}_*')
    assert pattern.match(u'к12_ось').groups() == (u'12',)
    assert pattern.match(u'Xк12_ось') is None


@pytest.mark.parametrize('mask', [u'{', u'}', u'{}', u'{x}_{x}', u'{{x}}'])
def test_invalid_mask_rejected_before_saving(mask):
    with pytest.raises(ValueError):
        core.compile_mask(mask)
    values, errors = cfg.SETTINGS.parse_form({'grid_mask': mask, 'level_mask': '*'})
    assert errors


def test_no_captures_means_individual_names_with_natural_sort():
    rows, unmatched = core.group_datums([
        item('10'), item('2', 2), item('1', 3)], '*')
    assert [row['name'] for row in rows] == ['1', '2', '10']
    assert all(row['checked'] is True for row in rows)
    assert unmatched == 0


def test_restore_does_not_unhide_unrelated_or_unhideable_items():
    items = [item('A', 1, True), item('A', 2), item('A', 3, True, False)]
    assert core.visibility_changes(items, True) == [1]
    assert core.visibility_changes(items, False) == [2]


def test_empty_mask_defaults_to_all_and_captures_do_not_merge_on_slashes():
    assert len(core.group_datums([item('A'), item('B', 2)], '')[0]) == 2
    rows, _ = core.group_datums([item('A / B_C'), item('A_B / C', 2)], '{a}_{b}')
    assert len(rows) == 2


@pytest.mark.parametrize('is_3d', [False, True])
def test_snapshot_reuses_existing_datum_collectors(monkeypatch, is_3d):
    import lowlife
    from lowlife import datum_filter_revit as adapter

    class View3D:
        pass

    class Element:
        def IsHidden(self, view):
            return True

        def CanBeHidden(self, view):
            return True

    class Document:
        def GetElement(self, element_id):
            assert element_id == 17
            return Element()

    doc = Document()
    view = View3D() if is_3d else object()
    calls = []

    def levels(source_doc, transform, base_z):
        calls.append(('levels', source_doc, transform, base_z))
        return [dict(id=17, name='B2_L1', elevation=123)]

    def grids(source_doc, transform):
        calls.append(('grids', source_doc, transform))
        return [dict(id=17, name='B1_G1', line=((0, 0), (1, 1)))]

    db = types.ModuleType('Autodesk.Revit.DB')
    db.View3D = View3D
    monkeypatch.setitem(sys.modules, 'Autodesk.Revit.DB', db)
    monkeypatch.setattr(lowlife, 'link_datums', types.SimpleNamespace(
        collect_levels=levels, collect_grids=grids), raising=False)
    groups, unmatched, mask, actual_3d = adapter.snapshot(
        doc, view, {'grid_mask': '{building}_G*', 'level_mask': '{building}_L*'})
    assert calls == ([('levels', doc, None, 0.0)] if is_3d else [('grids', doc, None)])
    assert groups[0]['name'] == ('B2' if is_3d else 'B1')
    assert groups[0]['checked'] is False
    assert groups[0]['items'][0]['id'] == 17
    assert groups[0]['items'][0]['hideable'] is True
    assert actual_3d == is_3d
    assert unmatched == 0


@pytest.mark.parametrize('changed_document', [False, True])
def test_queued_click_cannot_edit_another_view_or_document(changed_document):
    # Exercise the actual event handler without loading WPF/Revit assemblies.
    source = Path(__file__).resolve().parents[1] / 'lib/lowlife/datum_filter_panel.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Handler')
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'Execute')
    module = ast.Module(body=[method], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {'tr': lambda text: text}
    exec(compile(module, str(source), 'exec'), namespace)

    class Object:
        pass

    panel = Object()
    panel.pending = ('visibility', 'original-document', 1, [], False)
    panel.status_label = Object()
    panel.status_label.Text = ''
    refreshed = []
    busy = []
    panel.refresh = lambda uiapp: refreshed.append(uiapp)
    panel.set_busy = busy.append
    handler = Object()
    handler.panel = panel
    uiapp = Object()
    uiapp.ActiveUIDocument = Object()
    uiapp.ActiveUIDocument.Document = 'other-document' if changed_document else 'original-document'
    uiapp.ActiveUIDocument.ActiveView = Object()
    uiapp.ActiveUIDocument.ActiveView.Id = 1 if changed_document else 2
    namespace['Execute'](handler, uiapp)
    assert panel.pending is None
    assert refreshed == [uiapp]
    assert busy == [False]
    assert panel.status_label.Text


# --- пользовательские группы настроек (пресеты) ----------------------------

def test_document_key_prefers_path_and_falls_back_to_title():
    assert presets.document_key(u'Проект', u'C:\\a.rvt') == u'C:\\a.rvt'
    assert presets.document_key(u'Проект', u'') == u'Проект'
    assert presets.document_key(None, None) == u''


def test_list_presets_normalizes_sorts_and_skips_garbage():
    raw = {
        u'C:\\a.rvt': {
            u'Группа 10': {u'grid_mask': u'*', u'level_mask': None,
                           u'visibility': {u'A': True, u'B': None, u'C': u'yes'}},
            u'Группа 2': u'битое',
            u'': {u'grid_mask': u'*'},
        },
        u'битый ключ': u'не словарь',
    }
    result = presets.list_presets(raw, u'C:\\a.rvt')
    assert [preset['name'] for preset in result] == [u'Группа 2', u'Группа 10']
    assert result[1]['grid_mask'] == u'*'
    assert result[1]['level_mask'] == u'*'  # None -> умолчание
    assert result[1]['visibility'] == {u'A': True, u'C': True}  # None выброшено
    assert presets.list_presets(u'не словарь', u'C:\\a.rvt') == []
    assert presets.list_presets({}, u'нет такой модели') == []


def test_save_preset_updates_named_group_and_validates_masks():
    raw = presets.save_preset({}, u'C:\\a.rvt', u'А', u'{к}_{с}_*', u'*',
                              {u'B2 / S1': False})
    again = presets.save_preset(raw, u'C:\\a.rvt', u'А', u'*', u'{к}_*', {})
    assert again[u'C:\\a.rvt'][u'А'][u'grid_mask'] == u'*'
    assert list(again.keys()) == [u'C:\\a.rvt']  # та же группа, не дубль
    assert raw[u'C:\\a.rvt'][u'А'][u'visibility'] == {u'B2 / S1': False}

    import pytest
    with pytest.raises(ValueError):
        presets.save_preset({}, u'C:\\a.rvt', u'Б', u'{', u'*', {})


def test_save_preset_keeps_other_models_and_empty_masks_default():
    raw = presets.save_preset({}, u'C:\\a.rvt', u'А', u'*', u'*', {})
    raw = presets.save_preset(raw, u'C:\\b.rvt', u'Б', u'', u'  ', {})
    assert set(raw.keys()) == {u'C:\\a.rvt', u'C:\\b.rvt'}
    assert raw[u'C:\\b.rvt'][u'Б'] == {
        u'grid_mask': u'*', u'level_mask': u'*', u'visibility': {}}


def test_delete_preset_removes_group_and_empty_model():
    raw = presets.save_preset({}, u'C:\\a.rvt', u'А', u'*', u'*', {})
    raw = presets.delete_preset(raw, u'C:\\a.rvt', u'А')
    assert raw == {}
    # Другие модели и чужие группы не трогаются.
    raw = presets.save_preset(raw, u'C:\\a.rvt', u'А', u'*', u'*', {})
    raw = presets.save_preset(raw, u'C:\\b.rvt', u'Б', u'*', u'*', {})
    raw = presets.delete_preset(raw, u'C:\\a.rvt', u'нет такой')
    assert set(raw.keys()) == {u'C:\\a.rvt', u'C:\\b.rvt'}
    raw = presets.delete_preset(raw, u'C:\\b.rvt', u'Б')
    assert list(raw.keys()) == [u'C:\\a.rvt']


def test_visibility_map_captures_tri_state():
    rows, _ = core.group_datums(
        [item(u'A_1'), item(u'A_2', 2, True), item(u'B_1', 3)], u'{g}_*')
    assert presets.visibility_map(rows) == {u'A': None, u'B': True}


def test_plan_changes_applies_only_named_targets_that_differ():
    rows, _ = core.group_datums(
        [item(u'A_1', hidden=True), item(u'A_2', 2, hidden=True),
         item(u'B_1', 3), item(u'C_1', 4, hideable=False)], u'{g}_*')
    saved = {u'A': True, u'B': False, u'C': True, u'Нет такой группы': False}
    changes = presets.plan_changes(rows, saved)
    # A скрыта целиком -> показать; B видна -> скрыть; C уже видна,
    # единственный элемент не hideable -> без изменений.
    assert [(sorted(item[u'id'] for item in items), show) for items, show in changes] == [
        ([1, 2], True), ([3], False)]
    assert presets.plan_changes(rows, {}) == []
    assert presets.plan_changes(rows, {u'A': None}) == []


# --- мультивыбор групп (Shift/Ctrl) ----------------------------------------

def test_selection_targets_plain_click_selects_only_clicked():
    visible = [0, 1, 2, 3]
    assert core.selection_targets(visible, 0, 2, False) == set([2])
    assert core.selection_targets(visible, None, 2, True) == set([2])


def test_selection_targets_shift_selects_range_from_anchor():
    visible = [0, 1, 2, 3, 4]
    assert core.selection_targets(visible, 1, 3, True) == set([1, 2, 3])
    assert core.selection_targets(visible, 3, 1, True) == set([1, 2, 3])
    # Якорь вне отображаемых строк — только нажатая.
    assert core.selection_targets(visible, 9, 2, True) == set([2])
    assert core.selection_targets(visible, 2, 9, True) == set([9])


def test_selection_targets_respects_search_filtering():
    # Поиск отсек строки 1 и 2: диапазон идёт только по видимым.
    visible = [0, 3, 4]
    assert core.selection_targets(visible, 0, 4, True) == set([0, 3, 4])
