[Русский](../json-snapshot.md) | **English**

# A model snapshot in JSON — «Model → JSON» / «JSON → model»

Two buttons on the `ToolsSchedules` («Schedules») panel, the `General` theme of the `_Themes.panel` switcher. The logic is in `lib/lowlife/json_snapshot.py`, the settings in `lib/lowlife/json_snapshot_settings.py`.

The idea: export the part of the model you need to JSON, hand the file over for analysis (for example to Claude — including a cloud session that has no access to Revit), get a corrected file back and load the edits back in. The model changes **only** through the load button — after a preview and in one transaction.

## Workflow

1. **Shift+click** on «Model → JSON» — set up what to export (see below). Without setup, all elements of the active view with all parameters are exported.
2. **Click** on «Model → JSON» → choose where to save the `.json`.
3. Give the file to Claude with a task, for example: «find fire automation devices without an address», «number the addresses by floor», «fill in the empty LOI parameters according to the brief». The format rules are written into the file itself (the `"readme"` field) — there's no need to explain them separately.
4. **Click** on «JSON → model» → pick the corrected file → in the «was → becomes» list keep ticked what should be written → «Write ticked». Everything is written in one transaction: Ctrl+Z undoes the whole load.

## Export settings (Shift+click)

| Setting | What it does |
|---|---|
| **Which elements** | The active view (plan/3D/schedule) · selected elements · the whole document |
| **Categories** | Category names, one per line, with a «Pick from the model…» button. Empty — all model categories (no annotations, grids, levels, views) |
| **Parameters** | Parameter names, one per line, with a «Pick from the model…» button (✎ — the parameter is writable). Empty — all instance parameters |
| Read-only parameters | Lengths, calculated values, references — into `"readonly"`, for analysis. On by default. |
| Type parameters | Into `"type_params"`, for analysis. Off by default. |
| Empty values | Export unfilled parameters too — turn on if empty parameters need to be **filled in** in the snapshot. Off by default. |
| Electrical circuits | Adds the circuits the exported elements belong to, with the panel and the circuit members. On by default. |
| Coordinates and rotation | Insertion point and rotation / start-end of a linear element, mm — **editable** (see «Moving»). Off by default. |
| Tags | Tags of the exported elements (in the active view or in all views) — the head position is **editable**. Off by default. |
| Rooms and spaces | A `"rooms"` section (the current model **and links**) and, on each element, the `"room"`/`"space"` it stands in. For analysis only. Off by default. |
| Type catalog | A `"catalog"` section: the loaded families/types of the chosen categories (or of the exported elements' categories) — pick from it what to create in `"new"`. Off by default. |
| **Room parameters** | Which room/space parameters to add to `"rooms"` («Pick from the model…» button). For an air balance — the spaces' flow rates |

The settings can be exported/imported as a file (the buttons at the bottom of the window), as with the other buttons.

## File format (version 1)

```json
{
  "format": "lowlife-snapshot",
  "version": 1,
  "readme": ["…rules…"],
  "document": {"title": "…", "path": "…"},
  "exported_at": "2026-09-29 12:00:00",
  "settings": {"scope": "view", "view": "…", "categories": [], "param_filter": null, "…": "…"},
  "elements": [
    {
      "id": 123456,
      "uid": "5a1c…-0001e240",
      "category": "Пожарная сигнализация",
      "family": "…",
      "type": "…",
      "level": "Этаж 01",
      "params":      {"Комментарии": "…"},
      "readonly":    {"…": "…"},
      "type_params": {"…": "…"},
      "circuit":     {"panel": "<uid>", "elements": ["<uid>", "…"]},
      "location":    {"point_mm": [1000.0, 2000.0, 0.0], "rotation_deg": 90.0},
      "room":        {"uid": "…", "number": "101", "name": "Офис", "source": "АР.rvt : 1 : …"},
      "space":       {"uid": "…", "number": "101", "name": "…", "source": "текущая модель"},
      "h": {"Комментарии": "3f2a9c01", "@location": "a41c07e2"}
    }
  ],
  "rooms": [
    {
      "uid": "…", "kind": "room", "source": "АР.rvt : 1 : …",
      "number": "101", "name": "Офис", "level": "Этаж 01", "level_elevation_mm": 0,
      "area_m2": 18.4, "volume_m3": 55.2, "height_mm": 3000,
      "boundary_mm": [[[0, 0], [4000, 0], [4000, 4600], [0, 4600]]],
      "params": {"Тип помещения": "Офисное"}
    }
  ],
  "catalog": [
    {"category": "Пожарная сигнализация", "family": "…", "type": "…",
     "placement": "OneLevelBased", "instances": 12, "example_uid": "…"}
  ],
  "new": []
}
```

Category, parameter and level names are the project's own (Russian in a Russian project), exactly as Revit shows them.

- **`"params"` and `"location"` are loaded back.** In `"params"` you can change values and add keys (names of existing instance parameters of that element). Removing a key changes nothing.
- Values are text as in Revit: numbers in project units, Yes/No — `"Да"`/`"Нет"` (`true`/`false` and `1`/`0` are understood too). An empty string clears a text parameter; a numeric one can't be cleared with an empty string.
- `"readonly"`, `"type_params"`, `"circuit"`, `"tag"`, `"level"`, `"room"`, `"space"`, the `"rooms"` section and the rest are for analysis only; edits to them are ignored. Type parameters are deliberately not loaded: a change would affect all instances of the type.
- `"uid"`/`"id"` — the link to the element (UniqueId first, Id as the fallback).
- `"h"` — fingerprints of the `"params"` values at export time, per parameter (the position under the `"@location"` key). The load uses them to tell apart:
  - the value wasn't edited in the file → it isn't written, even if it has changed in the model since (otherwise the load would roll back someone else's work);
  - edited in the file, unchanged in the model → an ordinary edit;
  - edited in the file **and** changed in the model after the export → a conflict: ⚠ in the list, **unticked** by default. A parameter added to `"params"` counts as originally empty — if it is already filled in in the model, that's a conflict too.
- New elements are created only from the `"new"` section (see below); entries added to `"elements"` are ignored. Nothing is deleted: an element from the file that isn't in the model goes into the report.

## Moving (`"location"`)

Coordinates are in mm, in the project coordinate system (Revit's internal origin), the same as at export.

| Key | For | What a change does |
|---|---|---|
| `point_mm` `[x, y, z]` | point elements (equipment, devices, rooms) | moves the element to this point |
| `rotation_deg` | point elements with a rotation | rotates around the vertical to this angle (an absolute value, degrees) |
| `start_mm`, `end_mm` | straight linear elements (trays, lines, pipes) | sets new ends; for arcs (`"shape": "arc"`) — read-only |
| `tag_head_mm` | tags | moves the tag head |

Pinned elements don't move — that goes into the report's errors. Revit rebuilds connected fittings/neighbouring segments itself, as with a manual move; if it can't, there's an error in the report.

## Rooms and spaces (`"rooms"`)

Placed rooms (Rooms) and spaces (MEP Spaces) are taken from the current model and from all loaded links — architectural rooms usually live in the architectural link. Link coordinates are converted to the project coordinate system, so room outlines and the elements' `"location"` can be compared directly.

- **Which rooms get in:** all rooms that contain at least one exported element, plus all rooms on the same levels (compared by elevation, not by level name — the names may differ between the architectural model and yours), so empty rooms are visible too. When exporting the whole document — all of them.
- **What's in an entry:** number, name, level and its elevation, area (m²), volume (m³, if Revit calculates it), height, outlines `"boundary_mm"` (the first is the outer one, the rest are cut-outs around columns/shafts; arcs are split into segments) and the parameters from the «Room parameters» list.
- **Element assignment:** the element's point inside the room (with a probe 300 mm higher — for devices sitting exactly at floor level), otherwise the nearest room no farther than 90 mm from its outline (equipment recessed into a wall) — the same logic as the «Write room number» button.
- The section is for analysis only. The current model's spaces can also be exported as ordinary elements (the «Spaces» category) — then their writable parameters (for example calculated flow rates) are edited through `"params"`.

Example tasks: areas and device counts per room, rooms without detectors/outlets, an air balance by space (the sum of the flows of air terminals with the same `"space"` against the space's flow).

## Creating elements (`"new"`)

The export always has an empty `"new"` section. Every entry added there becomes a «＋ create …» row in the preview list on loading (ticked by default).

```json
"new": [
  {"family": "Извещатель", "type": "ИП212-64", "point_mm": [12000, 4500, 2700],
   "level": "Этаж 01", "rotation_deg": 0, "params": {"Адрес": "2.14"}},
  {"copy_of": "<uid of an existing instance>", "point_mm": [15000, 4500, 2700]}
]
```

| Field | Required | What it is |
|---|---|---|
| `family` + `type` | yes (or `copy_of`) | A loaded type — names as in `"catalog"` |
| `copy_of` | instead of family/type | Copy an existing instance to a new point. Needed for face/work-plane-based families that can't be placed by a point: the copy keeps its host. Together with `type` — a copy with the type swapped within the same family. The catalog has `"example_uid"` for this |
| `host` | no | The uid of a wall/ceiling of the current model — for wall-based families |
| `point_mm` | yes | The insertion point, mm, in the same coordinates as `"location"` |
| `level` | no | A level name of the current model; without it — the nearest level below |
| `rotation_deg` | no | Rotation around the vertical, degrees |
| `params` | no | Instance parameter values, as in `"params"` |

- Placement works as in the «Place relay, control modules» button (fire automation): the first option Revit accepts (with host and level → with host → by level → unattached; without a level, the level is assigned right away as a parameter if Revit allows it), then the element is moved exactly to `point_mm` and rotated — the height doesn't depend on how the family treats the Z of its insertion point.
- **No duplicates are created:** if there's already an instance of the same type within 10 mm of the point (in the model or earlier in the same `"new"`), the entry is skipped — loading the same file again doesn't double anything.
- Errors in an entry (no such type/level, not three numbers in the point) go into the report; the other entries are created. If an element was created but some of its parameters weren't written, it counts as created, with a note in the report.

A typical placement scenario: export with rooms and the catalog → ask Claude to place equipment by rules (spacing, offsets from walls, «in every room …») along the `"boundary_mm"` outlines → load. Claude doesn't see walls, doors and obstacles (they aren't in the file) — check the result on the plan; Ctrl+Z undoes it all.

## Report after loading

How much was written/created, how much wasn't ticked, how much matched the model, how much wasn't edited in the file but changed in the model (left as in the model); separately — elements not found in the model; parameters the element doesn't have; read-only parameters; values that can't be written (empty for a numeric one, a nested object instead of text, errors in `"new"` entries), `"new"` entries skipped as duplicates, and Revit errors/warnings when writing.

## Limitations

- Elements are exported and edited only in the current document; from links only rooms and spaces are taken (for analysis).
- Element reference parameters (`ElementId`, for example the circuit «Wire») are exported read-only — they can't be written unambiguously by name.
