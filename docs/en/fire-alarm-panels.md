[Русский](../fire-alarm-panels.md) | **English**

# SPS.panel and SOUE.panel — fire alarm and voice alarm (+ fire automation on CircuitsSPA.panel)

Two panels with the same set of buttons: **fire alarm** (СПС) and **voice alarm** (СОУЭ). They share the logic but have separate settings — their own panel, workset and length parameters, so each system is set up independently (`%APPDATA%\pyRevit\LowLifeSPS_settings.json` and `LowLifeSOUE_settings.json`).

The same logic («Loop circuits» + «Loop lengths», a device address of the form «panel.loop.number», `fire_alarm_settings`/`fire_alarm_buttons`) is also used by a third system — **fire automation** (СПА), but without a riser diagram and «Isolator–device circuits». It lives on `CircuitsSPA.panel` (`BuildLoopCircuitsSPA`, `CalcLoopLengthsSPA`), its own system `set_system("SPA")`, its own settings file `LowLifeSPA_settings.json`, the default workset keyword is «СПА» (for fire alarm/voice alarm it's filled in by hand in the settings, usually «СПС»/«СОУЭ»), the default circuit type is `Controls` (for fire alarm/voice alarm — `FireAlarm`). «Fire automation circuits» used to be a stub on the shared manual «panel -> devices» logic (`lowlife.manual_circuits`, as for SCS/ACS) — it was replaced with the addressable one once it became clear that fire automation addressing is the same as fire alarm's.

Fire automation devices have companion devices of the «Electrical Fixtures» category next to them (relay/addressable/control modules, `lowlife.companion_placement`) — they aren't addressable loop devices and aren't collected (see `fire_alarm_circuits._SYSTEM_EXCLUDED_CATEGORY_IDS`, an exception only for fire automation).

There is no separate settings button any more — every working button has its own settings on Shift+click (showing only the fields it uses itself; the system's JSON file is one for all).

The buttons in run order:

1. **Loop circuits** — creates an electrical circuit per loop and connects it to its panel. For voice alarm it is still `BuildLoopCircuits` on `SOUE.panel`; for fire alarm the button has moved to a separate panel `CircuitsSPS.panel` («Fire alarm circuits», `BuildLoopCircuitsSPS`) — every discipline now has its own panel for circuit-building buttons (CircuitsSCS/CircuitsSKUD/CircuitsSPS/CircuitsSPA), separate from the discipline's main panel.
2. **Loop lengths** (`CalcLoopLengths`) — calculates the length of every loop from device coordinates, tags the devices, gives them their previous address. It stays on its own panel (`SOUE.panel`/`SPS.panel`) — run after «Loop circuits» in the same order as before.
3. **Isolator–device circuits** (fire alarm only, `CircuitsSPS.panel`, `BuildIsolatorCircuitsSPS`) — see the separate section below.

«Voice alarm — typical floor» (`SOUE.panel/PlaceTypicalFloor`) isn't part of this chain either: it places speakers in every room of the architectural link (apartments — on a hallway wall; other rooms — by an acoustic calculation, wall or ceiling speakers under a suspended ceiling), with its own settings and the project's room table in `LowLifeSOUEFloor_settings.json` — see `lib/README.md`.

«Place relay, control modules» isn't here — it lives on `SPA.panel` (fire automation), not on `SPS.panel`: see [`companion-placement.md`](companion-placement.md).

## How fire alarm/voice alarm differ from SCS and ACS

| | SCS / ACS | Fire alarm / voice alarm |
|---|---|---|
| Route node | a separate marker family on the route line | **the device itself** |
| Topology | a tree from the panel along the route lines | a loop + branches from isolators |
| Length | along the line graph (A\*), or along orthogonal legs nearby | always from device coordinates |
| Long segments | yes | no |

There are **no** separate buttons for placing and addressing nodes here — they aren't needed: the designer sets the address right on the device, and the devices themselves serve as nodes.

## Addressing

Everything comes from two parameters; there's no need to parse a mask out of the family name:

| | «Designation» | «Device address» | Resulting tag |
|---|---|---|---|
| Panel | `ARK` | `3` | `ARK3` |
| Device | `BTH` | `3.1.2` | `BTH3.1.2` |

The device address is three numbers separated by dots:

- **3** — the panel number (links the device to panel `ARK3`);
- **1** — the loop number on that panel;
- **2** — the sequence number on the loop.

Devices with an address that can't be parsed don't get into loops and are listed in the report — that's how typos like `3.1` or `3.1.a` show up.

## 1. Loop circuits (BuildLoopCircuits)

Groups devices by the (panel, loop) pair and creates an electrical circuit for each group, connected to its panel. The circuit number is built by the format from the settings — `ШС-{}` by default, where `{}` is replaced with `panel.loop` (for example `ШС-3.1`).

A re-run is safe: a circuit with an already existing number isn't re-created.

### Devices on isolator branches aren't part of the main circuit

A device is excluded from the main circuit only if it already belongs to some electrical circuit of the document — checked through `fire_alarm_circuits.circuit_membership_map`, a map «element → the circuit it is already a member of», built over ALL electrical circuits of the document (any discipline, any number). In practice this means: the device is already connected to its isolator with a separate circuit through the «Isolator–device circuits» button (`BuildIsolatorCircuitsSPS`). Such devices are simply removed from the main line — Revit wouldn't let them be added to another circuit anyway (it fails with `electComponents`, without a clear message about the cause), but now this doesn't block the whole loop; it only excludes those particular devices and carries on with the rest. Isolators always stay in the main line (they're never a member of an isolator–device circuit themselves — there they are assigned as the source through `SelectPanel`, not as an element).

The «main line vs branch» split used to be decided by a geometric guess (`fire_alarm_loops.build_loop_tree`/`split_branch_devices` — the nearest already placed neighbour by distance). It was dropped: it was wrong both ways — it either kept in the main line devices that were really connected to an isolator with a separate circuit, or excluded ordinary devices that just happened to be geographically closer to an isolator than to the previous device by address, although electrically they had nothing to do with the isolator. Actual membership in an existing circuit is the only reliable source of this information, because Revit already knows it itself.

If all devices of some loop already belong to other circuits, no main circuit is created for it, and this is reported separately. In the pyRevit output window the button prints, for each loop, the number of isolators, devices in the main line and excluded devices — with the ID of the conflicting circuit for each.

A typical reason a device ends up «in another circuit» without actually being connected to an isolator is leftover test circuits (for example, created by hand through «Create System» in the Revit UI during diagnostics). To clean them up — the **«Delete circuits in view»** button (`CircuitsDelete.panel/DeleteViewCircuits`, the «Delete» panel, the «Electrical circuits» theme): after confirmation it deletes every electrical circuit that has at least one element visible in the active view.

### Circuit type

A fire alarm loop is created as a **fire alarm** circuit (`FireAlarm`) — this is the default in the fire alarm and voice alarm settings and is changed with the «Revit electrical circuit type» field. For voice alarm the type depends on how the speaker families are set up in a particular project, so it isn't hard-coded. Fire automation has a different default — `Controls` (as the old manual fire automation button had).

If a name is given that doesn't exist in this Revit version, the button says so and lists the available values.

Along the way the circuit gets a load name (`Designation` + the first device's address) and, if the «device type : cable type» dictionary is filled in, the cable type.

### Path mode, length and installation method

The same way as in «Isolator–device circuits»: right after the circuit is created it gets Revit's path mode `CircuitPathMode.AllDevices` («All Devices» instead of the default «to the farthest device») — so that Revit calculates the circuit `Length` from the actual positions of all loop devices itself, without drawing the wiring by hand. If the «Wire length» parameter is filled in in the settings, from this length (`circuit.Length` in feet → metres × the safety factor from the settings, rounded to a whole number) the following are written:

- «Wire length» — the result;
- «Installation method» (if both the «Circuit parameter «Installation method»» and «Conduit label format» fields are filled in) — the format from the settings with the length substituted, for example `ПВХл20-{}` → `ПВХл20-42`.

This is separate from the length calculation of the «Loop lengths» button below (it calculates from device coordinates through `calc_loop_length_ft` — needed for «Circuit route», «Previous address» and tagging, which need the loop topology). If «Loop lengths» is run after «Loop circuits», it overwrites «Wire length»/«Installation method» with its own calculation.

This whole part is in one try/except: a failure (an incompatible Revit API version, a broken format in the settings, etc.) is written to the pyRevit log but doesn't break the creation of the circuit itself or roll back the circuits of other loops already created in the same transaction.

### If the panel is listed as a circuit element (a «ring» circuit)

`create_circuit` (`lib/lowlife/electrical_circuits.py`) first tries to create the circuit only from the loop devices, without the panel — the panel is assigned separately through `SelectPanel`. From observation (diagnostics through `InspectConnectors`, see below): `ElectricalSystem.Create` requires at least one of the passed elements to be of the **«Electrical Equipment»** category (`OST_ElectricalEquipment`) — ordinary devices (sensors, detectors — category `OST_FireAlarmDevices`) can't create a circuit by themselves, only be a load in it, even though their connectors have the same `Domain=DomainElectrical` as the panel. The loop's isolators are modelled in the same «Electrical Equipment» category as the panel (see `fire_alarm_circuits.py`) — if the loop has at least one isolator, creating it without the panel in the list may succeed; if the loop consists only of ordinary detectors — it won't.

If Revit fails with `electComponents`, the button retries with the panel included in the element list, and then tries `system.Remove([panel])` to take it out of there BEFORE assigning it as the source through `SelectPanel` — while the panel is both an element of the circuit and its source, `SelectPanel` fails with «Not allow circular connection...» (the panel «sees» itself both as a load and as a source). If `Remove` isn't available for `ElectricalSystem` in this Revit version, the panel stays visible as an element of its own circuit, so the circuit may look closed on the plan/in the schedule.

For diagnostics — «Connector diagnostics» (`InspectConnectors`, a test button on `SPS.panel`): pick a panel, then several loop devices — it prints the category (marked if it's «Electrical Equipment») and the connectors (`Domain`/`ConnectorType`/`MEPSystem.SystemType`) of each element.

## 2. Loop lengths (CalcLoopLengths)

### How the length is calculated

From the coordinates of neighbouring devices (`|dx| + |dy| + |dz|`), with a safety factor from the settings. No route lines are needed: in fire alarm/voice alarm the device symbols stand right next to each other, and there's no room to draw lines between them.

If the panel has a point, the segment from the panel to the first loop device is included in the length too.

### Going between floors (a riser)

If two neighbouring devices by address (or the panel and the first device) are on different floors, the segment goes not directly by coordinates but through the nearest riser on each of the two floors: `device -> riser(floor A) -> riser(floor B) -> device`, each segment also along orthogonal legs. The riser is found by a keyword in the family name («Riser keyword» in the settings, «стояк» by default) — if there are several instances (different shafts/sections), for each end of the edge the riser nearest to IT on its own floor is taken independently (without explicitly matching shafts between floors — with an ordinary vertical riser aligned in X/Y on all floors it comes out the same either way). The categories searched for a riser are the same as for devices, plus «Generic Models».

The floor of a device/panel is the same parameter as on the riser diagram (the «Level» parameter in the settings; if empty — the real Revit level). If no riser keyword is set, or no riser was found on at least one of the two floors — the fallback: a straight segment along orthogonal legs, as before (including between floors, with the height difference `dz` as it is).

### Ring loop

The «Ring loop» field in the settings (`ring_loop`, «нет» (no) by default) — if «да» (yes), the main line (see «Branches from isolators» below — branches aren't part of the ring and aren't doubled) closes back to the panel: a segment from the **last device of the main line** (not of an isolator branch) to the nearest riser on its floor is added to the length; if no riser was found — a straight segment along orthogonal legs to the panel.

The «last device of the main line» is the last node by address whose parent in the loop tree is the immediately preceding node by address (and not an isolator via some earlier branch, see below) — so the main line is told apart from branches algorithmically, without a separate marker in the model.

### Branches from isolators

An isolator (a branch point) is recognised by a keyword in the family name («изолятор» by default). A branch leaves it and **doesn't come back** to the main line — otherwise the length would be counted with a return.

The `K` numbering runs through the whole loop, so «the main line continues» can't be told from «a device on a branch» by the number alone. Geometry decides: each next device attaches to whichever of the already placed candidates (the previous one in order or any isolator) is **closer** to it. So a branch hooks onto its own isolator instead of stretching across the whole route.

The actual topology after the calculation can be seen in two places:

- the «Previous address» parameter on each device — what it is really connected to;
- the «Circuit route» parameter — the whole loop as `3.1.1 -> 3.1.2; 3.1.2 -> 3.1.5`, where the second pair shows a branch from isolator `3.1.2`.

If a branch went the wrong way, it's fixed by rearranging the `K` numbers — geometry gives a hint, but the designer's numbering has the last word.

### What is written

- on the circuit: «Wire length», «Length in conduit» (loops are laid in conduit, so «in tray» = 0), «Installation method», «Circuit route»;
- on the devices: «Device tag» (`BTH3.1.2`) and «Previous address».

### Labelling wiring lines with the circuit number

If both the «Keyword in the wire line family name» and «Line parameter «Mark»» fields are filled in in the settings, the button additionally finds, in the active view, wiring lines already drawn by hand (line-based Generic Models, the same way as SCS routes — `lowlife.route_nodes.collect_segments`) near the loop's devices and writes the circuit number (`ШС-1.1`) to that parameter. «Near» means the line end is within ~300 mm (`fire_alarm_wire_marks.DEVICE_MATCH_TOLERANCE_FT`) of the point of a device/panel of that loop. The button doesn't draw lines itself — it only labels what's already drawn; if nothing is found, the field simply stays empty and no error is shown. An optional feature: if both settings fields are empty, it does nothing.

## 3. Isolator–device circuits (BuildIsolatorCircuitsSPS, fire alarm only)

`CircuitsSPS.panel`, the module `lib/lowlife/fire_alarm_isolator_circuits.py`.

Unlike «Loop circuits» (the whole loop at once by the panel.loop.number addressing), here the make-up of each circuit is chosen by hand — the button is for cases where a device or a group of devices is connected to an isolator separately from the loop's main addressing.

The selection order: fire alarm devices (`OST_FireAlarmDevices`, several allowed) and the isolator (`OST_ElectricalEquipment`, exactly one) are selected together, in one `PickObjects` (a window and/or clicks, confirmed with Enter/«Finish»). This is Revit's standard interactive selection, so its modifier rules apply: single clicks on elements are added to the list by themselves, but a repeated window selection without holding **Ctrl** replaces the previous selection entirely — for every window after the first, hold Ctrl. If the selection doesn't have exactly one isolator or has no devices, the button asks you to select again without ending the script. After confirmation the circuits for this set are built right away, and the button immediately offers to pick the next isolator with devices — no need to run the button again; the whole loop ends with Esc, after which the overall result is shown (circuits created, errors).

### Grouping rules

- All selected manual call points (determined by the word «ручной» in the family type name) are combined into **one shared** circuit (an isolator circuit may hold several call points).
- The remaining selected devices are combined into a **second shared** circuit.
- So an isolator has at most **2 circuits** — «manual» and «automatic». They can be built one at a time, over several runs of the button. If by the rules there would be more than 2 — a hard limit: the button **creates nothing** and shows a warning.

### What is written on the circuit

The same way as in «Loop circuits»:

- «Panel» — the isolator's name;
- «Load Name» — «Designation» + the address of the device with the highest sequence number in this circuit (for an address like `3.1.2` the number after the last dot is taken);
- «Wire» — if the «Wire» parameter is filled in in the settings and a cable type is chosen for the category of the circuit's first device (the «device type : cable type» dictionary in the fire alarm settings window) — the same catalog «Loop circuits» uses;
- «Wire length» and «Installation method» — the circuit immediately gets Revit's path mode `CircuitPathMode.AllDevices` («All Devices»), so that Revit calculates `Length` from the actual device positions itself without drawing the wiring by hand; from this length (feet → metres × the safety factor from the settings, rounded to a whole number) «Wire length» (the parameter from the settings) is written, and «Installation method» — by the «conduit label» format from the settings with the length substituted (for example `ПВХл20-{}` → `ПВХл20-42`), if both fields are filled in. This whole part is in one try/except: a failure (an incompatible Revit API version, etc.) is written to the pyRevit log but doesn't prevent creating the circuit itself;
- wiring lines near the devices/isolator — the same way as «Loop circuits» (see above), but the label is the circuit's **own Revit name** (`circuit.Name`, for example «Цепь 1») — an isolator–device circuit has no «Circuit Number» (unlike main loops, where the value of that parameter is written on the line).

## Diagnostics (InspectConnectors)

A separate button on `SPS.panel`, not part of the working pipeline: for the selected panel and several loop devices it prints to the pyRevit output window their category (marked if it's «Electrical Equipment» — see the section above) and electrical connectors (`Domain`, `ConnectorType`, `MEPSystem.SystemType`), and the list of `ElectricalSystemType`s available in the current Revit version. Used for debugging when circuit building refuses to create a circuit of a given type.

## Which parameters are needed

- **Panel** (`OST_ElectricalEquipment`): «Designation» (`ARK`), «Device address» (`3`) — both instance.
- **Devices** (fire alarm/security/communication devices/electrical fixtures): «Designation», «Device address» (`3.1.2`), «Device tag», «Previous address» — instance.
- **Electrical Circuits**: «Panel», «Circuit number», «Load Name», «Wire», «Circuit route», «Installation method» — text; «Wire length», «Length in conduit», «Length in tray» — numbers.
- **Wiring lines** (line-based Generic Model, optional): «Mark» — text; the family name must contain the keyword from the settings («Wiring lines» → «Keyword in the wire line family name»).
- A convention: the workset of the panel and devices contains the system's keyword; the isolator's family name contains the word «изолятор».

## For the future: marking a transition between floors (up/down)

Not implemented yet — this records the preferred approach so the decision isn't lost by the time fire alarm/voice alarm loops become multi-storey often enough to need a separate button.

The idea: a separate annotation family (Generic Annotation) whose **type name** is the direction — for example two types «Наверх» (up) and «Вниз» (down). The designer places an instance of this annotation at the point where the loop physically moves to another floor.

How to fit it into the existing pipeline (by analogy with isolator handling in `fire_alarm_loops.py`):

1. In `fire_alarm_settings.py`, add a setting with the keyword/name of the transition annotation family (on the same principle as `isolator_keyword` — the family name is a particular project's convention and isn't hard-coded).
2. In `find_devices`/`_collect` (`fire_alarm_buttons.py`), collect such annotations as a separate list with their points (they don't take part in device addressing, so they're outside `DEVICE_CATEGORIES`).
3. In `build_loop_tree`/`calc_loop_length_ft` (`fire_alarm_loops.py`), match each annotation to the nearest loop edge (between a parent and child node along the route) and read the direction from the instance's type name (`Element.Name.GetValue` on its `Symbol`, `u"наверх"`/`u"вниз"` — a case-insensitive comparison, like `isolator_keyword`).
4. Write the direction into `build_route_text`/a separate circuit parameter — for example add `↑`/`↓` before the address of the node after which the transition follows, or as a separate list at the end of the report.

This is an extension of `fire_alarm_loops.py` rather than a one-off fix of one script — the transition direction affects both the route text and potentially splitting the length by floor, if that's ever needed.
