# -*- coding: utf-8 -*-
"""Тесты для lowlife.favorites_core — панели «Избранного»."""

from lowlife import favorites_core as fc
from lowlife import ribbon_catalog


def _ref(panel, *path):
    return {u"panel": panel, u"path": list(path)}


def test_normalize_drops_junk_and_duplicates():
    data = {u"panels": [
        {u"title": u"  Мои   цепи ", u"buttons": [_ref(u"SCS", u"A"), _ref(u"SCS", u"A"), {u"panel": u"X"}, u"x"]},
        {u"title": u"мои цепи", u"buttons": []},  # та же подпись без учёта регистра
        {u"title": u"", u"buttons": [_ref(u"SCS", u"B")]},
        u"мусор",
    ]}
    assert fc.normalize(data) == {u"panels": [{u"title": u"Мои цепи", u"buttons": [_ref(u"SCS", u"A")]}]}
    assert fc.normalize(None) == {u"panels": []}
    assert fc.normalize({u"panels": u"не список"}) == {u"panels": []}


def test_button_name_round_trip():
    ref = _ref(u"Tools", u"Pull", u"Button")
    name = fc.button_name(ref)
    assert u"%" not in name
    assert fc.parse_button_name(name) == ref
    assert fc.parse_button_name(u"PlaceRouteNodes") is None
    assert fc.parse_button_name(fc.BUTTON_PREFIX + u"SCS") is None


def test_panel_name_prefix():
    assert fc.is_favorite_panel(fc.panel_name(u"Мои"))
    assert not fc.is_favorite_panel(u"Цепи СКС")
    assert not fc.is_favorite_panel(None)


def test_title_problem():
    assert fc.title_problem(u"  ", []) is not None
    assert fc.title_problem(u"x" * (fc.MAX_TITLE + 1), []) is not None
    assert fc.title_problem(u"a%b", []) is not None
    assert fc.title_problem(u"мои", [u"Мои"]) is not None
    assert fc.title_problem(u"цепи скс", [], reserved=[u"Цепи СКС"]) is not None
    assert fc.title_problem(u"Мои цепи", [u"Другие"], reserved=[u"Цепи СКС"]) is None


def test_add_button_creates_panel_and_skips_duplicates():
    data, added = fc.add_button({}, u"Мои", _ref(u"SCS", u"A"))
    assert added
    data, added = fc.add_button(data, u"мои", _ref(u"SCS", u"B"))
    assert added
    data, added = fc.add_button(data, u"Мои", _ref(u"SCS", u"A"))
    assert not added
    assert data == {u"panels": [{u"title": u"Мои", u"buttons": [_ref(u"SCS", u"A"), _ref(u"SCS", u"B")]}]}


def test_move():
    items = [1, 2, 3]
    assert fc.move(items, 0, -1) == 0 and items == [1, 2, 3]
    assert fc.move(items, 0, 1) == 1 and items == [2, 1, 3]
    assert fc.move(items, 2, 5) == 2 and items == [2, 1, 3]
    assert fc.move(items, 7, 1) == 7


def test_refs_resolve_against_real_catalog():
    entries = ribbon_catalog.list_buttons()
    entry = next(e for e in entries if e[u"panel"] == u"SCS" and e[u"button"] == u"PlaceRouteNodes")
    ref = fc.button_ref(entry)
    assert fc.find_entry(entries, ref) is entry
    assert fc.find_entry(entries, _ref(u"SCS", u"НетТакой")) is None
    # имя кнопки избранного узнаётся по папкам — так статистика запусков находит исходную кнопку
    assert fc.find_entry(entries, fc.parse_button_name(fc.button_name(ref))) is entry


def test_folder_names_have_no_dots():
    # на точках держится имя кнопки избранного (BUTTON_PREFIX + папки через точку)
    for entry in ribbon_catalog.list_buttons():
        assert all(u"." not in part for part in [entry[u"panel"]] + entry[u"path"])
