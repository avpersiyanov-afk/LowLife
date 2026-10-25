# -*- coding: utf-8 -*-
"""Тесты выбора языка (lowlife.i18n) и английских подписей ленты (title_en/tooltip_en в bundle.yaml)."""

import os

import pytest

from lowlife import favorites_core, i18n, panel_themes, ribbon_catalog, ribbon_language

TAB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "LowLife.tab")


@pytest.fixture
def appdata(tmpdir, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmpdir))
    i18n._STORE = None
    i18n._CACHE.update({"mtime": None, "lang": None})
    yield tmpdir
    i18n._STORE = None
    i18n._CACHE.update({"mtime": None, "lang": None})


def test_russian_is_the_default(appdata):
    assert i18n.current() == i18n.RU
    assert i18n.tr(u"Цепи", u"Circuits") == u"Цепи"


def test_saved_language_is_used(appdata):
    assert i18n.save(i18n.EN) == i18n.EN
    assert i18n.current() == i18n.EN
    assert i18n.tr(u"Цепи", u"Circuits") == u"Circuits"
    assert i18n.tr(u"Только по-русски") == u"Только по-русски"  # перевода нет — русский
    assert i18n.pick({"ru": u"Да", "en": u"Yes"}) == u"Yes"
    assert i18n.save("de") is None and i18n.current() == i18n.EN


def _panel_folders():
    return [os.path.join(TAB, n) for n in sorted(os.listdir(TAB))
            if n.endswith(".panel") and not favorites_core.is_slot(n[:-len(".panel")])]


def _button_folders():
    for panel in _panel_folders():
        for root, dirs, _files in os.walk(panel):
            for d in dirs:
                if os.path.splitext(d)[1] in ribbon_catalog.BUTTON_EXTS:
                    folder = os.path.join(root, d)
                    if os.path.exists(os.path.join(folder, "bundle.yaml")) or \
                            os.path.exists(os.path.join(folder, "script.py")):
                        yield folder


def test_every_panel_has_an_english_title():
    missing = [os.path.basename(f) for f in _panel_folders() if not ribbon_catalog.item_title_en(f)]
    assert missing == []


def test_every_button_has_an_english_title_and_tooltip():
    # новая кнопка — сразу с title_en (и tooltip_en, если у неё есть подсказка) в bundle.yaml
    no_title, no_tooltip = [], []
    for folder in _button_folders():
        text = ribbon_catalog.raw_bundle_text(folder)
        name = os.path.relpath(folder, TAB)
        if not text[u"title_en"]:
            no_title.append(name)
        if (text[u"tooltip"] or ribbon_catalog._script_doc(folder)) and not text[u"tooltip_en"]:
            no_tooltip.append(name)
    assert no_title == []
    assert no_tooltip == []


def test_theme_list_has_english_labels_for_every_theme():
    members = ribbon_catalog.read_members_en(os.path.join(TAB, "_Themes.panel", "ThemeSelector.combobox"))
    assert sorted(members) == sorted(panel_themes.THEME_NAMES)
    assert all(m.get(u"text") for m in members.values())


def test_english_tooltip_keeps_pyrevit_tail():
    original = u"Подсказка\n\nBundle Name:\nКнопка (pushbutton)"
    assert ribbon_language.english_tooltip(original, u"Tooltip") == u"Tooltip\n\nBundle Name:\nКнопка (pushbutton)"
    assert ribbon_language.english_tooltip(u"Подсказка", u"Tooltip") == u"Tooltip"
    assert ribbon_language.english_tooltip(u"Подсказка", u"") == u"Подсказка"
    assert ribbon_language._ribbon_text(u"Route\\nnodes") == u"Route\nnodes"


def test_panel_index_is_keyed_by_the_russian_ribbon_name():
    index = ribbon_language.panel_index()
    folder, buttons = index[u"СКС"]
    assert folder.endswith(u"SCS.panel")
    assert u"PlaceRouteNodes" in buttons
    assert u"Search" in index[u"LowLife"][1]  # кнопки стека тоже


def test_search_finds_buttons_by_english_caption():
    found = ribbon_catalog.search(ribbon_catalog.list_buttons(), u"route nodes")
    assert found[0][u"button"] in (u"PlaceRouteNodes", u"PlaceSkudRouteNodes")
    entry = found[0]
    assert ribbon_catalog.localized(entry, u"title", u"en") == entry[u"title_en"]
    assert ribbon_catalog.localized(entry, u"title", u"ru") == entry[u"title"]
    assert entry[u"panel_title_en"]


def test_language_window_marks_current_and_maps_back():
    from lowlife import language_ui
    options = dict(language_ui._options(i18n.EN))
    assert options == {u"Русский": i18n.RU, u"✓ English": i18n.EN}
    assert language_ui.chosen_language(u"Русский", i18n.EN) == i18n.RU
    assert language_ui.chosen_language(u"✓ English", i18n.EN) == i18n.EN
    assert language_ui.chosen_language(u"Deutsch", i18n.EN) is None
