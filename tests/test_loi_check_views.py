# -*- coding: utf-8 -*-
"""LOI per-parameter grouping using actual definitions without Revit assemblies."""
import ast
from pathlib import Path
from types import SimpleNamespace as Item

from lowlife import loi_check_core as core


def scope_with_definitions(**scope):
    path = Path(__file__).resolve().parents[1] / 'lib/lowlife/loi_check.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names = {'ElementRow', 'CategoryResult', 'check_category', 'build_3d_views'}
    tree.body = [node for node in tree.body
                 if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    scope.update(core=core, VIEW_3D_NAME='LOI', FILLED_FILTER_NAME='Filled')
    exec(compile(tree, str(path), 'exec'), scope)
    return scope


def test_check_category_preserves_actual_required_failures():
    elements = [Item(code='known'), Item(code='other')]
    plan = Item(UNKNOWN='unknown', NO_CODE='no_code',
                required_for=lambda code: ([u'Empty', u'Absent'], 'matched')
                if code == 'known' else (None, 'unknown'))
    scope = scope_with_definitions(
        collect_elements=lambda doc, cat: elements,
        element_info=lambda doc, el: ('Type', 'Family', None),
        read_param=lambda doc, el, param, el_type:
            (True, el.code) if param == 'Code' else (param != 'Absent', None),
        floor_text=lambda *args: '1')
    result = scope['check_category'](None, Item(Name='Equipment'),
                                    [(p, p) for p in ['Empty', 'Absent', 'Optional']],
                                    None, plan, 'Code')
    assert result.summary.total == 1
    assert result.unknown_codes == {'other': 1}
    assert len(result.incomplete_rows) == 1
    assert result.incomplete_rows[0].missing_params == ['Empty', 'Absent']


def test_views_combine_categories_without_sharing_filters_or_duplicating_elements():
    calls = []

    def build(doc, elements, categories, name, filter_name):
        calls.append((sorted(el.Id.IntegerValue for el in elements), categories, name, filter_name))
        return name, 10, 2

    scope = scope_with_definitions(build_3d_view=build)
    a, b = Item(Id=Item(IntegerValue=1)), Item(Id=Item(IntegerValue=2))
    results = [
        Item(category='Equipment', rows=[('A', 'p1'), ('B', 'p2'), ('C', 'filled')],
             incomplete_rows=[Item(element=a, missing_params=['p1', 'p2', 'p1'])]),
        Item(category='Trays', rows=[('A', 'p1')],
             incomplete_rows=[Item(element=b, missing_params=['p1'])])]
    views = scope['build_3d_views'](None, results)
    assert calls == [([1, 2], ['Equipment', 'Trays'], 'LOI — p1', 'Filled — p1'),
                     ([1], ['Equipment', 'Trays'], 'LOI — p2', 'Filled — p2')]
    assert [v[0] for v in views] == ['p1', 'p2']
    assert [v[2] for v in views] == [2, 1]
    scope['build_3d_views'](None, results)
    assert calls[:2] == calls[2:]
    assert scope['build_3d_views'](None, []) == []


def test_cleaned_name_collisions_remain_stable_when_one_parameter_is_fixed():
    calls = []

    def build(doc, elements, categories, name, filter_name):
        calls.append((name, filter_name))
        return name, 0, 0

    scope = scope_with_definitions(build_3d_view=build)
    row = Item(element=Item(Id=Item(IntegerValue=1)), missing_params=['A:B', 'A?B'])
    results = [Item(category='Equipment', rows=[('A', 'A:B'), ('B', 'A?B')],
                    incomplete_rows=[row])]
    scope['build_3d_views'](None, results)
    row.missing_params = ['A?B']
    scope['build_3d_views'](None, results)
    assert calls == [('LOI — A_B', 'Filled — A_B'),
                     ('LOI — A_B (2)', 'Filled — A_B (2)'),
                     ('LOI — A_B (2)', 'Filled — A_B (2)')]
