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


def test_button_folder_round_trip():
    ref = _ref(u"Tools", u"Pull", u"Button")
    name = fc.button_folder(ref)
    assert name == u"Tools-Pull-Button"
    assert fc.parse_button_folder(name) == ref
    assert fc.parse_button_folder(u"PlaceRouteNodes") is None


def test_slots():
    assert fc.slot_name(0) == u"MyPanel1"
    assert fc.is_slot(u"MyPanel8")
    assert not fc.is_slot(u"MyPanels")
    assert not fc.is_slot(u"SCS")
    # копию кнопки со своей панели на свою панель не кладём
    assert not fc.can_add(_ref(u"MyPanel1", u"SCS-A"))


def test_tab_layout_lists_every_slot():
    # pyRevit создаёт только панели из layout вкладки
    import io, os
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), u"LowLife.tab", u"bundle.yaml")
    with io.open(path, encoding=u"utf-8") as f:
        layout = [line.strip()[2:] for line in f if line.strip().startswith(u"- ")]
    assert [fc.slot_name(i) for i in range(fc.MAX_PANELS)] == [n for n in layout if fc.is_slot(n)]


def test_panel_bundle_quotes_title():
    text = fc.panel_bundle(u'Мои "цепи"', [u"SCS-A", u"SKUD-B"])
    assert text == u'title: "Мои \\"цепи\\""\nlayout:\n  - SCS-A\n  - SKUD-B\n'


def test_plan_skips_missing_and_empty_and_extra_panels():
    entries = [{u"panel": u"SCS", u"path": [u"A"], u"title": u"А"},
               {u"panel": u"SKUD", u"path": [u"A"], u"title": u"Б"}]
    data = {u"panels": [{u"title": u"пустая", u"buttons": [_ref(u"SCS", u"нет")]},
                        {u"title": u"моя", u"buttons": [_ref(u"SCS", u"A"), _ref(u"SKUD", u"A")]}]}
    data[u"panels"] += [{u"title": u"п{}".format(i), u"buttons": [_ref(u"SCS", u"A")]} for i in range(fc.MAX_PANELS)]
    panels, problems = fc.plan(data, entries)
    assert len(panels) == fc.MAX_PANELS
    assert panels[0] == (u"MyPanel1", u"моя", [(u"SCS-A", entries[0]), (u"SKUD-A", entries[1])])
    assert len(problems) == 2  # кнопки нет в LowLife + панель не поместилась


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
    # папка копии узнаётся — так статистика запусков находит исходную кнопку
    assert fc.find_entry(entries, fc.parse_button_folder(fc.button_folder(ref))) is entry


def test_folder_names_have_no_separator():
    # на дефисе держится имя папки копии (папки исходной через BUTTON_SEP)
    for entry in ribbon_catalog.list_buttons():
        assert all(fc.BUTTON_SEP not in part for part in [entry[u"panel"]] + entry[u"path"])


def test_manager_button_is_not_addable():
    # кнопка «Создать мою панель» (панель LowLife) — окно настройки, на свою панель её не кладём
    manager = _ref(u"_Themes", u"MyPanels")
    assert not fc.can_add(manager)
    assert fc.can_add(_ref(u"SCS", u"A"))
    data = fc.normalize({u"panels": [{u"title": u"моя", u"buttons": [manager, _ref(u"SCS", u"A")]}]})
    assert data[u"panels"][0][u"buttons"] == [_ref(u"SCS", u"A")]
    data, added = fc.add_button(data, u"моя", manager)
    assert not added
    entries = ribbon_catalog.list_buttons()
    assert any(e[u"panel"] == u"_Themes" and e[u"button"] == u"MyPanels" for e in entries)
    assert fc.can_add(_ref(u"_Themes", u"Search"))  # остальные кнопки панели LowLife — можно
    assert not fc.can_add(_ref(u"Favorites", u"Manage"))  # прежнее место кнопки
