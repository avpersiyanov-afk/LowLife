[Русский](../schematics.md) | **English**

# CCTV and fire alarm riser diagrams

The «Riser diagram» buttons on the **CCTV** (SOT) and **Fire alarm** (SPS) panels build a riser diagram on a drafting view from the model's devices and update it on re-runs. Both work the same way; the fire alarm one additionally draws loops and isolator branches. The SCS and ACS riser diagrams are described separately — [scs-panel.md](scs-panel.md#4-riser-diagram-buildscsschematic) and [skud-schematic-setup.md](skud-schematic-setup.md).

> [!WARNING]
> The riser diagram buttons have had little testing. All changes are undone with **Ctrl+Z**.

## What to prepare

1. **Schematic families** — a symbol for each diagram category («Camera», «Cabinet», «Detector», «Isolator», «Panel»…), category «Detail Items».
2. **A node tag** — an annotation type (usually «Designation, Address») placed above every symbol.
3. **Parameters** (easiest to create with the «Shared parameters» button, see [parameters.md](parameters.md)):
   - «Room» — on devices and on schematic families;
   - «Device address» — on devices (for CCTV — also on schematic families);
   - the service «Diagram layout» — text, category «Views»;
   - the service «Device UID» — text, on schematic families;
   - optional: «Level», «Building» (and for CCTV «Section») on devices.
4. **Levels** with names of the form «Этаж N» (Floor N) and an elevation «X,YYY» (negative for underground floors): the floor labels and their order are built from them. If the levels in your project are named differently, add a «Level» parameter on the devices with such text.

## Settings (Shift+click)

| Field | What to enter |
|---|---|
| Diagram device categories | Logical categories, one per line («Камера», «Шкаф»…). For each, the schematic family and the real model device types belonging to it are chosen below — only they get onto the diagram. |
| «Cabinet» category (fire alarm — «Cabinet»/«Panel») | One name from the list above. Lines from the other nodes are drawn to the device of this category. Empty — no lines. |
| «Room» parameter and room mask | If the parameter on the device is empty, the text is assembled from the linked model's room by the mask: «Имя (Номер)» → «Офис (212)». Nodes are grouped into frames by room. |
| «Device address» parameter | A ready address from the device, copied onto the symbol; also used for sorting within a room. |
| «Level» parameter | Optional; empty — the element's level in Revit. |
| Building parameter (CCTV — also section) | Optional: the diagram is split into blocks by building (and by section for CCTV) — each with its own header, floors, riser and cabinet. |
| Building value to filter by | Optional: only this building. «Pick from the model…» fills in existing values. To keep a separate diagram per building, give each its own view name. |
| Riser diagram view name | The drafting view is created on the first run and updated on re-runs. |
| Node tag offset, mm | How far the tag is raised above the symbol. |
| Maximum width of a row of rooms, mm | Rooms that don't fit in a floor's row wrap to a new row below. Empty or 0 — one row per floor. |
| Node tag, view template | The tag type and (optionally) the drafting view template — applied on every run. |
| Service layout and UID parameters | The parameter names from item 3 above. Not filled in by hand. |

Fire alarm only:

| Field | What it does |
|---|---|
| Isolator branch offset in the same room, mm | If all devices of an isolator branch are in its own room, the branch is drawn under it inside the same frame. Empty — 40 mm. |
| «Lot name» parameter on the linked room, «Lot name» filter | For devices on isolator branches: if the linked room's «Lot name» is filled in (and contains the filter word), it is written to «Room» instead of the name by mask — different rooms of one lot read as one frame on the diagram. |
| Draw loop and branch lines | «нет» (no) — only the node layout, no lines (noticeably faster on large models). Put back «да» (yes) once the layout suits you. |
| Place node tags | «нет» (no) — no tags (placing tags in Revit can be very slow). Tags can be added in the next run. |

## How the diagram is built

- The button finds the devices of the chosen types in the model itself and lays them out by floor (higher elevations at the top, underground at the bottom) and within a floor by room (a frame with the room label).
- **A re-run** doesn't re-create the diagram: the previous run's layout is kept in a service parameter of the view, and only the floors, rooms and devices where something changed (added, removed, moved) are updated. Neighbours shift to close or free up space. The symbols stay the same elements.
- **Lines to the cabinet** — a bus topology: a shared horizontal collector under the nodes on each floor, short drops from the nodes, and the collectors run to a shared riser to the left of the frames. The lines are redrawn on every run — there's no point editing them by hand.

### Fire alarm only: loops and isolators

- Devices connected to an isolator (by the actual «isolator → devices» circuit built by the [«Fire alarm isolator–device circuits»](fire-alarm-panels.md#3-isolatordevice-circuits-buildisolatorcircuitssps-fire-alarm-only) button) are drawn as a separate branch row under the isolator rather than in their own rooms.
- Each loop (address «panel.loop.number») is drawn as a ring: inside a room — a segment through the nodes; moving to another room — only through the shared riser on the left. The ring goes «there» and «back» in two passes 3 mm apart. A loop whose panel didn't get onto the diagram is drawn without closing on it.

## Workflow

1. Fill in the device addresses (for fire alarm — with the loop circuit and length buttons, see [fire-alarm-panels.md](fire-alarm-panels.md)).
2. Shift+click — diagram categories, families, device types, parameters.
3. Run the button. For large fire alarm systems — first without lines and tags, then turn them on and run again.
