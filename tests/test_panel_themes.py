# -*- coding: utf-8 -*-
"""Тесты для lowlife.panel_themes — каждая кнопка панели с темой должна быть в THEMES.

apply_theme() прячет кнопку, которой нет ни в одной теме, — забытая
регистрация молча убирает кнопку с ленты.
"""

import os

from lowlife import panel_themes

_TAB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "LowLife.tab")

# Ribbon items apply_theme() sees as a panel's children. A .stack is not an
# item itself: its buttons sit directly in the panel.
_ITEM_SUFFIXES = (".pushbutton", ".pulldown", ".splitbutton", ".splitpushbutton",
                  ".smartbutton", ".linkbutton", ".invokebutton", ".urlbutton",
                  ".panelbutton", ".combobox", ".nobutton")


def _panel_items(panel_dir):
    items = []
    for name in sorted(os.listdir(panel_dir)):
        path = os.path.join(panel_dir, name)
        if not os.path.isdir(path):
            continue
        if name.endswith(".stack"):
            items.extend(_panel_items(path))
        elif name.endswith(_ITEM_SUFFIXES):
            items.append(name.rsplit(".", 1)[0])
    return items


def _registered():
    return set(ref for refs in panel_themes.THEMES.values() for ref in refs)


def _themed_panels():
    return sorted(set(panel for panel, _ in _registered()))


def test_themed_panels_exist():
    missing = [p for p in _themed_panels()
               if not os.path.isdir(os.path.join(_TAB_DIR, p + u".panel"))]
    assert missing == []


def test_every_button_of_themed_panel_is_in_a_theme():
    registered = _registered()
    missing = []
    for panel in _themed_panels():
        panel_dir = os.path.join(_TAB_DIR, panel + u".panel")
        if not os.path.isdir(panel_dir):
            continue
        for button in _panel_items(panel_dir):
            if (panel, button) not in registered:
                missing.append((panel, button))
    assert missing == [], u"Кнопки без темы в panel_themes.THEMES: %r" % (missing,)


def test_every_registered_button_exists():
    stale = []
    for panel, button in sorted(_registered()):
        panel_dir = os.path.join(_TAB_DIR, panel + u".panel")
        if os.path.isdir(panel_dir) and button not in _panel_items(panel_dir):
            stale.append((panel, button))
    assert stale == [], u"Записи THEMES без кнопки на диске: %r" % (stale,)


def test_theme_names_match_themes():
    assert sorted(panel_themes.THEME_NAMES) == sorted(panel_themes.THEMES)
