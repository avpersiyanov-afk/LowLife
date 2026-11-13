# -*- coding: utf-8 -*-
"""Independent sections, inherited visibility and current-state writes."""
import sys
import types
import pytest
from lowlife import model_filter_revit as api
from lowlife import datum_filter_presets as presets


@pytest.fixture
def model(monkeypatch):
    import lowlife
    from lowlife import link_views
    worksets = [types.SimpleNamespace(Id=1, Name='B1_A', Kind='user', IsOpen=True),
                types.SimpleNamespace(Id=2, Name='B1_B', Kind='user', IsOpen=True),
                types.SimpleNamespace(Id=3, Name='B2_A', Kind='user', IsOpen=False)]

    class Link:
        def __init__(self, number, name, hidden=False, loaded=True):
            self.Id, self.Name, self.hidden, self.loaded = number, name, hidden, loaded

        def GetLinkDocument(self):
            return object() if self.loaded else None

        def IsHidden(self, view):
            return self.hidden

        def CanBeHidden(self, view):
            return True

    links = [Link(10, 'B1_A'), Link(11, 'B1_B', hidden=True), Link(12, 'B2_Link', loaded=False)]
    view = types.SimpleNamespace(ViewTemplateId=0, GetWorksetVisibility=lambda number: 'global')
    doc = types.SimpleNamespace(IsFamilyDocument=False, IsWorkshared=True, controlled=False)
    doc.GetElement = lambda number: next((link for link in links if link.Id == number), None)
    doc.GetWorksetTable = lambda: types.SimpleNamespace(GetWorkset=lambda number:
        next((workset for workset in worksets if workset.Id == number), None))

    class Collector:
        def __init__(self, doc):
            pass

        def OfClass(self, cls):
            return links

    db = types.ModuleType('Autodesk.Revit.DB')
    db.FilteredElementCollector, db.RevitLinkInstance = Collector, Link
    db.WorksetVisibility = types.SimpleNamespace(Visible='visible', Hidden='hidden', UseGlobalSetting='global')
    db.WorksetDefaultVisibilitySettings = types.SimpleNamespace(
        GetWorksetDefaultVisibilitySettings=lambda source: types.SimpleNamespace(IsWorksetVisible=lambda number: number != 2))
    db.BuiltInParameter = types.SimpleNamespace(VIS_GRAPHICS_WORKSETS=1)
    db.WorksetKind = types.SimpleNamespace(UserWorkset='user')
    monkeypatch.setitem(sys.modules, 'Autodesk.Revit.DB', db)
    monkeypatch.setattr(lowlife, 'cable_tray', types.SimpleNamespace(find_worksets=lambda source, mask: worksets), raising=False)
    monkeypatch.setitem(sys.modules, 'lowlife.cable_tray', lowlife.cable_tray)
    monkeypatch.setattr(link_views, 'safe_name', lambda link: link.Name)
    monkeypatch.setattr(link_views, 'template_controls', lambda source, view, parameter: doc.controlled)
    monkeypatch.setattr(api, 'supported', lambda view: True)
    writes = []
    monkeypatch.setattr(api.datums, 'set_visibility', lambda *args: writes.append(args))
    return doc, view, worksets, links, writes


def test_snapshot_has_two_sections_global_defaults_mixed_and_disabled_rows(model):
    doc, view, worksets, links, writes = model
    groups, unmatched, caption, _ = api.snapshot(doc, view, {'workset_mask': '{b}_*', 'link_mask': '{b}_*'})
    assert [group['checked'] for group in groups] == [None, False, None, False]
    assert groups[1]['items'][0]['hideable'] is False
    assert groups[3]['items'][0]['hideable'] is False
    assert groups[1]['items'][0]['reason']
    assert groups[3]['items'][0]['reason']
    assert len(set(group['visibility_key'] for group in groups)) == 4
    assert unmatched == 0
    assert not writes


def test_identical_group_names_do_not_share_presets_and_masks_round_trip(model):
    doc, view, _, _, _ = model
    groups, _, _, _ = api.snapshot(doc, view, {'workset_mask': '{b}_*', 'link_mask': '{b}_*'})
    saved = {groups[0]['visibility_key']: False, groups[2]['visibility_key']: True}
    raw = presets.save_preset({}, 'Model', 'Preset', '{b}_*', '*', saved, ('workset_mask', 'link_mask'))
    preset = presets.list_presets(raw, 'Model', ('workset_mask', 'link_mask'))[0]
    assert preset['workset_mask'] == '{b}_*'
    assert 'grid_mask' not in preset
    changes = presets.plan_changes(groups, preset['visibility'])
    assert [items[0]['kind'] for items, show in changes] == ['workset', 'link']
    assert [show for items, show in changes] == [False, True]


def test_unshared_model_still_lists_links(model):
    doc, view, _, _, _ = model
    doc.IsWorkshared = False
    groups, _, _, _ = api.snapshot(doc, view, {'workset_mask': '*', 'link_mask': '*'})
    assert all(item['kind'] == 'link' for group in groups for item in group['items'])


def test_writes_read_live_state_and_use_one_combined_transaction(model):
    doc, view, _, links, writes = model
    groups, _, _, _ = api.snapshot(doc, view, {'workset_mask': '*', 'link_mask': '*'})
    links[0].hidden = True  # manual change after snapshot
    links.pop(1)           # deletion after snapshot
    changed, skipped = api.apply_visibility_map(doc, view, [(group['items'], True) for group in groups])
    assert changed == 2   # globally hidden workset 2 and now-hidden link 10
    assert skipped == 3   # closed workset, deleted link, unloaded link
    assert len(writes) == 1
    args = writes[0]
    assert args[2] == []
    assert args[3] == [10]
    assert args[4] == [(2, True)]


def test_template_control_added_after_snapshot_blocks_worksets_only(model):
    doc, view, _, _, writes = model
    groups, _, _, _ = api.snapshot(doc, view, {'workset_mask': '*', 'link_mask': '*'})
    doc.controlled = True
    template = types.SimpleNamespace(GetWorksetVisibility=lambda number: 'visible')
    get_element = doc.GetElement
    doc.GetElement = lambda number: template if number == 0 else get_element(number)
    changed, skipped = api.apply_visibility_map(doc, view, [(group['items'], False) for group in groups])
    assert changed == 1
    assert skipped == 4
    assert writes[0][4] == []
    assert writes[0][2] == [10]
