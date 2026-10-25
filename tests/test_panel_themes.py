# -*- coding: utf-8 -*-
"""Тесты для lowlife.panel_themes — темы ленты (комбобокс «Тема» на
панели LowLife)."""

import os

import pytest

from lowlife import panel_themes

TAB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "LowLife.tab")
_BUTTON_KINDS = ("pushbutton", "pulldown", "splitbutton", "splitpushbutton",
                 "smartbutton", "linkbutton", "urlbutton", "combobox", "stack")


def _registered():
    return set(ref for refs in panel_themes.THEMES.values() for ref in refs)


def test_every_button_of_a_themed_panel_is_registered():
    # кнопку, забытую в THEMES, apply_theme прячет при любой теме
    refs = _registered()
    missing = []
    for panel in sorted(set(p for p, _ in refs)):
        folder = os.path.join(TAB, panel + ".panel")
        for name in os.listdir(folder):
            base, _dot, kind = name.rpartition(".")
            if kind in _BUTTON_KINDS and (panel, base) not in refs:
                missing.append((panel, base))
    assert missing == []


def test_every_registered_button_exists():
    stale = [(p, b) for p, b in _registered()
             if not any(os.path.isdir(os.path.join(TAB, p + ".panel", b + "." + k))
                        for k in _BUTTON_KINDS)]
    assert stale == []


def test_theme_names_match_combobox_members():
    with open(os.path.join(TAB, "_Themes.panel", "ThemeSelector.combobox", "bundle.yaml"),
              encoding="utf-8") as f:
        text = f.read().split("members_en:")[0]  # английские подписи — отдельный блок (lowlife.ribbon_language)
        ids = [line.split(":", 1)[1].strip() for line in text.splitlines() if line.strip().startswith("- id:")]
    assert sorted(ids) == sorted(panel_themes.THEMES)
    assert sorted(panel_themes.THEME_NAMES) == sorted(panel_themes.THEMES)


@pytest.fixture
def appdata(tmpdir, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmpdir))
    monkeypatch.setattr(panel_themes, "_STORE", None)
    return tmpdir


def test_selected_theme_is_remembered(appdata):
    assert panel_themes.load_selected() is None
    panel_themes.save_selected(u"КНК")
    assert panel_themes.load_selected() == u"КНК"
    panel_themes.save_selected(u"нет такой")  # не тема — не сохраняется
    assert panel_themes.load_selected() == u"КНК"


def test_mine_theme_leaves_only_lowlife_and_user_panels():
    # «Моя панель»: все панели LowLife спрятаны (кнопок в теме нет), панели вне THEMES — тоже,
    # кроме панели LowLife со списком тем; ячейки своих панелей пользователя не трогаются
    assert panel_themes.THEMES[panel_themes.MINE] == []
    other = dict(panel_themes._other_panels())
    assert u"_Themes" not in other and u"Info" not in other  # «LowLife» и «Справка» — видны всегда
    assert dict(panel_themes._always_visible_panels()) == {u"_Themes": u"LowLife", u"Info": u"Справка"}
    assert u"Favorites" not in other  # «Создать мою панель» — на панели LowLife
    assert not any(name.startswith(u"MyPanel") for name in other)
    themed = set(p for refs in panel_themes.THEMES.values() for p, _ in refs)
    on_disk = set(n[:-len(".panel")] for n in os.listdir(TAB) if n.endswith(".panel"))
    assert on_disk - themed - set(other) <= set(panel_themes.ALWAYS_VISIBLE) | set(
        n for n in on_disk if n.startswith(u"MyPanel"))


def _layout(folder):
    from lowlife import ribbon_catalog
    return ribbon_catalog.read_bundle(folder)[1]


def test_every_panel_is_in_the_tab_layout():
    # панель, которой нет в layout: вкладки, pyRevit не строит вовсе
    listed = set(_layout(TAB))
    on_disk = set(n[:-len(".panel")] for n in os.listdir(TAB) if n.endswith(".panel"))
    assert sorted(on_disk - listed) == []
    themed = set(p for refs in panel_themes.THEMES.values() for p, _ in refs)
    assert sorted(themed - listed) == []


def test_every_button_is_in_its_container_layout():
    # то же для кнопок внутри панели/стека со своим layout:
    missing = []
    for root, dirs, _files in os.walk(TAB):
        layout = _layout(root) if root != TAB else None
        if not layout:
            continue
        for name in dirs:
            base, _dot, kind = name.rpartition(".")
            if kind in _BUTTON_KINDS and base not in layout:
                missing.append(os.path.relpath(os.path.join(root, name), TAB))
    assert missing == []


def test_panels_are_found_by_their_ribbon_title():
    assert panel_themes._ribbon_name(u"SCS") == u"СКС"
    assert panel_themes._ribbon_name(u"ToolsCables") == u"Кабели"
    assert panel_themes._ribbon_name(u"LOI") == u"Заполнение LOI"
