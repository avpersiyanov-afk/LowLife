# -*- coding: utf-8 -*-
"""Batch linked-view settings: compatibility, inheritance and atomic rollback."""
import copy
from types import SimpleNamespace as Obj

import pytest

from lowlife import link_views as lv


class Settings(object):
    def __init__(self):
        self.LinkVisibilityType = 'host'
        self.LinkedViewId = -1
        self.other_graphics = 'keep'


class Host(object):
    IsTemplate = False
    ViewType = 'plan'
    ViewTemplateId = -1

    def __init__(self):
        self.overrides = {100: Settings(), 999: Settings()}
        self.fail_on = None

    def AreGraphicsOverridesAllowed(self):
        return True

    def GetLinkOverrides(self, key):
        return copy.deepcopy(self.overrides.get(key))

    def SetLinkOverrides(self, key, settings):
        if key == self.fail_on:
            raise ValueError('API rejected linked view')
        self.overrides[key] = copy.deepcopy(settings)


@pytest.fixture
def model(monkeypatch):
    host = Host()
    linked_doc = Obj()
    doc = Obj(GetElement=lambda key: None, Application=Obj(VersionNumber='2025'))
    transactions = []
    hosts = [host]

    class Transaction(object):
        def __init__(self, doc, name):
            self.status = None
            self.disposed = False
            transactions.append(self)

        def Start(self):
            self.before = [copy.deepcopy(v.overrides) for v in hosts]
            self.status = 'started'

        def Commit(self):
            self.status = 'committed'
            return self.status

        def GetStatus(self):
            return self.status

        def RollBack(self):
            for view, before in zip(hosts, self.before):
                view.overrides = before
            self.status = 'rolledback'

        def Dispose(self):
            self.disposed = True

    db = Obj(RevitLinkGraphicsSettings=Settings, Transaction=Transaction,
             TransactionStatus=Obj(Started='started', Committed='committed'),
             LinkVisibility=Obj(ByLinkView='linked', Custom='custom'),
             ElementId=lambda key: key,
             BuiltInParameter=Obj(VIS_GRAPHICS_RVT_LINKS=42))
    monkeypatch.setattr(lv, '_db', lambda: db)

    def pair(key, view_id=200):
        link = Obj(Id=key, GetTypeId=lambda: 100, GetLinkDocument=lambda: linked_doc)
        view = Obj(Id=view_id, Document=linked_doc, IsTemplate=False, ViewType='plan')
        return link, view

    return Obj(host=host, doc=doc, linked_doc=linked_doc, pair=pair,
               transactions=transactions, db=db, hosts=hosts)


def test_batch_changes_instances_preserving_type_and_unselected_links(model):
    original_type = copy.deepcopy(vars(model.host.overrides[100]))
    assert lv.apply(model.doc, model.host, [model.pair(1), model.pair(2, 201)]) == 2
    assert model.host.overrides[1].LinkedViewId == 200
    assert model.host.overrides[2].LinkedViewId == 201
    assert model.host.overrides[1].LinkVisibilityType == 'linked'
    assert model.host.overrides[1].other_graphics == 'keep'
    assert vars(model.host.overrides[100]) == original_type
    assert model.host.overrides[999].LinkVisibilityType == 'host'
    assert len(model.transactions) == 1
    assert model.transactions[0].disposed


def test_existing_instance_settings_take_priority_over_type(model):
    model.host.overrides[1] = Settings()
    model.host.overrides[1].other_graphics = 'instance'
    lv.apply(model.doc, model.host, [model.pair(1)])
    assert model.host.overrides[1].other_graphics == 'instance'


def test_multiple_hosts_keep_their_own_graphics_in_one_transaction(model):
    second = Host()
    second.overrides[100].other_graphics = 'second host'
    model.hosts.append(second)
    assert lv.apply_many(model.doc, model.hosts, [model.pair(1)]) == 2
    assert model.host.overrides[1].LinkedViewId == 200
    assert second.overrides[1].LinkedViewId == 200
    assert second.overrides[1].other_graphics == 'second host'
    assert model.host.overrides[1].other_graphics == 'keep'
    assert len(model.transactions) == 1


def test_independent_assignments_and_untouched_hosts(model):
    second, untouched = Host(), Host()
    model.hosts.extend([second, untouched])
    assert lv.apply_assignments(model.doc, [
        (model.host, [model.pair(1, 200)]),
        (second, [model.pair(1, 201), model.pair(2, 202)])]) == 3
    assert model.host.overrides[1].LinkedViewId == 200
    assert second.overrides[1].LinkedViewId == 201
    assert second.overrides[2].LinkedViewId == 202
    assert 2 not in model.host.overrides
    assert 1 not in untouched.overrides
    assert len(model.transactions) == 1


