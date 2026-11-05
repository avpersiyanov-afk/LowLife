# -*- coding: utf-8 -*-
"""Exercise candidate scope without loading the Revit/WPF assemblies."""
import ast
from pathlib import Path
from types import SimpleNamespace as Item


def definitions(module, names, scope):
    path = Path(__file__).resolve().parents[1] / 'lib' / 'lowlife' / (module + '.py')
    tree = ast.parse(path.read_text(encoding='utf-8'))
    tree.body = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(tree, str(path), 'exec'), scope)
    return scope


def collector_scope():
    calls = []
    model = Item(CategoryType='model', Name='Equipment')
    elements = {
        1: Item(Category=model),
        2: Item(Category=model),
        3: Item(Category=Item(CategoryType='annotation', Name='Tags')),
        4: Item(Category=Item(CategoryType='model', Name='Mass')),
        5: Item(Category=None),
    }
    doc = Item(GetElement=elements.get)

    class Collector:
        def __init__(self, document, view_id=None):
            calls.append(view_id)
            self.items = [elements[2], elements[3], elements[4], elements[5]]

        def WhereElementIsNotElementType(self):
            return self

        def __iter__(self):
            return iter(self.items)

    scope = definitions('loi_fill', ['collect_candidates'], {
        'SELECTION_MODE_VIEW': 'view', 'SELECTION_MODE_ALL': 'all',
        'SELECTION_MODE_TYPES': 'types', 'CategoryType': Item(Model='model'),
        'FilteredElementCollector': Collector,
    })
    return scope['collect_candidates'], doc, elements, calls


def test_selected_objects_are_independent_of_active_view_and_exclude_non_targets():
    collect, doc, elements, calls = collector_scope()
    assert collect(doc, None, 'Mass', selected_ids=[1, 3, 4, 5, 99]) == [elements[1]]
    assert calls == []


def test_empty_selection_never_expands_to_whole_view_or_document():
    collect, doc, _, calls = collector_scope()
    assert collect(doc, None, 'Mass', mode='all', selected_ids=[]) == []
    assert calls == []


def test_view_scope_uses_chosen_view_instead_of_active_view():
    collect, doc, elements, calls = collector_scope()
    doc.ActiveView = Item(Id=10)
    assert collect(doc, Item(Id=20), 'Mass') == [elements[2]]
    assert calls == [20]


def test_saving_parameters_excludes_revit_objects_and_removes_legacy_scope():
    saved = {'selection_mode': 'all', 'selected_type_ids': [1], 'other': 'keep'}
    writes = []
    save = definitions('loi_settings', ['save_values'], {
        '_read_all': lambda: dict(saved), '_write_all': writes.append,
    })['save_values']
    save({'param_names_text': 'Parameter', '_view': object(), '_selected_ids': [object()]})
    assert writes == [{'other': 'keep', 'param_names_text': 'Parameter'}]
