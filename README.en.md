<p align="center">
  <img src="docs/brand/lowlife-logo.png" width="120" alt="LowLife logo">
  <br><br>
  <img src="docs/brand/lowlife-wordmark.png" width="520" alt="LowLife">
</p>

<p align="center"><a href="README.md">Русский</a> | <b>English</b></p>

# LowLife

A pyRevit extension for designing low-voltage systems (structured cabling, access control, fire alarm, voice alarm, fire automation, CCTV) in Autodesk Revit: IronPython/CPython 2 scripts that run inside Revit through pyRevit.

The ribbon is available in Russian and English — pick the language with the **«Language / Язык»** button on the LowLife panel, under «Create my panel» (the switch is instant, no pyRevit reload). Windows and messages are being translated panel by panel; until then some of them are still in Russian.

> [!WARNING]
> **This is a test product.** The buttons that build riser diagrams — «Riser diagram» for SCS/ACS/CCTV/fire alarm, «Riser diagram draft» and others — have had little testing, and the result can be unpredictable. Every change the buttons make can be undone with **Ctrl+Z** in Revit.

News, updates and discussion — in the Telegram channel [t.me/rvt_lowlife](https://t.me/rvt_lowlife) (in Russian).

## A note on names

LowLife comes from Russian design practice, so the systems carry their Russian abbreviations in folder names, settings and parameter names:

| Abbreviation | System | In English |
|---|---|---|
| СКС (SCS) | структурированная кабельная система | structured cabling |
| СКУД (SKUD) | система контроля и управления доступом | access control (ACS) |
| СОТ (SOT) | система охранного телевидения | CCTV |
| СПС (SPS) | система пожарной сигнализации | fire alarm |
| СОУЭ (SOUE) | система оповещения и управления эвакуацией | voice alarm / evacuation |
| СПА (SPA) | система пожарной автоматики | fire automation |
| СС1 (SS1) | сети связи | communication networks |
| КНК | кабеленесущие конструкции | cable trays |
| ФОП | файл общих параметров | shared parameters file |

## Installation

Add the extension to pyRevit by this repository's URL (Extensions → Add from GitHub URL). pyRevit clones the repository into `%APPDATA%\pyRevit\Extensions\LowLife.extension\` by itself — the `LowLife.tab` folder must stay at the repository root; there is no separate `.extension` wrapper folder in the repository, and there must not be one.

To update — pull again through the pyRevit extension manager and reload pyRevit / restart Revit.

## Supported Revit versions

| Revit version | Status |
|---|---|
| 2024 | the main working version — API behaviour is checked on it |
| 2025, 2026 | supported: Revit's move to .NET 8 is handled (opening links, Outlook, ending processes) |
| 2022–2023 | should work: where the API changed there are fallbacks to the old calls (`ElementId.IntegerValue`, `ParameterType`), but it hasn't been tested separately |
| 2021 and older | not supported |

The buttons have no hard version limit (`min_revit_version`/`max_revit_version` aren't set): the extension loads in any Revit the installed pyRevit supports. The scripts are written in IronPython 2 for pyRevit's standard engine, so you need a pyRevit version that supports your Revit (for Revit 2025+ — pyRevit 5.x).

The same information and your current Revit version are shown in the «About» window (the «Help» panel at the end of the LowLife tab). If you change the table, update `REVIT_SUPPORT` in `lib/lowlife/about.py` too.

## Parameters

Which parameters which element categories need (route nodes, devices, panels, electrical circuits, schematic families, views) is in the overall list [docs/en/parameters.md](docs/en/parameters.md). The «About» window links to it as well.

The fastest way to prepare a project is the **«Shared parameters»** button (Tools panel): it shows the parameters the chosen systems need, suggests similar ones from your shared parameters file, binds them to categories and writes the names into the buttons' settings. A role has the same name in every button — a name entered in one button is filled into the others. Revit's built-in parameters (circuit «Panel», «Load Name», «Wire», workset) aren't asked for in the settings — the buttons handle them themselves.

## Panels and buttons

The first ribbon panel is **LowLife**: the «Search» button finds any LowLife button by name (or by a word from its tooltip) and runs it right away (Enter) or shows it on the ribbon (Ctrl+Enter — opens the tab, and the button blinks with an orange fill even if the selected theme hides it). «Create my panel» — build your own panels from the LowLife buttons you need (from different panels, in your own order, by drag and drop) — they appear on the ribbon right after the LowLife panel and are visible under any theme; a button can also be added from «Search» («To my panel»). The LowLife panel also has the «Theme» list — it switches which panels/buttons are visible on the ribbon: by discipline (SCS/ACS/CCTV/voice alarm/fire alarm/fire automation/SS1), by group (trays, electrical circuits, settings, general, service) or «My panel» — only your own panels (plus «LowLife» and «Help»). The third small button, under «Create my panel», is «Language / Язык»: a window to choose Russian or English. The last panel is **Help** (small buttons): «About» (the extension version — the commit pyRevit installed it from — and a link to the repository; there is also a «Show greeting when Revit starts» checkbox, off by default) and «Feedback» — tell the author about a problem or suggest an improvement (pick a panel and button + a description; messages go to the author's Google Sheet, [instructions →](docs/en/feedback-panel.md)). LowLife also sends the author button usage statistics (which button, when, who — no model content) to see what to improve first; switch it off with the checkbox in the «About» window. Most working buttons have Shift+click — it opens the settings of that particular button (there is no single settings window per panel). More about the LowLife panel buttons and themes — [docs/en/general-panels.md](docs/en/general-panels.md).

<details>
<summary><b>SCS</b> — structured cabling</summary>

- **Route nodes** — places panels/route nodes/risers at the points of a cable route.
- **Node addresses** — numbers route node addresses per floor, starting from panels/risers.
- **Circuit length** — calculates cable lengths along the route and circuit numbers/routes for the target panels.
- **Riser diagram** — builds/updates the SCS riser diagram: its own coloured bus (collector + riser) per panel, incremental update on a re-run.
- **Circuit route** — highlights in the model the route of the selected SCS circuit (for checking).
- **Bind parameters** — checks/adds the binding of SCS parameters to categories from the connected shared parameters file.

[Instructions →](docs/en/scs-panel.md)
</details>

<details>
<summary><b>ACS</b> — access control</summary>

- **ACS route nodes** — places ACS route nodes/risers (separate from the SCS nodes).
- **ACS node addresses** — numbers ACS route node addresses from controllers/risers.
- **Circuits and cables** — gives devices an address, wire type and load name, tags controllers.
- **Lengths and tags** — calculates the wire length of every controller → device circuit.
- **Access point rooms** — gives the ACS devices of an access point one shared room.
- **Access points on doors** — places access point elements (reader, lock, door closer, reed switch, buttons, intercom) on the doors of the selected rooms by the door layout; Shift+click — the door layout and access point types.
- **Riser diagram** — builds/updates the ACS riser diagram, incrementally. [Setup →](docs/en/skud-schematic-setup.md)
- **Circuit route** — highlights in the model the route of the selected ACS circuit.
- **Diagnostics: diagram devices** — test button: shows the circuits and devices of the selected controller.
- **Bind parameters** — checks/adds the binding of ACS parameters to categories from the shared parameters file.

[Instructions →](docs/en/skud-panel.md)
</details>

<details>
<summary><b>CCTV</b> — video surveillance</summary>

- **Aim at room** — calculates and writes the camera tilt by the room boundary.
- **Fields of view** — draws a camera's field of view (as a filled region), clipped by the room boundary. [Instructions →](docs/en/camera-fov.md)
- **Riser diagram** — builds/updates the CCTV riser diagram, incrementally. [Instructions →](docs/en/schematics.md)
- **View from camera** — creates/updates a 3D perspective view from the camera's point with its azimuth, tilt and field of view.
- **Check parameters** — diagnostics: which parameters of the selected camera fit the roles of the field-of-view calculation, where the orientation comes from, family breakdown. Doesn't change the model.
</details>

<details>
<summary><b>Voice alarm</b> — warning and evacuation control</summary>

- **Loop circuits** — creates one electrical circuit per loop and connects it to its panel.
- **Loop lengths** — calculates the length of every loop from device coordinates and tags the devices. [Instructions →](docs/en/fire-alarm-panels.md)
- **Voice alarm — typical floor** — speakers in every room of the architectural link: in each apartment (lot) — on a hallway wall; in the other rooms (except excluded ones) — the number, positions and the speaker itself with its power tap from an acoustic calculation (noise + 15 dB at 1.5 m): wall speakers on walls and columns, ceiling speakers under a suspended ceiling; chosen from all project types with SPL/power/version parameters. Noise comes from the project's room table (a category catalog, Excel export/import). [Instructions →](docs/en/soue-typical-floor.md)
</details>

<details>
<summary><b>Fire alarm</b></summary>

- **Fire alarm riser diagram** — builds/updates the riser diagram, including isolator branches and loop rings, incrementally. [Instructions →](docs/en/schematics.md)
- **Loop lengths** — calculates the length of every loop from device coordinates. [Instructions →](docs/en/fire-alarm-panels.md)
- **Circuit route** — highlights in the model the route (tree) of the selected loop.
- **Detectors to slab** — moves fire detectors to the underside of the slab above them (different slab elevations, architectural/structural links) and labels on plans the slab height above the floor, slab steps as a thick red line, and rooms with a suspended ceiling (a «ПП» filled region with the ceiling height). [Instructions →](docs/en/detectors-to-slab.md)
- **Detector access** — checks whether a detector can be reached from the floor: there is a floor, the detector isn't above a suspended ceiling or closer than 500 mm to a wall, and building services (in the model and links) don't block the access zone from the floor up to it. On plans it circles the access zone (green/red) and, for inaccessible ones, shows the nearest free spot with an arrow and the move distance. [Instructions →](docs/en/detector-access.md)
- **Connector diagnostics** — test button: shows the categories and electrical connectors of the selected elements.
</details>

<details>
<summary><b>Fire automation</b></summary>

- **Place relay, control modules** — places a companion device next to every configured base object, with an offset and parameters copied over. [Instructions →](docs/en/companion-placement.md)
</details>

<details>
<summary><b>SS1</b> — communication networks</summary>

- **SS1-8Mile** — places SS1 equipment: two cross-connects in every telecom shaft on every ticked level and a cable entry by the door from the hallway to the corridor/lobby on the apartment side (from the architectural link), circuits from cross-connect No. 1 of the shaft of its section to each entry, LOI filling, «Room» and the entries' address by a mask. Before placing, old instances of the chosen types on the ticked levels are deleted. Shift+click — settings. [Instructions →](docs/en/ss1.md)
</details>

<details>
<summary><b>Diagrams</b> — draft diagrams</summary>

- **Riser diagram draft** — builds a draft riser diagram by rooms (not by devices): in one window you write, for each floor, how a room should be shown on the diagram (the same label — a shared box); typical floors fill in by themselves, labels are remembered. [Instructions →](docs/en/room-schematic.md)
</details>

<details>
<summary><b>LOI filling</b> — filling parameters by context</summary>

- **Fill LOI** — copies parameters from «Masses» category elements to elements inside the mass solid (including from links); linear elements on mass borders are split, anything unresolved goes to a conflict table.
- **Fill floor** — writes a value by the element's level to the configured parameter (a «Level / Value» table on Shift+click).
- **LOI check** — checks whether elements of the selected categories have the parameters from the settings filled in (instance, then type), builds a schedule «LOI проверка — <category>» per category and isolates the empty elements in a 3D view; can take categories and parameters from the «LOI requirements» appendix by stage.
- **Update level name** — assigns a reference level to selected family instances with no level and no host (a level from a list or by height); if Revit won't let the «Level» parameter change, it re-creates the instance in the same place carrying over parameters and circuits.

[Instructions →](docs/en/loi-panel.md)
</details>

<details>
<summary><b>Electrical circuits</b> — SCS / ACS / fire alarm / fire automation / general / delete</summary>

- **SCS circuits** — builds SCS circuits between a panel and devices (a circuit per connector, home run). [Instructions →](docs/en/scs-panel.md)
- **ACS circuits** — manual panel (controller) → device circuits, one circuit per device. [Instructions →](docs/en/circuits-panels.md)
- **Fire alarm loop circuits** — creates a circuit per fire alarm loop and connects it to the panel. [Instructions →](docs/en/fire-alarm-panels.md)
- **Fire alarm isolator–device circuits** — builds circuits between an isolator and the selected devices.
- **Fire automation loop circuits** — builds fire automation circuits by device address (like fire alarm, the workset with the keyword «СПА»).
- **Fire automation loop lengths** — calculates the length of every fire automation loop from device coordinates.
- **Circuit (general)** — builds arbitrary panel → devices circuits entirely from settings, with no discipline logic built in; writes the cable from the catalog and the load name to the circuit's built-in «Wire» and «Load Name». [Instructions →](docs/en/circuits-panels.md)
- **Delete circuits in view** — deletes every circuit with at least one element visible in the active view.
- **Highlight unconnected** — highlights in the active view elements with electrical connectors that have no circuit yet; the highlight goes away by itself as circuits are created. Shift+click — clear the highlight right away.
</details>

<details>
<summary><b>Cable trays</b> — ladder / perforated / solid / wire mesh / roof / tray section</summary>

Five panels (ladder / perforated / solid / wire mesh / on the roof), each with four buttons of the same meaning, **Tray SB / SPZo / SPZp / SS**: they switch to the workset containing «КНК» and start placing a cable tray of the matching profile and type. [Instructions →](docs/en/cable-tray-panels.md)

- **Tray section** — draws a tray cross-section with the actual cable layout (gravity packing of circles) from Excel data on a drafting view. [Instructions →](docs/en/tray-section.md)
</details>

<details>
<summary><b>Tools</b> — general tools</summary>

- **Element ID** — shows and copies to the clipboard the ID of the selected element, including inside a linked model.
- **Dimension grids** — dimensions the selected grids in the view: a chain between neighbouring grids and an overall dimension.
- **Line length** — total length of the selected generic models by type.
- **Section by family** — builds a cropped section through the selected family or linear system element (tray, conduit, pipe, wall) with a view template, type and name by mask; in height — up to the next floor of the same building; for several elements — one shared section or one per element.
- **Views by level** — creates plans for all (or chosen) model levels from the ticked view templates, named by a mask ({Level}, {View group and purpose}, {Floor}, {Building}, {Elevation}…); an existing view with the same name only gets the template; optionally aligns the view range. [Instructions →](docs/en/level-views.md)
- **View range** — aligns the view range of plans (selected in the Project Browser, or the active one): bottom and depth — the plan's level, cut plane — +1200 mm (+900 mm if the next floor is less than 1400 mm away), top — the next floor −200 mm; the next floor is found by the level name pattern (same building, another floor) set in the button's settings (Shift+click).
- **Equipment tags** — places missing equipment tags in the active view and arranges them neatly without overlaps (a stack/column with shoulder leaders). [Instructions →](docs/en/equipment-tags.md)
- **Tray tags** — the same for cable trays: tags the selected straight segments (fittings and sloped trays aren't tagged) and arranges them neatly without overlaps; parallel trays of a run — as one block. [Instructions →](docs/en/tray-tags.md)
- **Opening boxes for trays** — places a box (a «бокс» family, «временный» type) at every crossing of the selected trays with walls and floors of the model chosen in the settings (this model, a link or all): the tray cross-section plus 50 mm, depth by the wall/floor thickness; where there's already a box, no new one is created, with a warning. [Instructions →](docs/en/tray-opening-boxes.md)
- **Line bypass** — draws a bypass arc of a given diameter where detail lines cross (single/multiple mode).
- **Link trays to Excel** — exports to .xlsx the cable trays of a linked model visible in the active view (ID, type, elevation, level, link).
- **Grids and levels vs coordination** — compares the model's levels and grids with those of the coordination (КФП) link and lists what matches, which level has a different elevation, which grid is offset or rotated, what's named differently and what's missing from the model or the link. Doesn't change the model.
- **Spell check** — sends text notes (selected, in the view or in the whole model) to AI and fixes spelling, grammar and punctuation; corrections are shown as a «was → becomes» list, only the ticked ones are written, the notes' formatting is kept. The AI is the same as for «Tasks from mail» (a shared connection). [Instructions →](docs/en/spellcheck.md)
- **DWG → drafting** — traces a DWG underlay with annotations: DWG lines become detail lines (one style or styles per DWG layer), text becomes text notes in the same place with the same rotation and paper height; into a new drafting view or onto the same view. The text is read from a DXF of the same drawing (a DXF next to the DWG, conversion with the free ODA File Converter, or a file picked by hand) — the Revit API doesn't expose DWG text.
- **Shared parameters** — the list of shared parameters the LowLife buttons of the chosen systems need (SCS, ACS, fire alarm, voice alarm, fire automation, CCTV, plus voice alarm «Typical floor», SS1, «Place relay, control modules», «Write room number», «Fill floor»), with an example name, data type and categories; if the shared parameters file already has a similar parameter (for example «Wire length» with the project's prefix), it is suggested right away; names are edited right in the table, the ticked parameters are taken from the shared parameters file or the project (missing ones are created in the file — the connected one, another or a new one — only with «Write to shared parameters file» on, off by default) and bound to the right project categories right away, and the names are written into the buttons' settings. [Instructions →](docs/en/parameters.md)
- **Greeting** — a window with a greeting in big letters: «Good morning/afternoon/evening» by the time of day and the Revit user name, and at night (23:00–5:00) and at weekends also a joking warning that you shouldn't work like that, in the daytime on weekdays (12:00–17:00) a joke about being late, on weekday evenings (17:00–23:00) that it's time to go home, and on weekday mornings a nice wish for the day; closes with a click, Enter or Esc.
- **Zoom to element** — zooms the view to the selected element or an element by ID.
- **Crop view** — crops the view and annotations to a frame from two corners picked with the mouse (plan, section, elevation, detail); after picking the frame — crop the view itself or a copy of it (plain, with detailing, dependent) with a suffix at the end of the name.
- **Rotate 3D view** — in an open 3D view, pick a grid from a list (grids of the model and links: Revit doesn't show them in 3D) or click a straight line, wall or tray (in the model or a link), and the view turns around the vertical along/across that axis (the nearest of four rotations, the tilt doesn't change); an enabled 3D section box lines its sides up parallel to the axis.
- **Parking elevations** — labels on the plan the elevations of «Parking» elements from links relative to the plan's level: luminaire zone — bottom and top, driveway and parking spaces — top, zone outlines hatched in their own colours; groups — by words in the comment, workset and family name.

More — [docs/en/tools-panel.md](docs/en/tools-panel.md).
</details>

<details>
<summary><b>Export</b></summary>

- **Rename export** — replaces «0000» with «000» in the names of exported files (DWG/PDF); can run automatically after an export in ModPlus. [Instructions →](docs/en/rename-export-files.md)
- **Rename by list** — renames files by a table of matches between two subfolders with paired files (for example DWG and PDF). [Instructions →](docs/en/rename-by-list.md)
- **Catch command id** — a diagnostic button: finds the id of a pressed ribbon button through `ComponentManager.ItemExecuted`.
</details>

<details>
<summary><b>Cables</b> — cable catalog</summary>

The cable catalog is the «Electrical Circuits» key schedule whose rows the circuit «Wire» parameter refers to.

- **Cable catalog** — finds the catalog in the model and shows its rows and the number of circuits where each row is already set.
- **Edit catalog** — a table window: edit values and add new cables (rows can't be deleted — circuits may refer to them).
- **Export catalog** — exports the catalog to .xlsx.
- **Import catalog** — loads the catalog from .xlsx: rows are matched by key name, found ones are updated, new ones added.

[Instructions →](docs/en/cable-catalog.md)
</details>

<details>
<summary><b>Families</b></summary>

- **Load families** — loads the chosen families/types from a .rfa catalog folder into the model.
- **Update/check families** — shows how up to date the model's families are and updates them from the catalog.

[Instructions →](docs/en/families-panel.md)
</details>

<details>
<summary><b>Rooms</b></summary>

- **Find room** — search, filtering by number/name and highlighting a room (including from links). [Instructions →](docs/en/rooms-panel.md)
- **Write room number** — carries a room value from the linked model into a parameter of the selected elements by a mask. [Instructions →](docs/en/room-info.md)
- **Two-level lots** — groups the link's rooms by lot name and shows only the lots whose rooms are on several levels (with the section and the list of levels).
- **Room tags** — places and fixes tags of rooms from the linked model (including orphaned/shifted ones). [Instructions →](docs/en/room-tags.md)
- **Tag diagnostics** — temporary diagnostics: shows what the «Room tags» logic sees for the selected tag. Doesn't change the model.
- **Fragment room schedule** — for a cropped plan (see «Crop view») collects the rooms of the model and visible links inside the crop region and creates a «number — name — area — category» schedule table without filters. Table kind — in the settings: a manual schedule (a free table in the schedule header, no parameters in the model) or a key schedule (splits into parts on a sheet, but adds `LL_Экспликация_*` parameters to rooms). Title, column headers and widths, row height (by default form 2 of GOST 21.501: 15/80/20/10 mm, header 20 mm, row 8 mm), the room number/name/area (empty — built-in) and category parameters, sorting/grouping as in a Revit schedule («Sort by» and up to three «Then by»: parameter, ascending/descending, group header; the room number as the last key) — Shift+click.
- **Update room schedule** — rebuilds fragment room schedules from the current rooms: click — all in the project, Shift+click — only the chosen ones (selected, open, of the open plan or sheet, otherwise a pick from a list).
</details>

<details>
<summary><b>Schedules</b></summary>

- **Export to Excel** — exports the active schedule to .xlsx (no openpyxl/Excel). [Instructions →](docs/en/schedules-panel.md)
- **Import from Excel** — loads edits from .xlsx back into the model by the «Revit ID» column.
- **Split schedule** — splits a schedule on a sheet into segments of a given height.
- **Model → JSON** — exports a model snapshot (elements, parameters, levels, optionally circuits, coordinates, tags, rooms and spaces from links with outlines, a type catalog) to .json — for example to hand to Claude for analysis. Shift+click — what to export: scope, categories, parameters, etc. [Instructions →](docs/en/json-snapshot.md)
- **JSON → model** — loads edits from a snapshot back into the model: parameter values, moving/rotating elements and tags, creating new elements (the `"new"` section), with a «was → becomes» preview and conflicts marked.
</details>

<details>
<summary><b>Selection filter</b></summary>

- **Selection filter** — selects elements in the view, limited to the ticked categories; Shift+click — choose the categories. [Instructions →](docs/en/general-panels.md)
</details>

<details>
<summary><b>Music</b> — player control</summary>

- **Previous track**, **Play / pause**, **Next track** — Windows media keys for the active player.
- **Quieter**, **Louder** — a step of the Windows system volume.
</details>

<details>
<summary><b>Mail</b></summary>

- **Tasks from mail** — goes through the classic Outlook «Inbox» for N days with AI and saves a task list to Excel; mail is only read. AI of your choice: Claude or ChatGPT, through the app under your subscription (Claude Code / Codex CLI) or with an API key (Anthropic / OpenAI). Works without an open project. Shift+click — settings (how to connect the AI with links to instructions, model, period, subfolder, prompt, test mode). More and connection instructions — [docs/en/email-tasks.md](docs/en/email-tasks.md). For colleagues without Revit — the same function as a separate program `LowLifeMail.exe` (download from [Releases](https://github.com/avpersiyanov-afk/LowLife/releases)): [docs/en/email-tasks-app.md](docs/en/email-tasks-app.md).
</details>

<details>
<summary><b>Notes</b> — notes, questions and tasks on a project</summary>

- **Note** — quickly jot down a remark, question, task or reminder for the current project; the project code, view and selected elements are filled in from the model.
- **Summary** — all notes of the project: filters, «Done / In progress», answering a question, editing a note, going to the view/sheet and to the linked elements.
- **Setup** — connecting to the Google Sheet and choosing the «Project Information» parameters.

Notes are kept in **your team's** Google Sheet, which has to be created once: step-by-step instructions (the sheet, the [`Code.gs`](docs/notes/Code.gs) script, token, address) — [docs/en/notes-panel.md](docs/en/notes-panel.md).
</details>

Details on individual tools — in [docs/en/](docs/en/) (Russian originals in [docs/](docs/)) and in the `README.md` files inside `lib/` and `tests/`.

## Development

The shared library lives in `lib/` (the `lowlife` package) and gets onto pyRevit's `sys.path` automatically — see [lib/README.md](lib/README.md) for the module reference (in Russian). Button scripts (`script.py`) should stay thin orchestration over `lib/lowlife/`.

There is no build step, package manager or linter; changes are checked by loading the extension into Revit. Pure logic without the Revit API (graphs, addressing, loops, layouts) is covered by unit tests in [tests/](tests/) — run `python -m pytest tests -v` under Python 2.7 + `pytest<5`, details in [tests/README.md](tests/README.md). Detailed architecture notes and IronPython/Revit API pitfalls — in [CLAUDE.md](CLAUDE.md) (English and Russian).

A new button or panel needs an English caption next to the Russian one in its `bundle.yaml` (`title_en:`, and `tooltip_en:` if it has a tooltip) — `tests/test_i18n.py` checks it.

## License

[MIT](LICENSE) © 2026 Andrey Persiyanov. You may freely use, copy, modify and distribute it, including commercially, provided the copyright line and the license text are kept in copies. The extension is provided «as is», without any warranty: check the results (addresses, circuits, cable lengths, etc.) before issuing documentation.

## Logo

The mark is the «⅃Γ» monogram (a mirrored L from «Low» and an upside-down orange L from «Life»); the name is LowLife's own artwork with the same orange «Γ»; in the «About» window the name is set in a font. Files and the generator are in [`docs/brand/`](docs/brand/) (`python docs/brand/make_brand.py` rebuilds the logo PNG/SVG, the name image and the «About» button icon). All button icons share the palette, separately for Revit's light theme (`icon.png`: light background, black drawing) and dark theme (`icon.dark.png`: black background, white drawing), with an orange accent (`docs/brand/restyle_icons.py`).
