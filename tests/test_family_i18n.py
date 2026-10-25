# -*- coding: utf-8 -*-
"""Run display adapters without importing Revit or WPF."""
import ast
import os
from types import SimpleNamespace

from lowlife import i18n


def _definitions(name, functions, constants=(), namespace=None):
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lib', 'lowlife', name + '.py')
    with open(path, encoding='utf-8') as stream:
        tree = ast.parse(stream.read(), path)
    tree.body = [node for node in tree.body if
                 isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in functions or
                 isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in node.targets)]
    scope = {'tr': i18n.tr, 'N_': i18n.N_, 'unicode': str}
    scope.update(namespace or {})
    exec(compile(tree, path, 'exec'), scope)
    return scope


def test_catalog_statuses_translate_without_changing_comparisons_or_colors(monkeypatch):
    brushes = SimpleNamespace(Firebrick='red', DarkOrange='orange', Green='green', Gray='gray')
    names = ['STATUS_STALE', 'STATUS_CURRENT', 'STATUS_NO_STAMP', 'STATUS_NO_CATALOG', 'STALE_TOLERANCE_SEC']
    scope = _definitions('family_catalog', ['stamp_status', '_StatusRow', '_status_brush'], names, {'Brushes': brushes})
    entry = SimpleNamespace(mtime=200, mtime_iso='date', rel=u'Каталог/Устройство.rfa')
    mr = SimpleNamespace(family_name=u'Устройство', family=SimpleNamespace(FamilyCategory=SimpleNamespace(Name=u'Категория')),
                         status=scope['stamp_status']({'epoch': 1}, entry), stamp={'iso': 'old'}, entry=entry, score=1)
    assert mr.status == u'устарело'
    for lang, text in [(i18n.EN, 'outdated'), (i18n.RU, u'устарело')]:
        monkeypatch.setattr(i18n, 'current', lambda: lang)
        row = scope['_StatusRow'](mr)
        assert row.Status == text
        assert scope['_status_brush'](row.mr.status) == 'red'
        assert row.FamilyName == u'Устройство' and row.CatalogFile == entry.rel
        assert mr.status == u'устарело'
        assert scope['stamp_status']({}, entry) == u'нет метки'
        assert scope['stamp_status']({'epoch': 200}, entry) == u'актуально'


def test_section_choices_translate_only_sentinel_and_keep_raw_selection(monkeypatch):
    class Items(list):
        Add = list.append
    class Combo(object):
        def __init__(self):
            self.Items = Items()
    scope = _definitions('family_section_settings', ['_combo', '_parse_mm'], ['NO_TEMPLATE', 'DEFAULT_TYPE'], {'ComboBox': Combo})
    parent = SimpleNamespace(Children=Items())
    raw = [scope['NO_TEMPLATE'], u'Шаблон проекта']
    monkeypatch.setattr(i18n, 'current', lambda: i18n.EN)
    combo = scope['_combo'](parent, raw, raw[1])
    assert combo.Items == ['<No template>', u'Шаблон проекта']
    assert raw[combo.SelectedIndex] == u'Шаблон проекта'
    assert scope['_combo'](parent, raw, scope['NO_TEMPLATE']).SelectedIndex == 0
    errors = []
    assert scope['_parse_mm']('-1', 'Left and right', errors) is None
    assert errors == ['“Left and right” — cannot be negative']
    monkeypatch.setattr(i18n, 'current', lambda: i18n.RU)
    assert scope['_combo'](parent, raw, raw[1]).Items == raw


def test_family_summaries_translate_but_user_names_in_errors_are_preserved(monkeypatch):
    scope = _definitions('family_catalog', ['result_summary_lines', 'load_summary_lines', '_compact_symbol_errors', '_invalid_name_chars'])
    result = {key: [] for key in ['updated', 'renamed', 'unchanged', 'failed', 'rename_failed', 'stamp_failed', 'loaded']}
    result['updated'] = [u'Семейство']
    monkeypatch.setattr(i18n, 'current', lambda: i18n.EN)
    assert scope['result_summary_lines'](result) == ['Updated: 1']
    assert scope['load_summary_lines'](result) == ['New families loaded: 0', 'Reloaded: 1']
    errors = scope['_compact_symbol_errors']([(u'Тип|1', u'Ошибка Revit')])
    assert errors[0] == u'Ошибка Revit (types: 1, e.g. “Тип|1”)'
    assert errors[1] == 'type names contain characters prohibited by Revit: |'
