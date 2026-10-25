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
these buttons (and SOUE.panel/BuildLoopCircuits, which has no Circuits*
panel of its own) is listed under BOTH its own discipline's theme AND the
cross-discipline "Circuits" theme ("Электрические цепи" in the ComboBox) —
so picking a discipline theme shows that discipline's circuit button among
its other tools, while picking "Электрические цепи" shows all of them
together regardless of discipline.

DeleteViewCircuits lives on its own CircuitsDelete.panel ("Удаление") and
is cross-discipline (deletes any circuit type), so it is only listed under
"Circuits", not under a specific discipline theme — as are CircuitsGeneric
("Цепи (общее)") and the wire catalog that circuits' «Проводник» comes from
(ToolsCables.panel, "Кабели").

SetupParameters buttons across all disciplines are grouped under their own
"Settings" theme rather than staying always-visible; Tools.panel/FopParameters
(creates the parameters in the shared-parameter file and binds them) is
listed there too, as well as under "General".

The discipline-agnostic tools are split across several small panels for
readability instead of one jumbled Tools.panel: Tools.panel ("Инструменты"),
FilterSelection.panel ("Фильтр выбора"), Schematic.panel ("Схемы" — the
room-based schematic draft), ToolsRooms.panel ("Помещения"),
ToolsSchedules.panel ("Спецификации"), ToolsFamilies.panel ("Семейства"),
LOI.panel ("Заполнение LOI"), Music.panel and Mail.panel ("Почта"). Every
button on them is listed under the single "General"
theme ("Общее" in the ComboBox), so picking "Общее" shows the whole set
together.

"Service" theme ("Служебное" in the ComboBox) holds rarely-needed helpers
that live on their own ToolsExport.panel ("Выгрузка") — RenameExportFiles,
RenameByList and CaptureExportCommand — kept off the "General" list so
they don't clutter the everyday toolset (the rename runs itself on export
anyway).

Tray*.panel ("Лестничный лоток"/"Неперфорированный лоток"/"Перфорированный
лоток"/"Проволочный лоток"/"Лотки на кровле") are grouped under their own
theme, "КНК" — named after the workset every one of their buttons switches
to (see lowlife.cable_tray.DEFAULT_WORKSET_FILTER), not after a discipline,
since tray creation isn't tied to one specific discipline's devices. The
tray helpers on Tools.panel (TagTrays, LinkTraysToExcel, TrayOpeningBoxes)
and ToolsTraySection.panel ("Сечение лотка") are listed under both "КНК" and
"General".

Notes.panel ("Заметки") is deliberately outside THEMES: it stays visible
under every theme except «Моя панель» (see _other_panels), like the
always-visible _Themes.panel/Info.panel.

Every panel folder must also be listed in LowLife.tab/bundle.yaml `layout:`
— pyRevit doesn't build a panel missing from it at all (SPA, LOI,
FilterSelection, Schematic and ToolsTraySection once were, and never showed
up). tests/test_panel_themes.py checks both lists.

