# -*- coding: utf-8 -*-
"""Ribbon buttons grouped by discipline theme, for the theme ComboBox switcher.

Each entry maps a theme label (shown in the ComboBox) to (panel_folder_name,
button_folder_name) pairs — the bundle directory names as they appear on
disk under LowLife.tab (without the .panel/.pushbutton suffix), which is
what pyRevit uses as the internal component name (see
GenericUIComponent.name in pyrevit/extensions/genericcomps.py). Button
__title__ text is not used for lookup because it is not guaranteed unique
across panels (e.g. every discipline has its own SetupParameters button).

Circuit-building buttons for each discipline live on their own dedicated
panel (CircuitsSCS.panel "Цепи СКС", CircuitsSKUD.panel "Цепи СКУД",
CircuitsSPS.panel "Цепи СПС", CircuitsSPA.panel "Цепи СПА"), separate from
that discipline's main panel (SCS.panel, SKUD.panel, SPS.panel). Each of
these buttons is listed under BOTH its own discipline's theme AND the
cross-discipline "Circuits" theme ("Электрические цепи" in the ComboBox) —
so picking a discipline theme shows that discipline's circuit button among
its other tools, while picking "Электрические цепи" shows all of them
together regardless of discipline.

DeleteViewCircuits lives on its own CircuitsDelete.panel ("Удаление") and
is cross-discipline (deletes any circuit type), so it is only listed under
"Circuits", not under a specific discipline theme.

SetupParameters buttons across all disciplines are grouped under their own
"Settings" theme rather than staying always-visible.

Tray*.panel ("Лестничный лоток"/"Неперфорированный лоток"/"Перфорированный
лоток"/"Проволочный лоток"/"Лотки на кровле") are grouped under their own
theme, "КНК" — named after the workset every one of their buttons switches
to (see lowlife.cable_tray.DEFAULT_WORKSET_FILTER), not after a discipline,
since tray creation isn't tied to one specific discipline's devices.

Every button in every panel referenced below MUST have an entry in some
theme's list. apply_theme() defaults any button it finds in a touched panel
but can't find in `visibility` to hidden — so a forgotten registration
makes the button disappear (safe, obvious) rather than making the whole
panel permanently visible regardless of the selected theme (the bug this
replaced: ExportAddressesToExcel and DeleteViewCircuits were missing from
THEMES, which pinned SCS.panel and Tools.panel visible under every theme).
"""

