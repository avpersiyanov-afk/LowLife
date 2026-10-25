[Русский](../tools-panel.md) | **English**

# The Tools panel — general tools

Buttons not tied to a discipline. This page describes the ones without their own guide; «Views by level», «Equipment tags», «Spell check» and «Shared parameters» have separate pages (links in the [README](../../README.en.md#panels-and-buttons)).

All model changes the buttons make are undone with **Ctrl+Z**.

## Element ID

Shows the ID of the selected element and copies it to the clipboard right away.

1. Select an element (you can select an element inside a linked model — Tab to the link element you need).
2. Press the button.

For a link element, its ID **in the linked file** is shown, not the ID of the link instance. If several elements are selected, a comma-separated list of IDs goes to the clipboard — it can be pasted into Revit's own «Select Elements by ID» dialog.

## Dimension grids

Dimensions the selected grids with one chain and an overall dimension.

1. Select at least two grids (of the same direction) in the view.
2. Press the button and pick a dimension type from the list.

The button builds a dimension chain between neighbouring grids at an offset of 1400 mm from the grid ends and, if there are three or more grids, an overall dimension from the first grid to the last — another 700 mm farther out.

## Line length

Sums the lengths of the selected generic models by type — for example, to quickly count the length of routes drawn with line-based families.

1. Select the elements (extra categories don't need to be removed — only generic models are counted).
2. Press the button.

The output window shows the length per type in metres and the total length. The length is taken along the element's line, or if it has none — from the «Длина»/«Length»/«L» parameter of the instance or type.

## Section by family

Builds a section through the selected element, already cropped, with a view template, a section type and a name by mask.

1. Select one or several elements (or press the button without a selection — it asks you to pick them in the model). Families and linear elements will do: cable trays, conduits, pipes, ducts, walls.
2. If there are several elements, choose: one shared section (bounds by the outermost elements) or a section per element.
3. Enter how far to lower the section bottom below the base level (mm). The answers are remembered until next time.

How the section is built:

- **in height** — from the element's base level to the next floor of the same building (the next floor is found by level name and the pattern from the settings; levels of other buildings are hidden in the section);
- **in width** — 2000 mm to the left and right of the element;
- **in depth** — the cut plane 100 mm in front of the element, the far clip 1000 mm behind it;
- **direction** — towards the family's front side; for a wall device — from the room side; for linear elements — along the axis, viewed from the south (for north–south axes — from the west).

**Shift+click** — settings: view template, section type, name mask, crop offsets, level name pattern (by default `{Дисциплина}_{Корпус}_{Отметка}_{Этаж}_{Комментарий}` — {Discipline}_{Building}_{Elevation}_{Floor}_{Comment}), «look from the back».

## View range

Aligns the view range of plans by one rule:

| Boundary | Value |
|---|---|
| Bottom and depth | the plan's level |
| Cut plane | the plan's level +1200 mm (+900 mm if the next floor is less than 1400 mm away) |
| Top | the next floor's level −200 mm («Unlimited» if there are no levels above) |

1. Select plans in the Project Browser — or just open the plan you need.
2. Press the button.

The next floor is found by level name: the same building, another floor. The level name pattern is set in the settings (**Shift+click**), for example `{Дисциплина}_{Корпус}_{Отметка}_{Этаж}_{Комментарий}` or `Этаж {Этаж}`. Ceiling plans and plans whose view range is controlled by a view template are skipped — the button says why.

## Line bypass

Draws an arc «hop» of one detail line over another where they cross (like the bypasses on schematics).

1. Press the button and enter the arc diameter.
2. Choose a mode:
   - **Single** — its own arc of exactly the given diameter at each crossing;
   - **Multiple** — one big arc over the whole bundle if the line crosses several base lines at once.
3. Pick the base lines — with a window and/or clicks, confirm with Enter or «Finish». The base lines stay whole.
4. Then round and round: click the line that should go around the base lines, then the bypass side. The arc is built right away.

**Esc** when picking a line — finish; **Esc** when picking a side — skip only that line.

## Link trays to Excel

Exports to .xlsx a list of the cable trays from a linked model that are visible in the active view. No Excel is needed for this.

1. Open a view where the link with the trays is visible.
2. Press the button. If there are several links in the view, tick which ones to collect from.
3. Choose where to save the file.

Columns: the tray ID in the linked file, type name, model, middle elevation (mm), reference level, link name. In Revit 2024 and newer, visibility is determined exactly by the view; in older versions — by the crop and view range.

## Grids and levels vs coordination

Compares the model's levels and grids with those of the linked coordination file (КФП) and shows a list in the pyRevit window. Doesn't change the model.

1. Load the coordination link.
2. Press the button. A link with «КФП» in its name is taken right away; if there isn't one or there are several — pick the link from a list.

«Model ↔ link» pairs are matched by name; if a name differs only by case or spaces, that's a pair too. The remaining levels and grids are matched by position (within the tolerance) — that's «Different name». The rest is «Not in the model» / «Not in the link».

- **Levels** are compared by elevation (from the model's project base point, mm): the table shows the elevations in the model and in the link and the difference.
- **Grids** — by the line itself in plan: the grid length and bubble positions don't matter. For straight ones — the largest deviation between the lines (mm) and the rotation angle; for arcs — the centre offset plus the radius difference. An arc grid against a straight grid with the same name — «Differs» with an explanation.

Link coordinates take its placement in the model into account: if the link is placed with an offset, all grids and levels will differ — check the link placement first.

The report shows the differences first (a table), and the list of matches below. A link on a model element selects it; a link element has its ID in the linked file.

**Shift+click** — settings: a word in the link name («КФП» by default; empty — always ask) and the tolerance, mm (1 by default).

## DWG → drafting

Traces a DWG underlay with Revit annotations: lines, arcs and polylines become detail lines, text becomes text notes at the same point, with the same rotation, alignment and height on paper.

1. Select the DWG in the view (or don't — the one visible in the view is taken; if there are several, pick from a list).
2. Choose where to put it: into a **new drafting view** (it opens) or **onto this same view** over the underlay.

Layers hidden in the view aren't carried over.

Revit can't see DWG text, so the button reads it from a DXF of the same drawing:

1. a DXF with the same name next to the DWG;
2. otherwise it converts the DWG with the free [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter), if installed;
3. otherwise it offers to pick a DXF by hand or carry over only the lines.

**Shift+click** — settings: one line style for everything or styles per DWG layer (with the layer colour), the source text type, the path to ODA File Converter.

## Greeting

A window with a greeting in big letters: «Good morning / afternoon / evening» by the time of day and the Revit user name. Sometimes a joke: at night (23:00–5:00) and at weekends — that you shouldn't work like that, in the daytime on weekdays (12:00–17:00) — about being late, on weekday evenings (17:00–23:00) — that it's time to go home, on weekday mornings — a wish for the day.

Close — click the window, Enter or Esc. Whether to show the greeting every time Revit starts is chosen with a checkbox in the «About» window (off by default); this button shows it at any moment.

## Zoom to element

Zooms the view to an element.

- If elements are selected — zooms to them (to several — to their combined extent).
- If nothing is selected — asks for an element ID.

If the element isn't visible in the active view, the button tells you which view (plan, section, 3D) to switch to.

## Crop view

Crops the view and annotations to a rectangle picked with the mouse.

1. Open a plan, section, elevation or detail.
2. Click two opposite corners of the frame.
3. Choose what to crop: **this view** or a **copy** of it — plain, with detailing or dependent. For a copy, enter the text to add to the end of its name.

View cropping and annotation cropping are turned on (with the minimum offset from the frame); the copy opens right away. **Esc** — cancel.

A plan cropped this way can be used with the [«Fragment room schedule»](rooms-panel.md#fragment-room-schedule) button.

## Rotate 3D view

Turns the open 3D view to look along or across the chosen axis.

1. Open a 3D view (unlock a locked view first).
2. Point out the axis in one of these ways:
   - pick a grid from the list — it has the grids of the model and of loaded links (Revit doesn't show them in 3D);
   - click a straight line, wall or tray in the view — in the model or in a link.

The view turns around the vertical to the nearest of the four «along/across» angles; the camera tilt doesn't change. If the 3D view's section box is on, it turns the same way — its sides become parallel to the axis. **Esc** — cancel.

## Parking elevations

Labels on the plan the elevations of «Parking» category elements from links (usually architectural) — **relative to the plan's level** (floor = ±0.000).

1. Open a plan (if what's open isn't a plan, the button offers a list of plans to choose from).
2. Press the button.

Elements are split into groups by words in «Comments», the workset name and the family/type name. The groups are checked in order; an element goes to the first one that fits:

| Group | Default words | Default label | Hatching |
|---|---|---|---|
| Luminaire zone | светильн | `Светильники: низ +2,800, верх +3,200` | yes |
| Driveway | проезд | `Проезд: верх +2,450` | yes |
| Parking space | машиномест, машино-мест | `М/м: верх +2,100` | yes |
| Others | — | `Верх +…` | no |

An element made of several separate bodies (for example an in-place model with several luminaire zones) is split into zones: bodies that overlap in plan are one zone (a car inside a parking space), separate ones are different zones, each with its own label and hatching. The luminaire zone comes first because its «Comments» sometimes say «…в зоне проезда» (in the driveway zone). Top and bottom are taken from the horizontal faces of the element's geometry, for elements without faces — from the extent. Labels that land in the same spot on the plan (for example a luminaire zone over a driveway) are merged into one note. The hatching is a filled region along the element outline; the type «LowLife — <group>» is created on the first run (a diagonal hatch of its own colour for each group; it can be changed in Revit later).

Elements of all loaded links are taken — including links hidden on the plan (luminaire zones are sometimes in a model not shown on the plan) — that reach above the plan's level and below the next floor, within the view crop. The next floor is the nearest level of the main model at least 2.5 m above the plan (closer levels are parts of the same floor at other elevations), but the top is taken no lower than the top of the view range. Skipped zones are listed in the output window with their bottom/top elevations relative to the level and the reason.

A re-run replaces the previous run's labels and hatching on this plan. The output window shows how many elements of each group were found and what was skipped (unloaded links, another floor, outside the crop).

**Shift+click** — settings: for each group, the words, the label text (`{top}` — the top elevation, `{bottom}` — the bottom; empty text — no label) and the hatching.
