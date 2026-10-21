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
        ids = [line.split(":", 1)[1].strip() for line in f if line.strip().startswith("- id:")]
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