def test_independent_assignments_roll_back_together(model):
    second = Host()
    second.fail_on = 2
    model.hosts.append(second)
    with pytest.raises(ValueError):
        lv.apply_assignments(model.doc, [
            (model.host, [model.pair(1, 200)]),
            (second, [model.pair(2, 201)])])
    assert 1 not in model.host.overrides
    assert 2 not in second.overrides
    assert model.transactions[0].status == 'rolledback'


def test_duplicate_host_link_pair_is_rejected(model):
    with pytest.raises(ValueError):
        lv.apply_assignments(model.doc, [
            (model.host, [model.pair(1, 200)]),
            (model.host, [model.pair(1, 201)])])
    assert model.transactions == []


def test_failure_on_later_host_rolls_back_earlier_host(model):
    second = Host()
    second.fail_on = 1
    model.hosts.append(second)
    with pytest.raises(ValueError, match='API rejected'):
        lv.apply_many(model.doc, model.hosts, [model.pair(1)])
    assert 1 not in model.host.overrides
    assert 1 not in second.overrides
    assert model.transactions[0].status == 'rolledback'


def test_incompatible_later_host_is_rejected_before_transaction(model):
    second = Host()
    second.ViewType = 'section'
    with pytest.raises(ValueError):
        lv.apply_many(model.doc, [model.host, second], [model.pair(1)])
    assert model.transactions == []


def test_mixed_current_values_are_labelled(model, monkeypatch):
    second = Host()
    link, _ = model.pair(1)
    monkeypatch.setattr(lv, 'collect_rows', lambda doc, view: [
        dict(link=link, current='first' if view is model.host else 'second')])
    rows = lv.collect_many_rows(model.doc, [model.host, second])
    assert rows[0]['current'] == lv.tr(u'Разные значения', u'Mixed values')


def test_api_rejection_rolls_back_the_whole_batch(model):
    model.host.fail_on = 2
    with pytest.raises(ValueError, match='API rejected'):
        lv.apply(model.doc, model.host, [model.pair(1), model.pair(2)])
    assert set(model.host.overrides) == {100, 999}
    assert model.transactions[0].status == 'rolledback'
    assert model.transactions[0].disposed


@pytest.mark.parametrize('invalid', ['unloaded', 'template', 'type', 'document', 'duplicate'])
def test_invalid_batch_is_rejected_before_opening_transaction(model, invalid):
    link, view = model.pair(1)
    choices = [(link, view)]
    if invalid == 'unloaded':
        link.GetLinkDocument = lambda: None
    elif invalid == 'template':
        view.IsTemplate = True
    elif invalid == 'type':
        view.ViewType = 'section'
    elif invalid == 'document':
        view.Document = Obj(other_document=True)
    else:
        choices.append(model.pair(1))
    with pytest.raises(ValueError):
        lv.apply(model.doc, model.host, choices)
    assert model.transactions == []


def test_template_control_is_blocked_unless_link_parameter_is_free(model):
    free = []
    template = Obj(Id=20, GetTemplateParameterIds=lambda: [42],
                   GetNonControlledTemplateParameterIds=lambda: free)
    model.doc.GetElement = lambda key: template
    assert lv.availability(model.doc, model.host)
    free.append(42)
    assert lv.availability(model.doc, model.host) is None


def test_empty_batch_does_not_start_transaction(model):
    assert lv.apply(model.doc, model.host, []) == 0
    assert model.transactions == []


def test_commit_rollback_is_not_reported_as_success(model):
    base = model.db.Transaction

    class RejectedTransaction(base):
        def Commit(self):
            self.RollBack()
            return self.status

    model.db.Transaction = RejectedTransaction
    with pytest.raises(RuntimeError):
        lv.apply(model.doc, model.host, [model.pair(1)])
    assert 1 not in model.host.overrides
    assert model.transactions[0].disposed


def test_new_settings_are_created_when_no_instance_or_type_override_exists(model):
    model.host.overrides = {}
    lv.apply(model.doc, model.host, [model.pair(1)])
    assert model.host.overrides[1].LinkedViewId == 200


def test_candidates_exclude_templates_and_different_view_types(model, monkeypatch):
    candidates = [Obj(Id=1, IsTemplate=False, ViewType='plan'),
                  Obj(Id=2, IsTemplate=True, ViewType='plan'),
                  Obj(Id=3, IsTemplate=False, ViewType='section')]
    model.db.View = object
    model.db.FilteredElementCollector = lambda doc: Obj(OfClass=lambda cls: candidates)
    monkeypatch.setattr(lv, 'safe_name', lambda view: str(view.Id))
    assert lv.compatible_views(model.linked_doc, model.host) == [candidates[0]]


