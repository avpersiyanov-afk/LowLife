[Русский](../cable-tray-panels.md) | **English**

# Tray*.panel — creating cable trays

Five panels on the LowLife ribbon, each for one tray construction, with four identical buttons («Tray SPZo» / «Tray SPZp» / «Tray SB» / «Tray SS» — by the system the tray is laid for). 20 buttons in total; all the logic is in `lib/lowlife/cable_tray.py` (`run_tray_button`), the settings in `lib/lowlife/cable_tray_settings.py`.

## What to create in the project

1. **Cable tray types.** The button doesn't create a type, it looks for an existing one. Create in the project (or load from a template) cable tray types whose names contain the text from the table below — one type per button. The name may be longer (for example `КЛ_СБ_ЛЛ_1.5_СЦ_200х100`), but the text must occur in exactly one type.
2. **A workset** with «КНК» in its name (exactly one). The buttons put new trays into it. The project must be workshared.

If the types or the workset in your project are named differently, don't rename them — change the text in the button settings (see below).

Default type names:

| Panel | Tray SPZo | Tray SPZp | Tray SB | Tray SS |
|---|---|---|---|---|
| Ladder tray | `СПЗо_ЛЛ_1.5_СЦ` | `СПЗп_ЛЛ_1.5_СЦ` | `СБ_ЛЛ_1.5_СЦ` | `СС_ЛЛ_1.5_СЦ` |
| Solid tray | `СПЗо_ЛН_1.5_СЦ` | `СПЗп_ЛН_1.5_СЦ` | `СБ_ЛН_1.5_СЦ` | `СС_ЛН_1.5_СЦ` |
| Perforated tray | `СПЗо_ЛП_1.5_СЦ` | `СПЗп_ЛП_1.5_СЦ` | `СБ_ЛП_1.5_СЦ` | `СС_ЛП_1.5_СЦ` |
| Wire mesh tray | `СПЗо_ЛВ_1.5_СЦ` | `СПЗп_ЛВ_1.5_СЦ` | `СБ_ЛВ_1.5_СЦ` | `СС_ЛВ_1.5_СЦ` |
| Roof trays | `СПЗо_ЛП_1.5_ГЦ` | `СПЗп_ЛП_1.5_ГЦ` | `СБ_ЛП_1.5_ГЦ` | `СС_ЛП_1.5_ГЦ` |

The panels live in the `TrayLadder.panel`, `TrayUnperforated.panel`, `TrayPerforated.panel`, `TrayWire.panel`, `TrayRoof.panel` folders.

## Settings (Shift+click)

Shift+click on **any** tray button opens one shared settings window for all tray buttons:

- **Workset** — part of the name of the workset the buttons put trays into; «КНК» by default.
- **Type names** — by panel («Ladder tray», «Solid tray», …), each with four fields: «Tray SPZo / SPZp / SB / SS — part of the type name». The defaults are the values from the table above.

«Reset» brings back the defaults. The settings are kept in `%APPDATA%\pyRevit\LowLifeCableTray_settings.json`; they can be exported and loaded on another computer.

## What the button does

1. Looks among the project's `CableTrayType`s for exactly one type whose name contains the text set for this button in the settings. If there are 0 or more than 1 such types — a message and a stop, no guessing.
2. Looks among the user worksets for exactly one whose name contains the text from the «Workset» setting and makes it active (`WorksetTable.SetActiveWorksetId`) — so the new tray is created in the right workset.
3. Starts Revit's own interactive «Cable Tray» tool with the found type through `UIDocument.PostRequestForElementTypePlacement` — from there you draw the tray with the mouse as usual.

If your Revit version doesn't support `PostRequestForElementTypePlacement`, the button still switches the workset and tells you which type to pick by hand in the «Cable Tray» tool.

## Themes (`_Themes.panel`)

All five panels and all 20 buttons are registered in `panel_themes.THEMES` under their own theme — `u"КНК"` (named after the workset they switch the project to rather than a discipline: creating trays isn't tied to one particular system). In the theme switcher (`ThemeSelector.combobox`) this is the «Trays» item («КНК» in Russian). Choosing it shows only the Tray*.panel panels; any other theme hides them — like the other disciplines.

Since every Tray*.panel has its own `title:` in bundle.yaml (for example «Лестничный лоток» for `TrayLadder.panel`), and `RibbonPanel.Name` at runtime is the displayed title, not the folder name, panels are looked up by the title read from their bundle.yaml (otherwise `_find_panel` would look for the panel by the folder name `"TrayLadder"` and not find it on the ribbon — the recurring «panel ignores the theme switcher» bug caused by title ≠ folder name).
