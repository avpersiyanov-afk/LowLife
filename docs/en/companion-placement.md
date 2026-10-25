[Русский](../companion-placement.md) | **English**

# «Place relay, control modules» (SPA.panel/PlaceCompanionDevices)

It lives on `SPA.panel` (fire automation), not on `SPS.panel` (fire alarm) — this button's typical companions, remote control modules (МДУ), belong to fire automation even if the base object (for example a smoke control damper) belongs to another discipline.

It places a companion next to an object that is already there: for example a manual call point (РМ) at every emergency exit door, or a remote control module (МДУ) at every smoke control damper. The companion is placed at a fixed offset, and the values of chosen parameters of the base object (address, designation, etc.) are copied onto it.

The logic is in `lib/lowlife/companion_placement.py`; the settings and window are in `lib/lowlife/companion_placement_settings.py`, stored in `%APPDATA%\pyRevit\LowLifeCompanionPlacement_settings.json`.

## Setup (Shift+click)

One text list of arbitrary pair names («РМ у дверей, МДУ у клапанов» — call points at doors, modules at dampers), on the model of the ACS riser diagram categories (`skud_settings.py`): type the names, press «Refresh list» — a section for each name appears under the field. A section doesn't disappear or lose its settings when a name is temporarily removed from the list — only the names listed in the field at the moment of the run are used.

For each pair:

- **Place next to what** — one or several family types of any category (doors, equipment, generic models...) — these are the «base objects».
- **What to place** — one companion family type.
- **Offset** — forward/sideways/up, in mm, in the base object's LOCAL coordinates (in the direction of its rotation in plan) — so the same «forward» offset stays forward however the object is rotated.
- **Parameters to copy** — `Source=Target, Source2=Target2` (without `=` — the parameter name is the same on both sides). At least one is required — without it there's nothing to protect against placing twice (see below), and a re-run would create duplicates.
- **Group by 2-4** (optional, a checkbox) — see the section below.
- **A circuit between the companion and the base object** (optional, a checkbox) — see the section below.

## Grouping by 2-4 (a companion for several inputs)

Sometimes several base objects stand close together, and the companion serves not one input but several at once (for example a 4-input module). The «Group by 2-4...» checkbox in a pair's settings turns this on for it:

- **Group companion** — a separate family type (with several inputs), placed ONCE per group — not to be confused with the ordinary «What to place» (the one-per-object companion), which is used for everything that didn't get into a group.
- **Grouping radius, mm** — base objects are combined into groups of 2-4 if they are in the same room (a `Room` of the CURRENT document at the object's point, `Document.GetRoomAtPoint`) AND within this radius of each other. 2000 mm by default.
- An object without a detectable room (common for doors — the insertion point lies in the wall opening rather than inside the room outline) doesn't get into a group — it goes the ordinary one-by-one way with its own companion.
- If there are more than 4 candidates in one room, the 4 closest to each other are taken, and further groups of 2-4 are collected from the rest (rather than one overfull group).
- The group companion's point is the group centre (the average of its objects' points) plus the same offset from the pair's settings, but applied along the WORLD X/Y axes (not in one object's local coordinates — the group has no common rotation).
- Parameter values: each source from the «Parameters to copy» list is taken from ALL objects of the group, sorted and joined with `", "` into the same target of the group companion (so one target parameter gets all the addresses/designations of the group as one string, rather than a separate target per input).
- Protection against placing twice works the same way as for ordinary companions (see below), but by the group companion's own instances and by these joined values.

## Circuit(s) between the companion and the base object

The same logic as «Isolator–device circuits» (`lib/lowlife/fire_alarm_isolator_circuits.py`, `lib/lowlife/electrical_circuits.py`): the companion plays the isolator's role — the source/panel of the circuit (assigned through `ElectricalSystem.SelectPanel`, with the same protective manoeuvre against the Revit error «Not allow circular connection...» when the panel had to get into the circuit's element list temporarily), and the base object(s) it serves — one for one-by-one placement, all objects of the group for group placement — become the load (`lowlife.companion_placement.build_companion_circuits`).

Turned on with the «Build an electrical circuit...» checkbox in a pair's settings. Some companions need TWO circuits of different kinds to the same base object AT ONCE (for example power + signal), so the circuit is set not as one type but as two slots:

