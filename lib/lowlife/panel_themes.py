# -*- coding: utf-8 -*-
"""Ribbon buttons grouped by discipline theme, for the theme ComboBox switcher.

Each entry maps a theme label (shown in the ComboBox) to (panel_folder_name,
button_folder_name) pairs — the bundle directory names as they appear on
disk under LowLife.tab (without the .panel/.pushbutton suffix), which is
what pyRevit uses as the internal component name (see
GenericUIComponent.name in pyrevit/extensions/genericcomps.py). Button
__title__ text is not used for lookup because it is not guaranteed unique
across panels (SOUE and SPS both have buttons titled "Цепи шлейфов").

SetupParameters buttons across all disciplines are grouped under their own
"Settings" theme rather than staying always-visible.
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
    u"Settings": [
        (u"SCS", u"SetupParameters"),
        (u"SKUD", u"SetupParameters"),
        (u"SOUE", u"SetupParameters"),
        (u"SPS", u"SetupParameters"),
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

THEME_NAMES = [u"SCS", u"ACS", u"FAS", u"FAD", u"Settings", u"General"]


def _find_panel(pyrevit_tabs, panel_name):
    for tab in pyrevit_tabs:
        panel = tab.find_child(panel_name)
        if panel is not None:
            return panel
    return None


def apply_theme(selected_theme):
    """Show only the buttons belonging to selected_theme; hide the rest.

    Panels that end up with no visible button (e.g. SKUD.panel when the
    General theme is selected) are hidden too, so no empty panel frame
    is left on the ribbon.
    """
    from pyrevit.coreutils.ribbon import get_current_ui

    pyrevit_tabs = get_current_ui().get_pyrevit_tabs()

    touched_panel_names = set()
    for button_refs in THEMES.values():
        for panel_name, _ in button_refs:
            touched_panel_names.add(panel_name)

    for theme_name, button_refs in THEMES.items():
        visible = theme_name == selected_theme
        for panel_name, button_name in button_refs:
            panel = _find_panel(pyrevit_tabs, panel_name)
            if panel is None:
                continue
            button = panel.find_child(button_name)
            if button is not None:
                button.visible = visible

    for panel_name in touched_panel_names:
        panel = _find_panel(pyrevit_tabs, panel_name)
        if panel is None:
            continue
        panel_visible = any(
            child.visible for child in panel if hasattr(child, "visible")
        )
        panel.visible = panel_visible
        # RibbonPanel.Visible alone can leave an empty strip on the ribbon
        # until the layout is rebuilt; the underlying Autodesk.Windows
        # panel's IsVisible is what the ribbon actually renders from.
        adwindows_panel = panel.get_adwindows_object()
        if adwindows_panel is not None:
            adwindows_panel.IsVisible = panel_visible
