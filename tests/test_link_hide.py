# -*- coding: utf-8 -*-
"""Regression tests for link scope, criteria and native command dispatch."""
import sys
import types

import pytest

from lowlife import link_hide, link_hide_core


def criterion(**overrides):
    result = dict(field="parameter", filter_param_name="User field", scope="instance_or_type",
                  operator="contains", value="test")
    result.update(overrides)
    return result


@pytest.mark.parametrize("actual,op,value,expected", [
    (u"  СТЕНА АР  ", "contains", u"стена", True),
    ("Test", "equals", "test", True),
    ("Test", "equals", "tes", False),
    ("Test", "starts_with", "tes", True),
    ("Test", "not_contains", "other", True),
    ("Test", "not_equals", "other", True),
    ("", "empty", "", True),
    ("   ", "not_empty", "", False),
    ("0", "not_empty", "", True),
    ("a.*b", "contains", ".*", True),
    ("ab", "contains", ".*", False),
])
def test_literal_text_criteria(actual, op, value, expected):
    assert link_hide_core.matches(actual, op, value) is expected


@pytest.mark.parametrize("op", link_hide_core.OPERATORS)
def test_missing_property_never_matches_even_negative_conditions(op):
    assert not link_hide_core.matches(None, op, "test")


def test_blank_value_cannot_hide_everything_accidentally():
    assert link_hide_core.validate(criterion(value="  ")) == "value"
    with pytest.raises(ValueError):
        link_hide_core.matches("any", "contains", "")
    assert link_hide_core.validate(criterion(operator="empty", value="")) is None
    assert link_hide_core.validate(criterion(filter_param_name="")) == "parameter"
    assert link_hide_core.validate(criterion(operator="unknown")) == "operator"


class Id(object):
    def __init__(self, value):
        self.Value = value


class Document(object):
    def __init__(self):
        self.types = {}

    def Equals(self, other):
        return self is other

    def GetElement(self, ident):
        return self.types.get(ident.Value)


class Element(object):
    def __init__(self, doc, ident, value="test"):
        self.Document = doc
        self.Id = Id(ident)
        self.Name = "Element"
        self.Category = types.SimpleNamespace(Id=Id(-2000011), Name="Walls", CategoryType="Model")
        self.params = {}
        self.value = value

    def GetTypeId(self):
        return Id(99)

    def GetParameters(self, name):
        return self.params.get(name, [])


class Link(Element):
    def __init__(self, host, ident, linked):
        Element.__init__(self, host, ident)
        self.linked = linked

    def GetLinkDocument(self):
        return self.linked


class TypedList(list):
    @classmethod
    def __class_getitem__(cls, item):
        return cls

    def Add(self, item):
        self.append(item)


@pytest.fixture
def api(monkeypatch):
    class Reference(object):
        def __init__(self, element):
            self.element = element

        def CreateLinkReference(self, link):
            return (link.Id.Value, self.element.Id.Value)

    db = types.SimpleNamespace(
        Reference=Reference,
        Element=types.SimpleNamespace(Name=types.SimpleNamespace(GetValue=lambda el: el.Name)),
        StorageType=types.SimpleNamespace(String="string", Integer="int", Double="double", ElementId="id"),
        CategoryType=types.SimpleNamespace(Model="Model"), RevitLinkInstance=Link)
    ui = types.SimpleNamespace(
        RevitCommandId=types.SimpleNamespace(LookupPostableCommandId=lambda cmd: cmd),
        PostableCommand=types.SimpleNamespace(HideElements="hide"))
    monkeypatch.setitem(sys.modules, "pyrevit", types.SimpleNamespace(DB=db, UI=ui))
    monkeypatch.setitem(sys.modules, "System.Collections.Generic", types.SimpleNamespace(List=TypedList))
    return db


