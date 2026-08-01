# -*- coding: utf-8 -*-
"""Ribbon buttons grouped by discipline theme, for the theme ComboBox switcher.

Each entry maps a theme label (shown in the ComboBox) to (panel_folder_name,
button_folder_name) pairs — the bundle directory names as they appear on
disk under LowLife.tab (without the .panel/.pushbutton suffix), which is
what pyRevit uses as the internal component name (see
GenericUIComponent.name in pyrevit/extensions/genericcomps.py). Button
__title__ text is not used for lookup because it is not guaranteed unique
across panels (SOUE and SPS both have buttons titled "Цепи шлейфов").

SetupParameters buttons are intentionally excluded: each panel keeps its
own Settings button visible regardless of the selected theme.
"""

THEMES = {
    u"SCS": [
        (u"SCS", u"PlaceRouteNodes"),
        (u"SCS", u"RenumberAddresses"),
        (u"SCS", u"SyncCircuitsAndLengths"),
    ],
    u"ACS": [
        (u"SKUD", u"PlaceSkudRouteNodes"),
        (u"SKUD", u"RenumberSkudAddresses"),
        (u"SKUD", u"AssignCircuitsAndCables"),
        (u"SKUD", u"CalcSkudLengths"),
        (u"SKUD", u"BuildSkudSchematic"),
    ],
    u"FAS": [
        (u"SOUE", u"BuildLoopCircuits"),
        (u"SOUE", u"CalcLoopLengths"),
    ],
    u"FAD": [
        (u"SPS", u"BuildLoopCircuits"),
        (u"SPS", u"CalcLoopLengths"),
    ],
    u"General": [
        (u"Tools", u"DimensionGrids"),
        (u"Tools", u"GenericModelLength"),
        (u"Tools", u"Hello"),
        (u"Music", u"PlayPause"),
        (u"Music", u"Previous"),
        (u"Music", u"Next"),
        (u"Music", u"VolumeDown"),
        (u"Music", u"VolumeUp"),
    ],
}

THEME_NAMES = [u"SCS", u"ACS", u"FAS", u"FAD", u"General"]


def _find_button(pyrevit_tabs, panel_name, button_name):
    for tab in pyrevit_tabs:
        panel = tab.find_child(panel_name)
        if panel is not None:
            button = panel.find_child(button_name)
            if button is not None:
                return button
    return None


def apply_theme(selected_theme):
    """Show only the buttons belonging to selected_theme; hide the rest."""
    from pyrevit.coreutils.ribbon import get_current_ui

    pyrevit_tabs = get_current_ui().get_pyrevit_tabs()
    for theme_name, button_refs in THEMES.items():
        visible = theme_name == selected_theme
        for panel_name, button_name in button_refs:
            button = _find_button(pyrevit_tabs, panel_name, button_name)
            if button is not None:
                button.visible = visible
