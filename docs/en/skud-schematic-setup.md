[Русский](../skud-schematic-setup.md) | **English**

# ACS riser diagram: what to prepare and how it works

This applies to the `SKUD.panel` buttons **Access point rooms** (`AssignSkudRooms`) and **Riser diagram** (`BuildSkudSchematic`). An overview of the panel is in `docs/en/skud-panel.md`, the function reference in `lib/README.md`.

---

## 1. The idea

`BuildSkudSchematic` used to lay out each device of a controller as a separate schematic family by category coordinates. Now:

- one controller can serve several **access points** (doors / turnstiles);
- a controller can physically stand far from its readers — on a riser diagram that doesn't matter, the diagram is topological;
- for each access point there is a **typical assembly** — a Revit **detail group** made beforehand (reader + lock + exit button + reed switch, etc. + a frame);
- the button compares the **make-up of the access point** with the make-up of each typical group, finds the matching one, places it on the drafting view, ungroups it and carries the addresses over to the schematic elements;
- the controller is a single schematic family (chosen in the category table, the «контроллер» row); it has no typical group; it is placed once per controller and connected with a line to each access point;
- the diagram state (what stands where, which schematic element corresponds to which device) is kept as JSON **in a service parameter of the drafting view** (like the CCTV/fire alarm layout), plus each schematic element carries its device's `UniqueId` in a parameter;
- **a re-run of the same button is an incremental sync:** unchanged access points are left alone (manual layout is kept), changed ones are redrawn, missing ones are deleted, new ones are added. There is no separate update button.

«Make-up» = a multiset of device **categories**. The category of a real device is determined by the **exact family type** (not by keywords) — the «category → real types» table is set in the settings.

---

## 2. What to prepare (once per project)

### 2.1. Shared parameters

All of them are project shared parameters, entered in the «ACS parameters» window and in the «Write room number» settings (Shift+click on that button). The real names are up to the project.

| Parameter | Where | Type | Req. | Why |
|---|---|---|---|---|
| «Device address» | device and controller instance | text | yes | filled in by the ACS pipeline; carried over to the diagram |
| «Device tag» | device instance | text | yes | written on the diagram = the address |
| «Access point number» | device instance | text/number | no | splits a controller's devices by access point; **empty → one access point** |
| the address parameter on the schematic family | Detail Component instance (schematic families) | text | yes | where the button writes the address/tag on the diagram |
| `device_uid_param_name` | Detail Component instance (schematic families) | text | yes | where the button writes the source device's `UniqueId` — the diagram↔model link for the incremental sync. The counterpart of CCTV's `device_uid_param_name` |
| the service manifest parameter | the **«Views»** category (`OST_Views`) | text | yes | where `BuildSkudSchematic` writes the JSON of the whole diagram (its state); don't touch by hand. The counterpart of CCTV's `layout_param_name` |
| room name (by mask, by default «Имя (Номер)») | device and controller instance | text | yes (for «Access point rooms») | the target parameter in the «Write room number» settings (`room_param_name`) |
| the room value mask | refers to Room parameters in the linked file | text | yes (for «Access point rooms») | the «Write room number» settings (`room_mask`), e.g. `Имя (Номер)` |

### 2.2. Diagram device categories

In «ACS parameters» → the **«Diagram device categories»** field (one per line). The `контроллер` (controller) line is required. An example:

```
контроллер
считыватель
замок
кнопка выхода
геркон
доводчик
ИБП
```

(controller, reader, lock, exit button, reed switch, door closer, UPS)

### 2.3. Category → real device types (the identity key)

In «ACS parameters», for each category → **«Real device types of this category (in the model)»** — a multi-select from the Revit categories `Security Devices` / `Electrical Equipment`.

It is by this table that the button understands that a given instance in the model is a «reader». If a type isn't ticked in any category, the device goes into «no category» and doesn't count in the signature (there will be a line about it in the report and in the diagnostics).