Every button in every panel referenced below MUST have an entry in some
theme's list. apply_theme() defaults any button it finds in a touched panel
but can't find in `visibility` to hidden — so a forgotten registration
makes the button disappear (safe, obvious) rather than making the whole
panel permanently visible regardless of the selected theme (the bug this
replaced: ExportAddressesToExcel and DeleteViewCircuits were missing from
THEMES, which pinned SCS.panel and Tools.panel visible under every theme).
"""

# «Моя панель»: на вкладке остаются только свои панели пользователя («Мои панели», lowlife.favorites)
# и панель LowLife с этим списком; прячутся и панели вне THEMES (см. _other_panels).
MINE = u"Mine"

THEMES = {
    MINE: [],
    u"SCS": [
        (u"SCS", u"PlaceRouteNodes"),
        (u"SCS", u"RenumberAddresses"),
        (u"SCS", u"SyncCircuitsAndLengths"),
        (u"SCS", u"ShowCircuitRoute"),
        (u"SCS", u"BuildScsSchematic"),
        (u"CircuitsSCS", u"BuildCircuitsSCS"),
    ],
    u"ACS": [
        (u"SKUD", u"PlaceSkudRouteNodes"),
        (u"SKUD", u"RenumberSkudAddresses"),
        (u"SKUD", u"AssignCircuitsAndCables"),
        (u"SKUD", u"CalcSkudLengths"),
        (u"SKUD", u"ShowCircuitRoute"),
        (u"SKUD", u"AssignSkudRooms"),
        (u"SKUD", u"BuildSkudSchematic"),
        (u"SKUD", u"InspectSchematicDevices"),
        (u"SKUD", u"PlaceDoorAccessPoints"),
        (u"CircuitsSKUD", u"BuildCircuitsSKUD"),
    ],
    u"SOT": [
        (u"SOT", u"BuildSotSchematic"),
        (u"SOT", u"CameraFov"),
        (u"SOT", u"AimCameras"),
        (u"SOT", u"CameraParamsCheck"),
        (u"SOT", u"CameraPreviewView"),
    ],
    u"FAS": [
        (u"SOUE", u"BuildLoopCircuits"),
        (u"SOUE", u"CalcLoopLengths"),
        (u"SOUE", u"PlaceTypicalFloor"),
    ],
    u"FAD": [
        (u"CircuitsSPS", u"BuildLoopCircuitsSPS"),
        (u"SPS", u"CalcLoopLengths"),
        (u"SPS", u"ShowCircuitRoute"),
        (u"SPS", u"InspectConnectors"),
        (u"SPS", u"BuildSpsSchematic"),
        (u"SPS", u"DetectorsToSlab"),
        (u"SPS", u"DetectorAccess"),
        (u"CircuitsSPS", u"BuildIsolatorCircuitsSPS"),
    ],
    u"SPA": [
        (u"CircuitsSPA", u"BuildLoopCircuitsSPA"),
        (u"CircuitsSPA", u"CalcLoopLengthsSPA"),
        (u"SPA", u"PlaceCompanionDevices"),
    ],
    u"SS1": [
        (u"SS1", u"SS1Easy"),
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
        (u"ToolsTraySection", u"TraySection"),
        (u"Tools", u"TagTrays"),
        (u"Tools", u"LinkTraysToExcel"),
        (u"Tools", u"TrayOpeningBoxes"),
    ],
    u"Circuits": [
        (u"CircuitsSCS", u"BuildCircuitsSCS"),
        (u"CircuitsSKUD", u"BuildCircuitsSKUD"),
        (u"CircuitsSPS", u"BuildLoopCircuitsSPS"),
        (u"CircuitsSPS", u"BuildIsolatorCircuitsSPS"),
        (u"CircuitsSPA", u"BuildLoopCircuitsSPA"),
        (u"SOUE", u"BuildLoopCircuits"),
        (u"CircuitsGeneric", u"BuildGenericCircuits"),
        (u"CircuitsGeneric", u"WriteLoadName"),
        (u"CircuitsGeneric", u"WritePanelName"),
        (u"CircuitsDelete", u"DeleteViewCircuits"),
        (u"CircuitsDelete", u"HighlightNoCircuit"),
        (u"ToolsCables", u"WireCatalog"),
        (u"ToolsCables", u"WireCatalogEdit"),
        (u"ToolsCables", u"WireCatalogExport"),
        (u"ToolsCables", u"WireCatalogImport"),
    ],
    u"Settings": [
        (u"SCS", u"SetupParameters"),
        (u"SKUD", u"SetupParameters"),
        (u"Tools", u"FopParameters"),
    ],
    u"General": [
        (u"Tools", u"DimensionGrids"),
        (u"Tools", u"GenericModelLength"),
        (u"Tools", u"ZoomToElement"),
        (u"Tools", u"CopyElementId"),
        (u"Tools", u"FamilySection"),
        (u"Tools", u"AlignViewRange"),
        (u"Tools", u"LevelViews"),
        (u"Tools", u"Rotate3DView"),
        (u"Tools", u"Greeting"),
        (u"Tools", u"SpellCheck"),
        (u"Tools", u"DwgToDrafting"),
        (u"Tools", u"FopParameters"),
        (u"Tools", u"ParkingMarks"),
        (u"Tools", u"TagTrays"),
        (u"Tools", u"TagEquipment"),
        (u"Tools", u"CropView"),
        (u"Tools", u"LineBypass"),
        (u"Tools", u"LinkTraysToExcel"),
        (u"Tools", u"TrayOpeningBoxes"),
        (u"Tools", u"CompareLinkDatums"),
        (u"ToolsTraySection", u"TraySection"),
        (u"FilterSelection", u"CategoryFilterSelect"),
        (u"Schematic", u"BuildRoomSchematic"),
        (u"ToolsRooms", u"RoomInfo"),
        (u"ToolsRooms", u"RoomTags"),
        (u"ToolsRooms", u"FindRoom"),
        (u"ToolsRooms", u"RoomLots"),
        (u"ToolsRooms", u"DiagnoseRoomTag"),
        (u"ToolsRooms", u"FragmentExplication"),
        (u"ToolsRooms", u"UpdateExplication"),
        (u"ToolsSchedules", u"SplitScheduleOnSheet"),
        (u"ToolsSchedules", u"ScheduleToExcel"),
        (u"ToolsSchedules", u"ScheduleFromExcel"),
        (u"ToolsSchedules", u"ModelToJson"),
        (u"ToolsSchedules", u"JsonToModel"),
        (u"ToolsFamilies", u"LoadFamiliesFromCatalog"),
        (u"ToolsFamilies", u"UpdateFamiliesFromCatalog"),
        (u"LOI", u"FillLOI"),
        (u"LOI", u"CheckLOI"),
        (u"LOI", u"FillFloor"),
        (u"LOI", u"UpdateLevelName"),
        (u"Music", u"PlayPause"),
        (u"Music", u"Previous"),
        (u"Music", u"Next"),
        (u"Music", u"VolumeDown"),
        (u"Music", u"VolumeUp"),
        (u"Mail", u"EmailTasks"),
    ],
    u"Service": [
        (u"ToolsExport", u"RenameExportFiles"),
        (u"ToolsExport", u"RenameByList"),
        (u"ToolsExport", u"CaptureExportCommand"),
    ],
}

THEME_NAMES = [MINE, u"SCS", u"ACS", u"SOT", u"FAS", u"FAD", u"SPA", u"SS1", u"КНК", u"Circuits", u"Settings", u"General", u"Service"]

# A pyRevit RibbonPanel's runtime .name mirrors the Revit API RibbonPanel.Name,
# which pyRevit sets to the panel's DISPLAYED title (bundle.yaml `title:`), not
# its bundle folder name — the two only coincide when a panel has no bundle.yaml
# title override (confirmed via pyrevit/coreutils/ribbon.py: CreateRibbonPanel is
# called with the title string). So panels are looked up by the title read from
# their bundle.yaml (ribbon_catalog.item_title) — no hand-kept folder -> title map
# to forget when a panel gets a title.
def _ribbon_name(panel_folder):
    import os
    from lowlife import ribbon_catalog
    return ribbon_catalog.item_title(os.path.join(
        ribbon_catalog.extension_root(), ribbon_catalog.TAB_FOLDER, panel_folder + u".panel"))


def _find_panel(pyrevit_tabs, ribbon_name):
    for tab in pyrevit_tabs:
        panel = tab.find_child(ribbon_name)
        if panel is not None:
            return panel
    return None


# Панели, которые видны при любой теме, даже «Моя панель»: _Themes.panel («LowLife» — в ней список тем)
# и Info.panel («Справка» — «О программе» и «Обратная связь»).
ALWAYS_VISIBLE = (u"_Themes", u"Info")


def _always_visible_panels(root=None):
    """[(папка, подпись)] панелей ALWAYS_VISIBLE, которые есть на диске."""
    import os
    from lowlife import ribbon_catalog
    tab = os.path.join(root or ribbon_catalog.extension_root(), ribbon_catalog.TAB_FOLDER)
    result = []
    for stem in ALWAYS_VISIBLE:
        folder = os.path.join(tab, stem + u".panel")
        if os.path.isdir(folder):
            result.append((stem, ribbon_catalog.item_title(folder)))
    return result


def _other_panels(root=None):
    """[(папка, подпись)] панелей вкладки, которых нет в THEMES, кроме ALWAYS_VISIBLE и своих панелей
    пользователя: обычно видны всегда, при «Моя панель» — прячутся."""
    import os
    from lowlife import favorites_core, ribbon_catalog
    tab = os.path.join(root or ribbon_catalog.extension_root(), ribbon_catalog.TAB_FOLDER)
    themed = set(panel for refs in THEMES.values() for panel, _ in refs)
    result = []
    for name in sorted(os.listdir(tab)):
        stem, ext = os.path.splitext(name)
        if ext != u".panel" or stem in themed or stem in ALWAYS_VISIBLE or favorites_core.is_slot(stem):
            continue
        result.append((stem, ribbon_catalog.item_title(os.path.join(tab, name))))
    return result


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
        panel = _find_panel(pyrevit_tabs, _ribbon_name(panel_name))
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

    # Панели вне THEMES («Заметки», «Фильтр выбора», …): при «Моя панель» прячутся, при остальных — видны.
    # ALWAYS_VISIBLE показываем всегда — вдруг их спрятала прежняя версия темы «Моя панель».
    show_other = selected_theme != MINE
    for _folder, title in _always_visible_panels():
        panel = _find_panel(pyrevit_tabs, title)
        if panel is not None:
            panel.visible = True
            adwindows_panel = panel.get_adwindows_object()
            if adwindows_panel is not None:
                adwindows_panel.IsVisible = True
    for _folder, title in _other_panels():
        panel = _find_panel(pyrevit_tabs, title)
        if panel is None:
            continue
        panel.visible = show_other
        adwindows_panel = panel.get_adwindows_object()
        if adwindows_panel is not None:
            adwindows_panel.IsVisible = show_other


# ------------------------------------------------------------
# ВЫБРАННАЯ ТЕМА МЕЖДУ ЗАПУСКАМИ
# ------------------------------------------------------------
#
# pyRevit при загрузке (запуск Revit, перезагрузка, обновление расширения)
# заново строит ленту: все кнопки видимы, а событие выбора темы в
# комбобоксе не приходит — фильтр включался только после ручной смены
# темы. Поэтому выбранная тема запоминается (save_selected — из
# обработчика комбобокса), а startup.py расширения (pyRevit выполняет его
# при каждой загрузке, но до построения ленты) ставит её обратно при
# первом простое Revit (restore_on_idle): в комбобоксе и на ленте.

THEME_PANEL_TITLE = u"LowLife"  # _Themes.panel — title из bundle.yaml

_STORE = None


def _store():
    global _STORE
    if _STORE is None:
        from lowlife import settings_core
        _STORE = settings_core.JsonStore("LowLifeTheme_settings.json", u"темы ленты",
                                         share=False)
    return _STORE


def save_selected(theme_name):
    """Запомнить выбранную тему (id участника комбобокса)."""
    if theme_name in THEMES:
        _store().update({"theme": theme_name})


def load_selected():
    """Запомненная тема или None."""
    name = _store().read().get("theme")
    return name if name in THEMES else None


def _theme_combobox(uiapp):
    """Revit-комбобокс «Тема» на панели LowLife или None."""
    from Autodesk.Revit.UI import ComboBox
    for panel in uiapp.GetRibbonPanels(u"LowLife"):
        if panel.Name != THEME_PANEL_TITLE and panel.Title != THEME_PANEL_TITLE:
            continue
        for item in panel.GetItems():
            if isinstance(item, ComboBox):
                return item
    return None


def _combobox_theme(cmb):
    """Тема, которую показывает комбобокс сейчас, или None."""
    try:
        cur = cmb.Current
        if cur is not None and cur.Name in THEMES:
            return cur.Name
    except Exception:
        pass
    return None


def restore_theme(uiapp, theme_name=None):
    """
    Включить тему theme_name (по умолчанию — запомненную, иначе ту, что
    показывает комбобокс): выбрать её в комбобоксе и применить к ленте.
    Возвращает применённую тему или None.
    """
    cmb = None
    try:
        cmb = _theme_combobox(uiapp)
    except Exception:
        cmb = None
    name = theme_name or (_combobox_theme(cmb) if cmb is not None else None)
    if not name:
        return None
    if cmb is not None and _combobox_theme(cmb) != name:
        try:
            for member in cmb.GetItems():
                if member.Name == name:
                    cmb.Current = member  # обработчик комбобокса тоже применит тему
                    break
        except Exception:
            pass
    apply_theme(name)
    return name


def restore_on_idle(app):
    """
    Из startup.py: при первом простое Revit (лента к этому времени
    достроена) включить запомненную тему. Тема читается сразу — до того,
    как комбобокс при построении ленты успеет что-то сохранить. app —
    UIApplication или UIControlledApplication (у обоих есть Idling).
    """
    saved = load_selected()
    state = {"done": False}

    def on_idle(sender, args):
        if state["done"]:
            return
        state["done"] = True
        try:
            app.Idling -= on_idle
        except Exception:
            pass
        try:
            restore_theme(sender, saved)
        except Exception:
            pass

    app.Idling += on_idle