def test_instance_blank_is_not_replaced_by_type_value(api):
    doc = Document()
    el = Element(doc, 1)
    typ = Element(doc, 99)
    doc.types[99] = typ
    empty = types.SimpleNamespace(HasValue=False)
    filled = types.SimpleNamespace(HasValue=True, StorageType="string", AsString=lambda: "type value")
    typ.params["User field"] = [filled]
    el.params["User field"] = [empty]
    assert link_hide.read_value(el, criterion()) == ""
    el.params.clear()
    assert link_hide.read_value(el, criterion()) == "type value"
    assert link_hide.read_value(el, criterion(scope="instance")) is None
    el.params["User field"] = [empty, filled]
    with pytest.raises(ValueError):
        link_hide.read_value(el, criterion())


def test_matches_keep_instance_identity_when_links_share_element_ids(api, monkeypatch):
    host, linked = Document(), Document()
    a, b = Link(host, 1, linked), Link(host, 2, linked)
    el = Element(linked, 10)
    other_category = Element(linked, 11)
    other_category.Category.Id = Id(-999)
    monkeypatch.setattr(link_hide, "read_value", lambda el, settings: el.value)
    rows = link_hide.find_matches([(a, el), (a, el), (b, el), (a, other_category)],
                                  [(-2000011, "Walls")], criterion())
    assert [(r.link.Id.Value, r.element.Id.Value) for r in rows] == [(1, 10), (2, 10)]


def test_collector_uses_host_view_and_specific_link_instance(api):
    calls = []
    host, linked = Document(), Document()
    link = Link(host, 5, linked)
    el = Element(linked, 10)

    class Collector(list):
        def __init__(self, doc, view_id, link_id):
            calls.append((doc, view_id.Value, link_id.Value))
            list.__init__(self, [el])

        def WhereElementIsNotElementType(self):
            return self

        def Dispose(self):
            pass

    api.FilteredElementCollector = Collector
    result = link_hide.collect_candidates(host, types.SimpleNamespace(Id=Id(22)), [types.SimpleNamespace(link=link)])
    assert calls == [(host, 22, 5)]
    assert result == [(link, el)]


def application(host, allowed=True, fail=False):
    class Selection(object):
        refs = ["original"]

        def GetReferences(self):
            return self.refs

        def SetReferences(self, refs):
            self.refs = list(refs)

    class App(object):
        ActiveUIDocument = types.SimpleNamespace(Document=host, Selection=Selection())
        posted = []

        def CanPostCommand(self, command):
            assert self.ActiveUIDocument.Selection.refs != ["original"]
            return allowed

        def PostCommand(self, command):
            if fail:
                raise RuntimeError("queue busy")
            self.posted.append(command)

    return App()


@pytest.mark.parametrize("allowed,fail", [(False, False), (True, True)])
def test_selection_restored_when_native_command_cannot_be_queued(api, allowed, fail):
    host, linked = Document(), Document()
    row = link_hide.MatchRow(Link(host, 1, linked), Element(linked, 10), "test")
    app = application(host, allowed, fail)
    with pytest.raises((ValueError, RuntimeError)):
        link_hide.post_hide(app, [row])
    assert app.ActiveUIDocument.Selection.refs == ["original"]
    assert app.posted == []


def test_native_hide_receives_link_references_not_host_element_ids(api):
    host, linked = Document(), Document()
    el = Element(linked, 10)
    a = link_hide.MatchRow(Link(host, 1, linked), el, "test")
    b = link_hide.MatchRow(Link(host, 2, linked), el, "test")
    app = application(host)
    assert not link_hide.post_hide(app, [])
    assert link_hide.post_hide(app, [a, a, b])
    assert app.ActiveUIDocument.Selection.refs == [(1, 10), (2, 10)]
    assert app.posted == ["hide"]
    wrong_app = application(Document())
    with pytest.raises(ValueError):
        link_hide.post_hide(wrong_app, [a])
    assert wrong_app.ActiveUIDocument.Selection.refs == ["original"]
