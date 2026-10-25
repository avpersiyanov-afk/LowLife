[Русский](../rooms-panel.md) | **English**

# «Rooms» panel (ToolsRooms)

Buttons for working with rooms — your own and from the linked architectural model. Two buttons are described separately: [«Write room number»](room-info.md) and [«Room tags»](room-tags.md).

## Find room

A list of the active view's rooms — from the current model and all loaded links (by the view's level and bounds), sorted by number and grouped by a parameter from the settings.

- Start typing a number or name — the list filters.
- The item at the top switches to **all rooms of the project** if the one you need isn't in this view.
- Pick a room and press **«Highlight»** — the active view zooms to it. If the room is on another level, the button tells you which plan to switch to.
- After highlighting, the list opens again — you can look for the next one right away.
- The list is collected once per Revit session; if the rooms in a link changed — the **«Refresh list»** item at the top.

Settings (Shift+click):

| Field | What to enter |
|---|---|
| Room number | The room parameter the list is built, sorted and searched by. Empty — the built-in «Number». |
| List grouping | The parameter the list is grouped by («Room type», «Occupancy», «Department»). Empty — no grouping. |

## Two-level lots

Finds **two-level lots** in the linked architectural model — lots whose rooms with the same lot name are on two or more levels. Shows the lot name, section and levels in the pyRevit window (sorted by lot name and section number), optionally exported to Excel. Doesn't change the model.

Only link rooms are taken (not the model's own); several instances of one link count once.

Settings (Shift+click): the room parameter **«Lot name»** (required) and **«Section number»** (optional — the second sort key and a report column).

## Tag diagnostics

Temporary diagnostics for the [«Room tags»](room-tags.md) button: select one room tag and press — the button shows what the «Room tags» logic sees for it (the tag's room, its area and point, the tag's position relative to the room boundaries). Needed to work out why a particular tag stays «?». Doesn't change the model.

## Fragment room schedule

A room schedule for a **cropped plan** (a fragment; the «Crop view» button on the Tools panel is handy for cropping). The button takes rooms of the model and visible links whose location point falls inside the active plan's crop region and which Revit shows on this plan, and creates a table: number, name, area, category. Rooms with zero area are skipped. If the plan already has a room schedule, it is updated.

You need a plan with cropping on. If no rooms are found, the button shows for each source: how many in total, how many inside the frame, how many on the floor.

Table kind (a setting):

- **Manual schedule** (the default) — a free table in the schedule header: no parameters appear in the model, the row height is set exactly; it can't be split into parts on a sheet.
- **Key schedule** — can be split into parts on a sheet, but columns in Revit are always parameters: the button adds text parameters `LL_Экспликация_*` to rooms, and Revit adds a key parameter to rooms for each schedule. Revit may not accept the row height.

The kind applies to new schedules; to change it for an existing one, delete it and create it again.

Settings (Shift+click):

| Section | What is set |
|---|---|
| ①–④ Columns | The header and width of each column. By default — form 2 of GOST 21.501: 15 / 80 / 20 / 10 mm. |
| ⑤ Room parameters | Number, name, area — empty: built-in. Category (by explosion and fire hazard) — empty: the column stays empty. An «Area»-type area parameter is converted to m². |
| ⑥ Sorting/grouping | Up to 4 levels of «Sort by» / «Then by»: a room parameter, the order and optionally a **group header** — a full-width row before rooms with a new value. The number in ascending order always comes as the last key. |
| ⑦ Area | Decimal places (2 by default). |
| ⑧ Row height | Header 20 mm, row 8 mm (form 2 of GOST 21.501). |
| Table | The table kind and the title above it. |

## Update room schedule

Rebuilds fragment room schedules (made by «Fragment room schedule») from the current rooms and settings.

- **Click** — all fragment room schedules in the project.
- **Shift+click** — only the chosen ones: selected schedules (on a sheet or in the Project Browser), the open schedule, schedules of the open plan or sheet; if nothing is selected — a list to choose from.