THEMES = {
    u"SCS": [
        (u"SCS", u"PlaceRouteNodes"),
        (u"SCS", u"RenumberAddresses"),
        (u"SCS", u"SyncCircuitsAndLengths"),
        (u"SCS", u"ExportAddressesToExcel"),
        (u"CircuitsSCS", u"BuildCircuitsSCS"),
    ],
    u"ACS": [
        (u"SKUD", u"PlaceSkudRouteNodes"),
        (u"SKUD", u"RenumberSkudAddresses"),
        (u"SKUD", u"AssignCircuitsAndCables"),
        (u"SKUD", u"CalcSkudLengths"),
        (u"SKUD", u"BuildSkudSchematic"),
        (u"SKUD", u"InspectSchematicDevices"),
        (u"CircuitsSKUD", u"BuildCircuitsSKUD"),
    ],
    u"FAS": [
        (u"SOUE", u"BuildLoopCircuits"),
        (u"SOUE", u"CalcLoopLengths"),
    ],
    u"FAD": [
        (u"CircuitsSPS", u"BuildLoopCircuitsSPS"),
        (u"SPS", u"CalcLoopLengths"),
        (u"SPS", u"InspectConnectors"),
        (u"CircuitsSPS", u"BuildIsolatorCircuitsSPS"),
    ],
    u"SPA": [
        (u"CircuitsSPA", u"BuildCircuitsSPA"),
    ],
    u"КНК": [
        (u"TrayLadder", u"TraySPZo"),
        (u"TrayLadder", u"TraySPZp"),
        (u"TrayLadder", u"TraySB"),
        (u"TrayLadder", u"TraySS"),
        (u"TrayUnperforated", u"TraySPZo"),
        (u"TrayUnperforated", u"TraySPZp"),
        (u"TrayUnperforated", u"TraySB"),
        (u"TrayUnperforated", u"TraySS"),
        (u"TrayPerforated", u"TraySPZo"),
        (u"TrayPerforated", u"TraySPZp"),
        (u"TrayPerforated", u"TraySB"),
        (u"TrayPerforated", u"TraySS"),
        (u"TrayWire", u"TraySPZo"),
        (u"TrayWire", u"TraySPZp"),
        (u"TrayWire", u"TraySB"),
        (u"TrayWire", u"TraySS"),
        (u"TrayRoof", u"TraySPZo"),
        (u"TrayRoof", u"TraySPZp"),
        (u"TrayRoof", u"TraySB"),
        (u"TrayRoof", u"TraySS"),
    ],
    u"Circuits": [
        (u"CircuitsSCS", u"BuildCircuitsSCS"),
        (u"CircuitsSKUD", u"BuildCircuitsSKUD"),
        (u"CircuitsSPS", u"BuildLoopCircuitsSPS"),
        (u"CircuitsSPS", u"BuildIsolatorCircuitsSPS"),
        (u"CircuitsSPA", u"BuildCircuitsSPA"),
        (u"CircuitsDelete", u"DeleteViewCircuits"),
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

THEME_NAMES = [u"SCS", u"ACS", u"FAS", u"FAD", u"SPA", u"КНК", u"Circuits", u"Settings", u"General"]

# A pyRevit RibbonPanel's runtime .name mirrors the Revit API RibbonPanel.Name,
# which pyRevit sets to the panel's DISPLAYED title (bundle.yaml `title:`), not
# its bundle folder name — the two only coincide when a panel has no bundle.yaml
# title override (confirmed via pyrevit/coreutils/ribbon.py: CreateRibbonPanel is
# called with the title string, and _PyRevitRibbonPanel has no separate field that
# preserves the folder name). Every panel below has a `title:` in its bundle.yaml,
# so find_child(folder_name) can never match it; this maps folder name -> title so
# _find_panel can look panels up by what they are actually named at runtime.
PANEL_RIBBON_NAMES = {
    u"CircuitsSCS": u"Цепи СКС",
    u"CircuitsSKUD": u"Цепи СКУД",
    u"CircuitsSPS": u"Цепи СПС",
    u"CircuitsSPA": u"Цепи СПА",
    u"CircuitsDelete": u"Удаление",
    u"TrayLadder": u"Лестничный лоток",
    u"TrayUnperforated": u"Неперфорированный лоток",
    u"TrayPerforated": u"Перфорированный лоток",
    u"TrayWire": u"Проволочный лоток",
    u"TrayRoof": u"Лотки на кровле",
}


def _find_panel(pyrevit_tabs, panel_name):
    ribbon_name = PANEL_RIBBON_NAMES.get(panel_name, panel_name)
    for tab in pyrevit_tabs:
        panel = tab.find_child(ribbon_name)
        if panel is not None:
            return panel
    return None


def apply_theme(selected_theme):
    """Show only the buttons belonging to selected_theme; hide the rest.

    A button can be listed under more than one theme (e.g. every
    CircuitsSCS/SKUD/SPS/SPA button is listed both under its own
    discipline's theme and under the cross-discipline "Circuits" theme).
    Visibility is computed as a union across all entries a button appears
    in — set True if ANY of its entries matches selected_theme — rather
    than overwritten per entry, because plain dict iteration order isn't
    guaranteed and a naive "last entry processed wins" would make such a
    button's final state depend on that order.

    Every actual child of a touched panel is visited (not just the ones
    listed in THEMES) and defaults to hidden if it has no entry in
    `visibility`. A button accidentally left out of THEMES therefore just
    disappears from the ribbon instead of staying permanently visible,
    which would otherwise pin its whole panel visible under every theme
    (any(child.visible for child in panel) is True forever once one
    untracked child never gets its .visible turned off).

    Panels that end up with no visible button (e.g. SKUD.panel when the
    General theme is selected) are hidden too, so no empty panel frame
    is left on the ribbon.
    """
    from pyrevit.coreutils.ribbon import get_current_ui

    pyrevit_tabs = get_current_ui().get_pyrevit_tabs()

    visibility = {}
    for theme_name, button_refs in THEMES.items():
        for ref in button_refs:
            visibility[ref] = visibility.get(ref, False) or (theme_name == selected_theme)

    touched_panel_names = set(panel_name for panel_name, _ in visibility)

    for panel_name in touched_panel_names:
        panel = _find_panel(pyrevit_tabs, panel_name)
        if panel is None:
            continue
        panel_visible = False
        for child in panel:
            if not hasattr(child, "visible"):
                continue
            child_visible = visibility.get((panel_name, child.name), False)
            child.visible = child_visible
            panel_visible = panel_visible or child_visible
        panel.visible = panel_visible
        # RibbonPanel.Visible alone can leave an empty strip on the ribbon
        # until the layout is rebuilt; the underlying Autodesk.Windows
        # panel's IsVisible is what the ribbon actually renders from.
        adwindows_panel = panel.get_adwindows_object()
        if adwindows_panel is not None:
            adwindows_panel.IsVisible = panel_visible
