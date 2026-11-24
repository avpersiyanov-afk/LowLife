# -*- coding: utf-8 -*-
"""Тесты для lowlife.panel_themes — темы ленты (комбобокс «Тема» на
панели LowLife)."""

import os
import sys
import types

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
    assert u"_Themes" not in other  # «LowLife» видна всегда
    assert dict(panel_themes._always_visible_panels()) == {u"_Themes": u"LowLife"}
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


def test_favorite_panels_are_discovered_separately(tmpdir):
    root = str(tmpdir)
    folder = os.path.join(root, "LowLife.tab", "MyPanel1.panel")
    os.makedirs(folder)
    with open(os.path.join(folder, "bundle.yaml"), "w", encoding="utf-8") as f:
        f.write('title: "My custom panel"\n')
    assert panel_themes._favorite_panels(root) == [(u"MyPanel1", u"My custom panel")]


def test_favorite_panels_visible_only_in_mine_theme(monkeypatch):
    class AdWindowsPanel(object):
        IsVisible = True

    class Panel(object):
        def __init__(self):
            self.visible = True
            self.adwindows = AdWindowsPanel()

        def __iter__(self):
            return iter(())

        def get_adwindows_object(self):
            return self.adwindows

    favorite = Panel()

    class Tab(object):
        def find_child(self, title):
            return favorite if title == u"My custom panel" else None

    class UI(object):
        def get_pyrevit_tabs(self):
            return [Tab()]

    ribbon = types.ModuleType("pyrevit.coreutils.ribbon")
    ribbon.get_current_ui = lambda: UI()
    coreutils = types.ModuleType("pyrevit.coreutils")
    coreutils.ribbon = ribbon
    pyrevit = types.ModuleType("pyrevit")
    pyrevit.coreutils = coreutils
    monkeypatch.setitem(sys.modules, "pyrevit", pyrevit)
    monkeypatch.setitem(sys.modules, "pyrevit.coreutils", coreutils)
    monkeypatch.setitem(sys.modules, "pyrevit.coreutils.ribbon", ribbon)
    monkeypatch.setattr(panel_themes, "_ribbon_name", lambda folder: folder)
    monkeypatch.setattr(panel_themes, "_favorite_panels",
                        lambda: [(u"MyPanel1", u"My custom panel")])
    monkeypatch.setattr(panel_themes, "_always_visible_panels", lambda: [])
    monkeypatch.setattr(panel_themes, "_other_panels", lambda: [])

    panel_themes.apply_theme(u"SCS")
    assert not favorite.visible
    assert not favorite.adwindows.IsVisible
    panel_themes.apply_theme(panel_themes.MINE)
    assert favorite.visible
    assert favorite.adwindows.IsVisible