- **Circuit 1** — required if the checkbox is on: a Revit electrical circuit type (`ElectricalSystemType`: `Controls`, `FireAlarm`, `Data`..., chosen with a picker, as in «Circuit (general)») + optionally a cable from the catalog.
- **Circuit 2** — optional; if its type isn't chosen, only «Circuit 1» is built. If it is, a SECOND, independent circuit of another kind with its own cable is built between the companion and the same base object (or the group's objects).
- **Cable** — chosen from the document's cable catalog, the same way as in «Circuit (general)»/SCS: first, at the top of the window (shared by all pairs), fill in the «Cable catalog row marker parameter» — an arbitrary parameter only the document's elements acting as catalog rows have (for example «Марка»), then for each circuit slot the «Choose...» button opens the list of rows found. Optional — if none is chosen, the cable just isn't set.
- The circuit «Panel» and «Wire» are Revit's built-in parameters and aren't in the settings: the companion itself becomes the circuit's panel (by connection), and «Wire» gets the catalog row chosen for the slot.
- Right after each circuit is created, it gets Revit's «All Devices» path mode (`CircuitPathMode.AllDevices`), so that Revit calculates `Length` from the actual element positions itself.
- Circuits are built only for companions placed IN THIS run of the button (not for existing ones) — an existing companion is detected by the protection against placing twice and skipped, so the circuit-building code just isn't called for it. If a companion was placed BEFORE this checkbox was turned on for its pair (or «Circuit 2» was added), its circuit(s) will never appear — only for new ones.
- If creating one of the circuits fails (for example, the companion's category doesn't fit as a circuit source), it goes into the «couldn't build» counter; the other circuits and the companion itself aren't affected.

### Labelling wiring lines (as for fire alarm)

The same way as «Isolator–device circuits» (see [fire-alarm-panels.md](fire-alarm-panels.md), the section on labelling wiring lines with the circuit number): if both fields at the top of the settings window are filled in — «Keyword in the wire line family name» and «Line parameter for the label» (shared by all pairs, not per pair) — after each successfully built circuit the button finds, in the active view, wiring lines already drawn by hand (line-based Generic Models) near the points of the base object/companion and writes the circuit's own Revit name (`circuit.Name`, for example «Цепь 1») to that parameter — this button's circuits have no «Circuit Number» of their own, so the label is the same as for «Isolator–device circuits» rather than a number as for main loops. «Near» means the line end is within ~300 mm of the point of the base object/companion/any other object of the group. The button doesn't draw lines itself — it only labels what's already drawn; if either of the two fields is empty, it does nothing (the button is fully functional without it — this is an optional add-on).

**The wire is usually drawn by hand AFTER the circuit is already built** — at the first run of the button it's most often not there yet, and there's nothing to label (that's expected, not a bug). So labelling is attempted not only right after the companion is created but also on every SUBSEQUENT run — including for existing companions the protection recognised as duplicates: the button finds their existing circuit(s) (by the companion's `Connector.MEPSystem` — the same sign as `detect_electrical_system_type` in `electrical_circuits.py`) and tries to label the wire with its name (`lowlife.companion_placement._mark_wires_for_existing_companion`). Without this repeated step the label would never appear on a wire drawn after the first run: on every re-run the companion would be recognised as a duplicate before the code got to the circuit/label.

## How the companion is placed

- The point — the base object's point (`LocationPoint`, otherwise the bounding box centre) plus the offset rotated by the base object's rotation angle.
- The host — if the base object has a `Host` (for example a wall), the companion tries to stand on the same host; otherwise — by the base object's level (or the nearest one below if the object has no level; a work-plane-based family is placed on that level's plane); as a last resort — with no attachment at all. Whatever Revit accepts first for the companion family. An instance inserted without a level gets the level assigned right away through the «Level» parameter if Revit allows it; otherwise it can be assigned later with the LOI button «Update level name».
- Families that require placement on a particular face (face-based without a host element) aren't supported yet — such companions go into the «couldn't create» counter.

## Protection against placing twice

Before creating a companion, the button looks among existing companion instances (of the same type) for those within a reasonable radius of the placement point and compares their target parameters with what is about to be copied from the base object. If a companion with matching values is found, the base object counts as already processed and is skipped («already there» in the report). So the list of parameters to copy isn't only a convenience — it's also the working duplicate protection.

## What one run processes

All base objects of the configured types in the active view (not only selected ones) — for each configured pair separately.

## Report

For each pair: how many base objects were found in the view, how many companions were placed one by one, how many were already there (skipped), how many had no location point and how many couldn't be created — and, if grouping is on for the pair: how many groups were found and how many group companions were placed/were already there/couldn't be created; and, if circuit building is on: how many circuits were built, how many failed and (if the line label fields are filled in) how many wiring lines were labelled.