### 2.4. Category → schematic family

In «ACS parameters», for each category → **«Schematic family (to place)»** — a type from the `Detail Items` category.

It's needed for two things:
- **reading the make-up of typical groups** — the category of a schematic element inside a group is determined by its family type;
- **the fallback layout** (when there's no group for an access point).

> If the typical groups are already built from these same schematic families, it is enough to give the same type here as the one in the group.

### 2.5. Typical access point groups

The **controller** has no typical group — it is placed as a single schematic family from the category table (the «контроллер» row, item 2.4).

**Access point groups** (one for each typical make-up) are assembled by hand in Revit **on a drafting view**:
1. for each device of the access point, place the schematic family of the right category (the type must be set in item 2.4). For a two-way door — two «reader» families, and so on;
2. a frame/labels — optional (they don't affect matching);
3. **Create Group**;
4. leave an instance in the project (the make-up is read from the **first placed instance**; if there are no instances, the group is skipped with «couldn't read the group make-up» in the report).

Group names — anything meaningful (they go into the report and the manifest).

A minimal typical set:
- `СКУД_ТП_односторонняя` (one-way) — reader + lock + exit button + reed switch;
- `СКУД_ТП_двусторонняя` (two-way) — reader ×2 + lock + reed switch;
- and more as needed.

### 2.6. Choosing the groups in the settings

«ACS parameters» → the **«Typical access point groups»** section — a multi-select of all typical access point groups (the list shows only the project's detail groups).

### 2.7. Rooms

- Load the link(s) with placed Rooms;
- the «Write room number» settings (Shift+click) — fill in `room_param_name` and `room_mask` (e.g. `Имя (Номер)`).

### 2.8. The drafting view and service parameters

- In «ACS parameters» → `[Схема]` (diagram), fill in:
  - **«Riser diagram drafting view name»** (`schematic_view_name`, by default `Структурная схема СКУД`);
  - **«Service view parameter for the manifest»** (`layout_param_name`);
  - **«Service schematic family parameter for the source device's UniqueId»** (`device_uid_param_name`).
- Add two shared parameters, both **text**:
  - `layout_param_name` — bound to the **«Views»** category (the button writes the whole diagram state JSON into it);
  - `device_uid_param_name` — bound to the categories of the **schematic Detail families** (the button writes the source device's `UniqueId` into it — a re-run uses it to recognise «the same device»).
- There's no need to create the view itself — `BuildSkudSchematic` creates a Drafting View with this name on the first run and keeps syncing it after that. Several diagrams in parallel — different view names.

---

## 3. What to fill in while modelling

- **Device addresses** — as usual, with the ACS pipeline (`AssignCircuitsAndCables` / `CalcSkudLengths`).
- **«Access point number»** — only where **several** access points are connected to one controller: the devices of the first door get `1`, of the second `2`, and so on. Where there is one access point, it can be left empty.

---

## 4. Run order

1. The ACS pipeline up to and including device addresses.
2. **Access point rooms** (`AssignSkudRooms`).
3. **Riser diagram** (`BuildSkudSchematic`) — the view is created/found by name by itself; there's no need to pick a point.
4. After any changes in the model — **Riser diagram** again. It finds the changes itself: unchanged access points are left alone, changed ones are redrawn. There is no separate update button.

---

## 5. How each button works

### 5.1. Access point rooms (`AssignSkudRooms`)

1. Collects the ACS controllers and their devices (by circuits, like `AssignCircuitsAndCables`).
2. Splits each controller's devices by access point — by the «Access point number» value (empty → access point `1`).
3. For each device, looks for the room in the links (the same mechanics as «Write room number»: an exact hit in a Room, otherwise the nearest outline within the tolerance).
4. For each access point, takes the **most common non-empty** value and writes it to **all** devices of the access point. With equal frequencies — the first in order (devices are sorted by address → the result is stable).
5. The controller gets its room individually (no majority).
6. Report: how many access points were processed, how many have no room.

### 5.2. Riser diagram (`BuildSkudSchematic`) — incremental sync

One entry point: both the first build and the update are the same button.

1. Finds the drafting view `schematic_view_name` (or creates a new Drafting View) and reads the **state** from the view parameter `layout_param_name`.
2. Reads the signatures of the typical access point groups: from the first placed instance of each group → the categories of its schematic elements → a multiset `((category, count), …)`.
3. Builds the **desired state** from the model: controllers with an address → access points (by «Access point number») → devices (with `UniqueId`, address, category) → signature → the matched group.
4. Syncs with the saved state (the unit is an **access point**):
   - **controller**: if its schematic family is in place — left alone, only the address is updated; otherwise the controller family is placed again and gets the controller's `UniqueId`;
   - **the access point didn't change** (the same set of devices by `UniqueId` and the same matched group) → the geometry is left alone, only «Device address» / «Device tag» on the schematic elements are updated;
   - **the access point changed** (the set of devices or the group) → its schematic elements are deleted and drawn again: `PlaceGroup` offset down from the controller → ungroup → match schematic elements to devices by category (within a category — by address) → write each the device's `UniqueId`, address, tag;
   - **the access point disappeared** from the model → its elements are deleted;
   - **a new access point** → placed;
   - **the controller disappeared** → its schematic family and all access points are deleted.
5. **No match** (no group for the access point's make-up) → the fallback layout: schematic families by category in a column down from the access point (step — `schematic_layout_step_mm`) + a line in the report with the make-up and a request to build a group.
6. **Lines** controller → access point are re-created on every run; the anchor is the average position of the actual schematic elements (it follows manual moves).
7. The new state is written back to the view parameter. If the parameter doesn't resolve/is read-only — a warning in the output window.
8. Report: access points unchanged / redrawn / added / deleted; controllers added / deleted; unresolved references; no match.

**No groups remain on the diagram** — only details and lines.

### 5.3. Diagnostics (`InspectSchematicDevices`)

Pick a controller → the output window shows: all circuits, all elements, duplicates by `ElementId`, **the split by access point with each one's signature** and each device's category. From this you can see why an access point didn't match a group (for example, a device has no category assigned, or the make-up differs from all typical groups).

---

## 6. Limitations and notes

- **The manifest is kept in a drafting view parameter** and is tied to the `ElementId`s of a particular file. «Save as» to a new file — the manifest moves along with the view, but the devices' `ElementId`s change: run «Riser diagram» again (it redraws by the fresh ids).
- **Don't duplicate the riser diagram view** — the copy takes the same manifest, and two views would fight over one set of ids. For a second diagram, set a different view name in the settings.
- The `layout_param_name` parameter must be **writable on the view** (not locked by a view template, type «Text»). If writing fails — a line in the output window; the next run won't see the previous state and will build everything again.
- **Signatures must match exactly.** An extra door closer or a missing exit button → the access point goes to the fallback. This also helps catch model errors: the report names the actual make-up.
- **The manual layout** can and should be adjusted: a re-run doesn't move unchanged access points. But if you change an access point's make-up or the type of the matched group, that access point is redrawn from scratch at its calculated position (the others aren't touched).
- **A new access point** is placed at its calculated position (vertically under the controller, a step of 1/3 of the «step between controllers») — it may overlap a neighbouring one moved by hand; pull them apart by hand.
- If `device_uid_param_name` isn't filled in on the elements (the parameter wasn't added), some links are lost on a re-run and access points are redrawn whole more often. The parameter is required.
- **The fallback layout** places devices in a simple column (step — `schematic_layout_step_mm`) and only works if a «Schematic family» is filled in for the categories (item 2.4); for categories without a schematic family there will only be a line in the report for that access point. Per-category coordinates and the layout preview have been removed from the settings — the main path is through groups.
- Each typical group must have **at least one placed instance** — otherwise its make-up can't be read.
