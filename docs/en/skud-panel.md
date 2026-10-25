[Русский](../skud-panel.md) | **English**

# SKUD.panel — requirements for families and parameters

The buttons on the `SKUD` panel automate an ACS (access control) project: from the equipment placed on the plan and the circuits set up — to finished cable logs, the cable schedule and the riser diagram. The settings are separate from `SCS.panel` (their own JSON file `%APPDATA%\pyRevit\LowLifeSKUD_settings.json`). No parameter/family names are stored in the repository — as in `SCS.panel`, every working button takes the values it needs through its own Shift+click (there's no shared form for the whole panel).

The natural run order — in this order (each next button uses the previous one's result), as in `SCS.panel`:

0. **Bind parameters** (`SetupParameters`) — only checking/binding parameters from the shared parameters file; setting values are no longer edited here (see the Shift+click of the buttons below). Run it first, once the needed fields are filled in.
1. **ACS route nodes** (`PlaceSkudRouteNodes`) — places ACS panels/route nodes/risers along the route lines. Only needed if there are distant devices (see below); if all devices stand right next to their controllers, there's no need to draw a route and this step is skipped.
2. **ACS node addresses** (`RenumberSkudAddresses`) — numbers these nodes and writes the nearest route node to controllers/devices.
3. **Circuits and cables** (`AssignCircuitsAndCables`) — finds the controllers and their circuits, gives the connected devices addresses, picks the cable type from a dictionary, writes the load name, tags the controllers.
4. **Lengths and tags** (`CalcSkudLengths`) — calculates the wire length (along orthogonal legs near the controller, otherwise along the route graph), writes the length in conduit/tray separately, the installation method, device tags and the list of circuits on route nodes.
5. **Access point rooms** (`AssignSkudRooms`) — writes the room name from the link to all ACS devices; for each access point one (the most common) value is taken and assigned to all its devices.
6. **Riser diagram** (`BuildSkudSchematic`) — by the make-up of each access point picks a typical detail group, places it, ungroups it, carries the addresses over and connects with lines. A re-run is an incremental sync (unchanged access points are left alone, changed ones are redrawn, missing ones are deleted). The state is JSON in a service parameter of the view. There is no separate update button.

Tagging deliberately lives inside the lengths button rather than as a separate button: a device tag is a copy of an already known address, and the list of circuits on nodes is collected from the circuit path, which at this step has already been calculated as a list (a separate button would have to parse it back from the text `"F1.1 -> F1.2"` in the «Circuit route» parameter).

## 0. ACS parameters (SetupParameters)

Like `SetupParameters` in `SCS.panel` — checks that the ACS parameters are bound to the right categories and adds missing bindings from the connected shared parameters file. It doesn't make anything up: if a parameter's definition is in neither the project nor the shared parameters file, it only reports it.

## 1. Circuits and cables (AssignCircuitsAndCables)

### Controllers

- They are looked for among `OST_ElectricalEquipment`: the workset contains a keyword («Controller workset keyword») **and** the type name (`Symbol.Name`) contains a keyword («Keyword in the controller type name»).
- The controller must already have the «Device address» parameter filled in (entered by the user by hand when placing the equipment) — without it the controller is skipped.

### Circuits and devices

- The circuit has the «Panel» parameter (the controller) with a value equal to the controller's `Name`.
- The first non-excluded device of the circuit (other than the controller itself) is the one the calculation applies to. Devices whose family name contains a word from «Spare port keywords» aren't taken.

### What is written

- On the device: «Device address» by the mask `{controller address}.{N}`, where `N` is a simple sequence number of the connected device within one controller (across all of the controller's circuits, not split by device type).
- On the circuit: «Load Name» (`Designation.Address`, from the device type parameter «Designation» and the address written above), the cable type (the «Wire» parameter) — by a «device type : cable type» dictionary entered line by line in the settings window (format `keyword:cable_type`, one per line).
- On the controller: the «Controller tag» parameter = its own address.

## 2. Lengths and tags (CalcSkudLengths)

### The «near the controller» threshold

The straight 3D distance between the controller and the device is compared with a threshold («The «near the controller» threshold, m», in metres).

- **Below the threshold** — the length is calculated along orthogonal legs: `|dx| + |dy| + |dz|`, multiplied by a safety factor («Safety factor for the orthogonal calculation»). The whole amount is written to «Wire length in conduit» — the installation method is always conduit, «Wire length in tray» = 0.
- **Above the threshold** — the length is calculated along the graph of addressed ACS route nodes, **with the same algorithm and the same maths as in `SCS.panel`**: A* by node addresses (`astar_path`), splitting by installation method (`calc_lengths`), the vertical part separately, safety factors, consistent rounding (`balance_round_parts`) — all of these are the same functions of `lib/lowlife/scs_circuits.py`, not copies of them.

### ACS route nodes — separate from the SCS ones

SCS nodes show the path to the SCS cabinet, ACS nodes the path from devices to the controller, so they are **different** elements: their own panel, route and riser families, chosen in «ACS parameters» separately from SCS.

**The parameter names, though, are shared with SCS** (the segment address and the rest) — the disciplines are separated by **workset**, not by separate parameters. The keyword is set in the «ACS element workset keyword» field and is applied in three places:

- panels/controllers — otherwise an SCS cabinet matching similar keywords («панель», «шкаф») would become a traversal root for the ACS route;
- **collecting route nodes** — it goes over the whole document, not the active view, so without the filter an SCS node with the same address (`F1.3` exists in both) would get into the ACS graph and the path would run through someone else's route;
- **clearing «foreign» addresses** — otherwise an ACS run would erase SCS node addresses, and vice versa.

The summary after a run has a «Nodes of another workset skipped» line — if it's unexpectedly large, the nodes' workset isn't filled in the way the filter expects.

The order for distant devices:

1. ACS → **«ACS route nodes»** — places nodes along the ACS route lines;
2. ACS → **«ACS node addresses»** — numbers them and writes «Nearest route node» to controllers and devices;
3. ACS → **«Lengths and tags»**.

### What is written

- «Wire length» (the sum of conduit and tray — the very same number that goes into both the cable log and the schedule, with no separate recalculation or copying of the length from the circuit), «Wire length in conduit», «Wire length in tray» — separately (unlike SCS, where conduit and open conduit are combined in one parameter).
- «Installation method» — text by templates with `{}` for metres, based on the «in conduit»/«in tray» values.
- «Circuit route» — node addresses joined with `->` (empty for the «near the controller» case, since there are no graph nodes there).
- «Device tag» = the «Device address» value (a copy, no recalculation).
- «Circuit list» on every route node at least one circuit passes through (accumulated right during the path calculation — at this step the path already exists as a list of addresses).

## 3. Access point rooms (AssignSkudRooms)

Like «Write room number» for fire alarm/CCTV, but taking into account that the devices of one access point stand in different rooms (a reader outside, a lock in the opening, etc.). The logic:

- controllers and their devices are collected the same way as in «Circuits and cables»;
- a controller's devices are split by **access point** — the value of the «Access point number» parameter (empty on a device → access point 1);
- for each access point, the room name is taken for each device (the search in links — the same `room_info.py` mechanics), the most common non-empty value is chosen and written to **all** devices of the access point;
- the controller gets its room individually (no majority).

The target parameter (`room_param_name`) and the room value mask (`room_mask`, for example `Имя (Номер)`) are shared with fire alarm/CCTV and are taken from the «Write room number» settings (`room_info_settings`, Shift+click on that button); they aren't duplicated in the ACS settings.

## 4. Riser diagram (BuildSkudSchematic)

### The controller's schematic family and typical access point groups

- **Controller** — a single schematic family chosen in the category table by the «контроллер» row (`schematic_category_type_ids`); it has no typical group.
- **Access points** — Revit **detail groups**, one for each typical make-up (one-way: reader + lock + exit button + reed switch; two-way: reader ×2 + lock + reed switch; and so on). Chosen in «ACS parameters» → «Typical access point groups» (the list shows only detail groups). Each chosen group must be placed in the project at least once — its make-up is read from the first placed instance.

### Access points and matching a group

- A controller's devices are split by access point (the «Access point number» parameter, empty → access point 1).
- For an access point, a **signature** is built — a multiset of its devices' categories (the category is determined by the exact family type, see `schematic_category_device_type_ids`).
- An access point group with exactly the same signature is looked for. The category of schematic elements inside a group is determined by the schematic family type (`schematic_category_type_ids`).

### What the button does (incremental sync, like CCTV/fire alarm)

- finds the drafting view named `schematic_view_name` (or creates it) and reads the diagram state from the JSON in the view parameter `layout_param_name` (the same trick as `sot_layout_state`);
- the controller's schematic family is placed once per controller and gets the address; every schematic element (of both the controller and the access points) gets the source device's `UniqueId` in `device_uid_param_name` — a permanent diagram↔model link;
- **the unit of unchangedness is an access point.** On a re-run:
  - the same set of devices (by `UniqueId`) and the same matched group → the access point's **geometry is left alone** (manual layout is kept), only «Device address» / «Device tag» on the schematic elements are updated;
  - the set of devices or the matched group changed → the access point is **deleted and drawn again**;
  - the access point disappeared from the model → deleted;
  - a new access point → placed;
  - the controller disappeared from the model → its node and all access points are deleted;
- for a matched access point the chosen group is placed and ungrouped; schematic elements are matched to real devices by category (within a category — by address order);
- **no match** (no group for the access point's make-up): the fallback layout — each device as a separate schematic family of its category, plus a line in the report with the make-up and a request to create a group;
- controller → access point lines are **re-created on every run** (straight connectors have no manual routing), the anchor is the average position of the actual schematic elements (it follows manual moves);
- the new state is written back to the view parameter.

There's no separate «update» button — a re-run of «Riser diagram» finds the changes itself.

## Diagnostics (InspectSchematicDevices)

A separate button on `SKUD.panel`, not part of the working pipeline: for the selected controller it prints to the pyRevit output window all its circuits, all elements of each circuit (with the address and an «excluded by keyword» flag) and the final list of devices `BuildSkudSchematic` will put on the riser diagram — with duplicates by `ElementId` highlighted. Used for debugging when the diagram doesn't look as expected (extra/missing devices on a controller).

## Access points on doors (PlaceDoorAccessPoints)

A separate button on `SKUD.panel`, not part of the circuit pipeline: places access point elements (reader, lock, door closer, reed switch, emergency release button, intercom, exit button) on all doors of the selected rooms in the active view.

**Shift+click — the door layout and access point types.** Two views of the door — from outside and from inside the room — and a table of positions (side × role). For each position:
- which **families** (not types) may stand on it — several per position are allowed;
- the reference: from the left / from the right edge of the door (as seen by a person standing on that side; the distance is from the edge of the opening towards the wall) or «above the door, from the axis» (the horizontal distance from the axis to the right, minus — to the left);
- the height — from the bottom of the door (for «above the door» — from the top of the door);
- the offset from the wall surface towards the viewer (0 — on the wall);
- for the lock and reed switch — the **count** (2 — a double door: the second element is placed mirrored about the door axis; at a distance of 0 from the axis both coincide, so give an offset from the axis).

At the top of the window — **access point types** («New…», «Copy…», «Rename…», «Delete»). For the chosen type, in the «Type» column each position gets a family type from the families allowed for it (empty — the position isn't used in this type). The door layout shows the make-up of the chosen type: a filled marker — the position is used in the type, an outline — there are families but the position isn't used in the type, grey — no families chosen. Families and types are stored by name, so the settings carry over between projects (export/import to a file is there too).

**Click — a table of rooms.** The rooms of the active view (of the current model and visible links — for links the plan's level and crop are used) as «Name(number)», the level, the number of doors in each and a dropdown of access point types. The number is taken from the room parameter given in the «Room number parameter» field of the settings window (empty — the built-in «Number»). There's a search and «For all shown: … Assign». The choice per room is remembered until the next run. The make-up of the chosen type is placed on every door of the room.

**Which doors are equipped.** For each door the room on the other side is known. The settings have «Equip doors leading to rooms whose name contains: …» (by default `коридор, МОП, холл, лифтов, паркинг, тамбур, лестнич, вестибюл` — corridor, common areas, hall, lift, parking, vestibule, stair, lobby; case-insensitive, a word stem is enough; empty — all doors) and an «and outside doors» checkbox (no room behind the door). So a ventilation room's door to the corridor is equipped, while its door to an airlock isn't. In the rooms table, the «Doors» column is an «equipped / total» button: a click shows a list of doors («Mark · Family : Type → Коридор(1.01)») with checkboxes pre-ticked by the filter; a checkbox changed by hand is remembered for the door and wins over the filter («Reset to filter» removes the manual edit).

**Show on plan.** A button in the rooms table: on the active plan the doors of rooms with a chosen type are circled — green — will be equipped, red — excluded. Nothing is placed, the choice of types and doors is saved; the highlight (detail lines) is removed on the next run of the button.

The «inside» side is the side of the door facing the room (determined by a test point on each side of the door; the same check gives the room behind the door). A door with the same room on both sides isn't counted. The real width/height is taken from each door, the wall thickness from the faces of the host wall. A door shared by two selected rooms is processed once (with the first room). A re-run doesn't place duplicates (the same family within 100 mm).

How an element is placed depends on the family: wall-based — on the door's wall (only if the door is in the current model), face-based — on the wall surface (including walls of a link; «from the wall» doesn't apply), others — by level, turned to face away from the wall.

## Which shared parameters to set up for your project

As in `docs/en/scs-panel.md` — all text (except the ones marked otherwise), instance (except the one marked otherwise). The real names are made up by the user and entered in the settings window.

- **Generic Models** (ACS route/riser nodes): «Node address», «Previous address», «Cable installation type», «Circuit list» (multiline) — these are **the very same parameters** SCS uses; there's no need to set up separate ones. The disciplines are separated by workset; only the family type ids (their own nodes) stay separate for ACS.
- **Devices and controllers** (Communication Devices / Electrical Fixtures / Data Devices / Electrical Equipment): «Nearest route node» — instance, on both; «Device address» — instance; «Designation» — a device type parameter; «Controller tag» — a controller instance parameter; «Device tag» — a device instance parameter; «Access point number» — a device instance parameter (optional: empty → the controller has one access point; 1/2/… — if several access points are connected to the controller); the room name (by mask, by default «Имя (Номер)») — instance, on all devices and controllers; the target parameter and mask are set in the «Write room number» settings.
- **Schematic families** (Detail Items of the riser diagram): the service text parameter `device_uid_param_name` — instance; `BuildSkudSchematic` writes the source device's `UniqueId` into it (the diagram↔model link for the incremental sync). The counterpart of CCTV's `device_uid_param_name`.
- **Electrical Circuits** (`OST_ElectricalCircuit`): «Panel» (the controller), «Wire» (the cable type), «Circuit route», «Installation method» — text; «Wire length», «Wire length in conduit», «Wire length in tray» — numbers; «Load Name» — usually Revit MEP's native parameter.
- **Views** (`OST_Views`): a service text parameter for the riser diagram manifest (`layout_param_name`) — bind it to the «Views» category; `BuildSkudSchematic` writes JSON into it, don't edit it by hand. The counterpart of CCTV's `layout_param_name`.
- Not a parameter but a convention: the controllers' workset and their type name must contain the corresponding keywords; the «device type → cable type» dictionary and the device categories for the riser diagram are set by keywords in the settings window and aren't stored in the repository; the diagram's drafting view name (`schematic_view_name`) is also a setting, not a model parameter.
