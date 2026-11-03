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
    doc = Obj(GetElement=lambda key: None)
    transactions = []

    class Transaction(object):
        def __init__(self, doc, name):
            self.status = None
            self.disposed = False
            transactions.append(self)

        def Start(self):
            self.before = copy.deepcopy(host.overrides)
            self.status = 'started'

        def Commit(self):
            self.status = 'committed'
            return self.status

        def GetStatus(self):
            return self.status

        def RollBack(self):
            host.overrides = self.before
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
               transactions=transactions, db=db)


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
