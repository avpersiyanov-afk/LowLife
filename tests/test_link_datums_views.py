"""Visibility rules select linked names, never host/link numeric IDs."""
import sys
from types import SimpleNamespace as NS
from lowlife import link_datums_views as views


class GenericList:
    def __class_getitem__(cls, item):
        return list


def test_name_filter_hides_only_names_outside_selection(monkeypatch):
    class Factory:
        @staticmethod
        def CreateNotEqualsRule(param, name):
            return lambda element: element != name

    created = []

    def create(doc, name, categories, rule):
        created.append((categories, rule))
        return NS(Id=42)

    db = NS(ElementParameterFilter=lambda rule: rule, ElementId=lambda n: n,
            BuiltInParameter=NS(DATUM_TEXT=-1008000), ElementFilter=object,
            ParameterFilterRuleFactory=Factory,
            LogicalAndFilter=lambda rules: lambda e: all(rule(e) for rule in rules),
            ParameterFilterElement=NS(Create=create))
    monkeypatch.setitem(sys.modules, 'Autodesk', NS())
    monkeypatch.setitem(sys.modules, 'Autodesk.Revit', NS(DB=db))
    monkeypatch.setitem(sys.modules, 'System', NS())
    monkeypatch.setitem(sys.modules, 'System.Collections', NS())
    monkeypatch.setitem(sys.modules, 'System.Collections.Generic', NS(List=GenericList))
    calls = []
    view = NS(Name='Control', AddFilter=lambda i: calls.append(i),
              SetFilterVisibility=lambda i, visible: calls.append(visible))
    choices = [('grid', NS(link={'name': n}), None, None) for n in ['A', 'B', 'A']]
    views._name_filter(None, view, 'grids', choices)
    categories, hidden = created[0]
    assert categories == ['grids']
    assert not hidden('A')
    assert not hidden('B')
    assert hidden('C')
    assert calls == [42, False]