def test_graphics_unavailable_and_old_api_are_explained(model):
    model.host.AreGraphicsOverridesAllowed = lambda: False
    assert lv.availability(model.doc, model.host)
    del model.db.RevitLinkGraphicsSettings
    assert lv.availability(model.doc, model.host)


def test_custom_preserves_existing_graphics_and_linked_view(model):
    settings = model.host.overrides[100]
    settings.LinkVisibilityType = 'linked'
    settings.LinkedViewId = 200
    settings.other_graphics = 'custom graphics'
    link, _ = model.pair(1)
    assert lv.apply(model.doc, model.host, [(link, lv.CUSTOM_VIEW)]) == 1
    assert model.host.overrides[1].LinkVisibilityType == 'custom'
    assert model.host.overrides[1].LinkedViewId == 200
    assert model.host.overrides[1].other_graphics == 'custom graphics'
    assert model.host.overrides[100].LinkVisibilityType == 'linked'


def test_custom_without_existing_override_does_not_require_linked_view(model):
    model.host.overrides = {}
    link, _ = model.pair(1)
    lv.apply(model.doc, model.host, [(link, lv.CUSTOM_VIEW)])
    assert model.host.overrides[1].LinkVisibilityType == 'custom'
    assert model.host.overrides[1].LinkedViewId == -1


def test_custom_with_selected_view_keeps_mode_view_and_existing_graphics(model):
    link, view = model.pair(1, 222)
    model.host.overrides[100].other_graphics = 'preserved'
    lv.apply(model.doc, model.host, [(link, lv.CustomView(view))])
    settings = model.host.overrides[1]
    assert settings.LinkVisibilityType == 'custom'
    assert settings.LinkedViewId == 222
    assert settings.other_graphics == 'preserved'
    # Switching back to By linked view still uses the explicitly selected view.
    lv.apply(model.doc, model.host, [(link, view)])
    assert model.host.overrides[1].LinkVisibilityType == 'linked'
    assert model.host.overrides[1].LinkedViewId == 222


@pytest.mark.parametrize('invalid', ['type', 'template', 'document', 'old_api'])
def test_custom_with_view_is_validated_before_transaction(model, invalid):
    link, view = model.pair(1)
    if invalid == 'type':
        view.ViewType = 'section'
    elif invalid == 'template':
        view.IsTemplate = True
    elif invalid == 'document':
        view.Document = Obj(other=True)
    else:
        model.doc.Application.VersionNumber = '2024'
    with pytest.raises(ValueError):
        lv.apply(model.doc, model.host, [(link, lv.CustomView(view))])
    assert model.transactions == []


def test_custom_without_selected_view_keeps_current_linked_view(model):
    model.host.overrides[100].LinkedViewId = 333
    link, _ = model.pair(1)
    lv.apply(model.doc, model.host, [(link, lv.CustomView())])
    assert model.host.overrides[1].LinkVisibilityType == 'custom'
    assert model.host.overrides[1].LinkedViewId == 333


@pytest.mark.parametrize('invalid', ['old_api', 'unloaded'])
def test_custom_rejected_before_transaction_when_unavailable(model, invalid):
    link, _ = model.pair(1)
    if invalid == 'old_api':
        model.doc.Application.VersionNumber = '2024'
    else:
        link.GetLinkDocument = lambda: None
    with pytest.raises(ValueError):
        lv.apply(model.doc, model.host, [(link, lv.CUSTOM_VIEW)])
    assert model.transactions == []


def test_custom_and_linked_assignments_roll_back_together(model):
    link, _ = model.pair(1)
    model.host.fail_on = 2
    with pytest.raises(ValueError):
        lv.apply(model.doc, model.host, [(link, lv.CUSTOM_VIEW), model.pair(2)])
    assert 1 not in model.host.overrides
    assert model.transactions[0].status == 'rolledback'


@pytest.mark.parametrize('version, available', [('2024', False), ('2025', True), ('2026', True)])
def test_custom_available_even_without_compatible_views(model, monkeypatch, version, available):
    model.doc.Application.VersionNumber = version
    link, _ = model.pair(1)
    model.db.RevitLinkInstance = object
    model.db.FilteredElementCollector = lambda doc: Obj(OfClass=lambda cls: [link])
    monkeypatch.setattr(lv, 'compatible_views', lambda doc, view: [])
    row = lv.collect_rows(model.doc, model.host)[0]
    assert row['custom_available'] is available
    assert (row['reason'] is None) is available

