[Русский](../camera-fov.md) | **English**

# CCTV · Camera fields of view

Four buttons on `SOT.panel`, not connected to the CCTV riser diagram — the logic and the shared settings live in `lib/lowlife/sot_fov.py`, with their own file `%APPDATA%\pyRevit\LowLifeCameraFov_settings.json`:

- **«Fields of view»** (`CameraFov`) — draws the field of view of the selected CCTV cameras in the active view as a filled region (`FilledRegion`), clipping it by the room boundary from the linked model. It only reads parameters and writes nothing to the camera.
- **«Aim at room»** (`AimCameras`) — the opposite: it draws nothing but **turns** each camera along the bisector of its room, picks and **writes** the focal length (for varifocal ones) and the tilt (the «Auto-aiming» section below). The order: first this button, then «Fields of view».
- **«Check parameters»** (`CameraParamsCheck`) — diagnostics; it builds and writes nothing. Use it first when connecting a new camera family: pick one camera, and the button reads ALL its instance and type parameters (`sot_fov.diagnose_camera_params`) and, for each role from the table below, shows whether the name is set in `LowLifeCameraFov_settings.json`, whether such a parameter was found on the camera, whether its data type fits (Length/Angle/Text/Number), and which other camera parameters of the same data type are there as ready candidates. It separately checks that the camera's category is in `camera_categories` and that `tilt_param_name` is SPECIFICALLY an instance parameter (see «Auto-aiming» below). Plus two reference sections: the **geometry and orientation** of the particular instance in the project (the same direction source «Fields of view» uses — `FacingOrientation`/`BasisY`/`BasisX`/`HandOrientation`, mirroring, host, level, the final azimuth) and a **family breakdown** — the button opens the family file for editing without showing a window (`Document.EditFamily`), reads all types with parameter values, formulas, nested families, solids/voids, reference planes and connectors, and closes it without saving. The family breakdown section hasn't been checked in a live Revit (`sot_fov.inspect_family_definition`) — if one of the API assumptions doesn't work in your Revit version, that item just shows an error or is skipped; the rest of the report isn't affected. See the button's `bundle.yaml` for a detailed description of the report statuses.
- **«View from camera»** (`CameraPreviewView`) — creates (or updates) a Revit 3D perspective view at the selected camera's point, looking the same way and with a field of view fitted to its calculated angle of view — see the «View from camera» section below.

The port of the «camera field of view» Dynamo script to plain Revit and the breakdown of the original are in the discussion history; this page describes the final behaviour.

## Workflow

1. **Press the button first**, then pick cameras in the model. The selection filter (`ISelectionFilter`) lets through only the **«Security Devices»** category (`OST_SecurityDevices`) — camera families usually belong to it. A pre-selection isn't used.
2. The active view must be a **floor/ceiling plan or a drafting view** (`ViewPlan` / `ViewDrafting`). On a 3D view, section, elevation or sheet the button stops with a message.
3. Building runs in one transaction; at the end the pyRevit output window has a report for each camera (see below).

**Shift+click** (`EXEC_PARAMS.config_mode`) opens the settings window.

## How the zone is calculated

For each camera:

- **The viewing direction** is determined in turn: `FamilyInstance.FacingOrientation` → `Transform.BasisY` → `BasisX` → `HandOrientation⟂` (the first source with a non-zero horizontal projection). `FacingOrientation` takes into account the rotation and mirroring **of the instance itself** in the model.
  - If the camera is turned **not by rotating the instance but by a parameter inside the family** (then `FacingOrientation` doesn't change and all zones look the same way), give the name of that parameter in **`rotation_param_name`**. This is the «Вращение (поворот)» (rotation) of the original Dynamo script. The value is turned into a direction by the scale:

    ```
    azimuth = the family's «forward» + rotation_zero_deg ± value
    ```

    `rotation_zero_deg` — where the camera looks at a value of 0 (degrees from «forward», counter-clockwise), the sign is «−» if `rotation_clockwise = да` (yes). By default zero = 0, counter-clockwise — the value is simply added.
    **A composite camera** (a base + a nested shared camera family): if the parameter is on neither the camera itself nor its type, it is looked for in the nested **shared** families — that's how the rotation/tilt/optics belonging to the nested camera are found. Parameters of a **non-shared** nested family aren't visible in the project at all — they have to be associated with a parameter of the base, and the base parameter's name entered in the settings. If a rotation name is set but the parameter wasn't found anywhere, the «Fields of view» report says so in the `напр.:` (direction) field — «поворот не учтён» (rotation not applied).
    **An example — a rotating camera on a wall base** (the nested camera family rotates on the base): on the plan, with the wall at the bottom, 0 — looks right along the wall, 90 — up, away from the wall, 180 — left. Settings: `rotation_zero_deg = -90`, `rotation_clockwise = нет` (no), `rotation_range_deg = 0-180`. For a mirrored scale (0 — left, 180 — right): `rotation_zero_deg = 90`, `rotation_clockwise = да` (yes). If the zones look mirrored, switch both settings to the second option.
  - **`direction_offset_deg`** — a fixed correction, the same for all cameras (when the family geometry doesn't look «forward»).
  - The report for each camera prints the source used and the final azimuth — you can see whether it matches the real direction.
- **The horizontal and vertical angles of view are ALWAYS calculated.** They aren't typed in as degrees — they're calculated from the physical characteristics of the lens and sensor:

  ```
  hfov = 2·arctan(sensor_width / (2·f))
  vfov = 2·arctan(sensor_height / (2·f))
  ```

  where `f` is the focal length (`focal_length_param_name`) and the sensor is the format from `sensor_format_param_name` on the camera or, if it isn't there, the shared `sensor_format` from the settings. So the angle never drifts from the real lens by itself — especially important for a varifocal one, whose angle of view changes along with the focal length every time it is refocused on site. The zone radius is a separate «range» parameter (`distance_param_name`) — not optics, but the camera's declared recognition/observation range.
- **Taking the mounting height into account.** If the mounting height and downward optical axis tilt parameters are set, the zone is calculated as the projection of the cone (with the vertical angle already calculated above) onto the calculation plane:

  ```
  near = h / tan(tilt + vertical/2)     (the near dead zone)
  far  = h / tan(tilt − vertical/2)     (the far edge)
  ```

  With `tilt ≤ vertical/2` the upper ray goes into the horizon → the far edge is taken from the range parameter. The height `h` — either from the parameter or «the insertion point elevation minus the camera's level elevation», minus **the calculation plane height** (0 — the floor, 1500 — the face plane, etc.). If there's no height or tilt, the zone is built as a flat sector from the camera point (the original script's behaviour). The tilt can be picked automatically with the «Aim at room» button (see below).

- **Clipping by the room.** `room_rings_for_point` goes through all **loaded** links, takes the outline of each `Room` (`GetBoundarySegments`, finish/centre), tessellates it and converts it to host coordinates (`Curve.CreateTransformed`). The camera's room is determined by a **2D «point inside the outline in XY» test** — not `Room.IsPointInRoom`, which cut off a camera under the ceiling (it's sensitive to Z, and a camera is almost always above the room volume). If several rooms fit in XY (floors above each other), the one whose vertical extent contains the camera's elevation is taken, otherwise the nearest by height. A point outside all outlines → the nearest room within 90 mm («the camera sits in the wall»).

  If `GetBoundarySegments` returned no usable outline at all for a room (an open/damaged boundary — not unusual for rooms of complex shape), the fallback is a section of the room's ready-made **solid**, which Revit itself builds for area/volume (`_room_solid_rings` → the bottom horizontal face of the solid through `_horizontal_face_rings`). It works for rooms of any shape — concave, with several outlines (an inner courtyard), with arcs.

  **Columns aren't handled separately.** Columns usually have a finish (in the architectural model) marked as «room bounding» — Revit itself cuts their outline out inside the `Room` boundary and returns it through `GetBoundarySegments` as an extra inner outline (a «hole», `rings[1:]`). Clipping by this boundary already gives the shadow of a column without any separate code: `_clip_distance` shortens a ray at its first intersection with **any** room outline — outer or inner — in the same way.

The zone outline is a star polygon from the camera point, or an annular sector with a non-zero dead zone (`_zone_curveloop`). One `FilledRegion` of the chosen type is drawn; the border is on an automatically created line subcategory («СОТ_Зона обзора» by default).

## Idempotency

The filled region's «Comments» parameter gets `<mark>|<camera Id>` (the mark is `CCTV_FOV` by default). On a re-run, `_delete_previous` deletes from the active view the zones of the **selected** cameras (by this mark) and the DORI arcs (by the line style name `«… · DORI»`), then builds them again. Zones of other cameras in the view aren't touched.

## DORI zones (optional)

With the flag on and the sensor's horizontal resolution set, concentric arcs are added at the identification / recognition / observation / detection distances (250 / 125 / 63 / 25 px/m, EN 62676-4):

```
d = H_res / (2 · px/m · tan(horizontal angle / 2))
```

Arcs beyond the range aren't drawn.

## Parameters on the camera family

The button **doesn't create** parameters — it reads existing camera parameters whose names are set in the settings. The default names come from the original Dynamo script (`УГО_ПВ_...`) and should be changed to match your shared parameters file.

**Each of these parameters can be either an instance parameter or a type parameter** — you don't need to say which: the button checks the instance first, and if it's empty there (or there's no such parameter) — the type (`_find_param`). This is specifically for varifocal lenses: for two cameras of one type (the same model, the same angle of view and range — fittingly kept as TYPE parameters), the focal length and mounting height in practice are almost always different and adjusted on site — it's natural to keep them as INSTANCE parameters. You decide what to make which by your family; the button finds both options equally.

**If several camera families in the project call the same parameter differently** (for example «Вращение (поворот)» on a bullet camera and «УГО_Поворот» on a dome), you can list all the variants in the setting field separated by `;`: `Вращение (поворот);УГО_Поворот`. The button checks the names in order and takes the first one found on the particular camera (instance, then type) — so one setting per project works for all families at once. The «Check parameters» button shows which of the listed names worked for the selected camera.

| Setting (parameter name) | What is read on the camera | Revit parameter type | Units / range | Required | Usually instance or type |
|---|---|---|---|---|---|
| `focal_length_param_name` — «Focal length parameter» | the lens focal length — an input to the angle of view calculation | «Length» (→ mm) or «Number» (already mm) | 1…50 mm; varifocal 2.8–12 mm — the current value is taken | **yes** | **instance** (a varifocal lens is focused on site) |
| `sensor_format_param_name` — «Sensor format parameter» | a text value of the sensor format (like the «Sensor format» field below) — the second input to the angle calculation | «Text» | see the format table below | no (otherwise the shared `sensor_format`) | type |
| `camera_h_res_param_name` — «Horizontal resolution parameter» | the sensor's horizontal resolution, px — for DORI arcs and focal length by DORI | «Integer» / «Number» / «Text» (`1920`, `1920x1080`) | 1280…3840 | no (otherwise the shared `camera_h_res_px`) | type |
| `distance_param_name` — «Range parameter» | the maximum zone radius (the far edge, if not limited by the cone calculation) — the camera's declared range, not optics | **«Length»** | 1…100 m; typically 8–40 m | **yes** | type |
| `height_param_name` — «Mounting height parameter» | the camera's mounting height above its level | «Length» | 2…12 m; typically 2.5–4 m. Empty → «insertion point elevation − level elevation» | no | **instance** (each camera has its own height) |
| `rotation_param_name` — «Camera rotation parameter» | the camera's rotation angle INSIDE the family (when the instance itself isn't rotated) | «Angle» / «Number» | 0…360° (or within `rotation_range_deg`). Into a direction — by the `rotation_zero_deg` / `rotation_clockwise` scale | no | **instance** |
| `tilt_param_name` — «Downward optical axis tilt parameter» | the angle of the camera axis tilted down from the horizon | «Angle» / «Number» | 0…90°; 0 = looks horizontally; typically 10–35° | no | **instance** |

The horizontal and vertical angles of view **aren't** in this table — they aren't parameters, they're not typed in by hand, they're calculated from the focal length and sensor format (see below). If a parameter from the table is **not of the «Length»/«Angle» type** but «Number», the value is taken as is: lengths count as millimetres, angles — by the «Angle units» field (`angle_unit`; this field doesn't affect the angle of view calculation — the optics always give radians).

### How the angle of view is calculated

1. `focal_length_param_name` is looked for on the camera (instance, then type). Not found/empty/not a number — the status is `no_optics`.
2. The sensor format: first `sensor_format_param_name` on the camera (instance, then type); if it isn't there/isn't recognised — the shared `sensor_format` from the settings. Not found in either — `no_optics`.
3. `hfov = 2·arctan(width / (2·f))`, `vfov = 2·arctan(height / (2·f))` — both at once, in one calculation.

### Why there may be no dead zone («the cone starts right at the camera»)

The dead zone (an annular cut-out around the camera) is calculated only if **both** parameters — `height_param_name` and `tilt_param_name` — were found (on the instance or the type) and gave a value (the vertical angle for the formula has already been calculated by the optics, see above). If even one wasn't found, the zone is built as a flat sector right from the camera point, with no cut-out. The most common reason is that one of these parameters was a **type** parameter while the button checked only the instance and didn't find it. The report for each camera prints explicitly what was used: `h=3.00 м, наклон=45°, верт.угол=30°` (height, tilt, vertical angle), or `мёртвая зона не считается (не найдено: наклон)` (dead zone not calculated, not found: tilt) — this line shows right away what's missing. By the way, the tilt doesn't have to be picked by hand — see the «Aim at room» button below.

## Checking the zone — test values

To check the built zone against a calculation by hand, give one test camera these values (`height_param_name` / `tilt_param_name` / `focal_length_param_name` / `distance_param_name` must already be filled in with names in the settings, `sensor_format` — as shared text in the settings; the values below go on the camera itself):

| Parameter on the camera / in the settings | Value |
|---|---|
| sensor format (`sensor_format` in the settings) | `6x4.5` (explicit W×H in mm — round numbers for checking, not the format of a particular sensor) |
| focal length (on the camera) | `3 mm` |
| range | `20000 mm` (20 m — clearly more than the calculated far edge, so it doesn't cut it) |
| mounting height | `3000 mm` (3 m) |
| downward optical axis tilt | `45°` |
| camera rotation (if used) | `0°` (for the first check — so the azimuth matches the family's direction) |
| calculation plane height (`target_level_offset_mm`, in the settings) | `0` (the floor) |

The calculated angles with these numbers:

```
hfov = 2·arctan(6 / (2·3))   = 2·arctan(1.0)   = 90.0°
vfov = 2·arctan(4.5 / (2·3)) = 2·arctan(0.75)  = 73.7°
```

The camera's report should show exactly `угол 90°` and `верт.угол=74°` (rounded to whole numbers; the exact value is 73.74°). The far/near edges of the cone at `h=3 m`, `tilt=45°`, `vertical/2=36.87°`:

```
near = h / tan(tilt + vert./2) = 3 / tan(81.87°) = 3 / 7.0007 = 0.4286 m
far  = h / tan(tilt − vert./2) = 3 / tan(8.13°)  = 3 / 0.1429 = 21.00 m
```

`far` (21.00 m) is more than the given range (20 m) — the safeguard «the far edge can't be more than `distance_param_name`» kicks in, and the real far edge is **20.00 m**, not 21.00 m (check this too — a good test of the safeguard). The resulting zone is an annular sector 90° wide, from **0.43 m** to **20.00 m**. The camera's report: `R 0.4–20.0 м; h=3.00 м, наклон=45°, верт.угол=74°`. It's checked in Revit itself with the «Measure» tool from the camera's insertion point to the near and far arcs of the outline.

If instead of a ring you get a solid sector from the camera point itself (`R 0.0–…`), the height or tilt wasn't found; look at `cone_note` in the report (see above) — it says exactly what's missing. If the report shows numbers other than 90°/74°, check that the sensor format and focal length really are the ones entered (perhaps they were found on ANOTHER level — instance instead of type or vice versa, see `_find_param`).

Then change one parameter at a time and recalculate by hand:
- **`tilt=0°`** (the camera looks horizontally) → `near = 3/tan(36.87°) = 4.00 m`, `far → ∞` (in reality it's capped by the 20 m range).
- **focal length `6 mm`** (twice as long) → `hfov = 2·arctan(6/12) = 53.13°`, `vfov = 2·arctan(4.5/12) = 41.11°` — both angles are narrower, and at the same tilt the visible distance is greater (the typical effect of a longer lens — narrower but farther).

## Ceiling cameras looking almost straight down (domes)

The button's model is a **directional wedge**: the camera looks one way horizontally (the azimuth), and in that direction an annular sector is cut by the tilt/vertical angle. This is right for cameras pointed **diagonally down** — outdoor/ceiling PTZ, corner cameras, a «bullet» along a corridor: a `tilt` within 10–60° is reasonable there.

For a classic **dome camera on the ceiling looking straight or almost straight down** (`tilt` close to 90°) this model stops being physical: in the formula `near = h / tan(tilt + vert./2)`, at `tilt + vert./2 ≥ 90°` the tangent goes negative — the code clips the result to 0 (the dead zone disappears), which for a camera pointed at the nadir is partly right (it sees the point right below itself with no cut-out), but **the zone is still drawn as a narrow wedge by the horizontal angle**, although for a camera looking straight down the coverage is physically a **circle** around the mounting point (a full one if the lens/dome gives all-round view, or a wide sector — depending on the camera model), not a narrow wedge.

**The decision for your cameras**: they are domes, but with a rotating lens (pan/tilt inside the dome) — so their direction and tilt aren't fixed «at the nadir» but are adjusted to a particular mounting point, like an ordinary directional camera. So a separate circular/nadir mode wasn't added — the directional model (wedge + annular sector) fits them too, as long as `tilt_param_name`/`rotation_param_name` reflect the lens's real current position. Picking this tilt for a particular room is exactly what the next section is about.

If some particular camera's lens is still fixed straight down (tilt ~80–90°), don't give it a `tilt_param_name` value (leave the field empty on that instance): the zone is built as a flat sector of radius `distance_param_name`, with no dead zone and no split by tilt. The sector's width is still the calculated `hfov`.

An important caveat: since the angle of view is now always calculated (by the usual «pinhole camera» formula, `2·arctan(size/2f)`), it fundamentally doesn't suit a real **fisheye** (honest 180–360° horizontally) — this formula physically can't give more than ~180° at any focal length; real fisheye lenses are calculated by a different projection (equidistant, etc.). If some of your domes are real fisheyes, this button will understate their field of view; say so if that's your case, and a separate fisheye formula can be added.

## Auto-aiming: the «Aim at room» button

The second button of the panel, `SOT.panel/AimCameras`. It doesn't build a zone — it **aims** each selected camera and writes the result to the camera.

**Normal mode** (the default): you place and orient the cameras yourself, and the button picks only the **focal length** and **tilt**. Two extra modes are turned on in the settings (section ⑥): **auto-rotation** (`auto_rotate`) and **taking other cameras into account** (`auto_consider_others`).

The sequence for one camera:

1. **Room and range.** The camera's room is found (including from a link) and the range `R` — the `distance_param_name` parameter (usually a **type** parameter: the model's rated range, for example 20 m; looked for on both the instance and the type; without it the camera is skipped — `no_distance_param`).
2. **A fan of rays** (needed for auto-rotation and the «by area» focal length). Rays go out from the camera all around in 1° steps to the room boundary; each is cut at the range `R`. A ray's weight is the area of a narrow sector of the room within `R`. When other cameras are taken into account, the area already seen by other cameras gets a weight of 0.1.
3. **Rotation** — only with `auto_rotate = да` (yes). The azimuth is chosen at which a sector of the lens's **widest** angle (at `auto_focal_min_mm`; for a camera with a type focal length parameter — its current angle) covers the largest weight. If several azimuths in a row qualify (a «plateau» — within 1 % of the maximum), the middle of the plateau is taken — the bisector: for a camera in a corner that's the diagonal, for a camera in the middle of a wall — the perpendicular to the wall. The rotation is written to `rotation_param_name` if it is set and found as an **instance** parameter — by its scale (`rotation_zero_deg`/`rotation_clockwise`), and if `rotation_range_deg` is set, the direction is chosen only from those reachable within that range (a rotating camera on a wall won't turn to face the wall); otherwise the family instance itself is rotated around the vertical through its insertion point.
4. **The working distance** `L = min(to the wall along the viewing axis, R)`.
5. **Focal length** (only if `focal_length_param_name` is an **instance** parameter — a varifocal lens), by `auto_focal_mode`:
   - **«площадь»** (area) — the narrowest angle around the axis that holds `auto_coverage_pct` % of the weight (the room area within `R`);
   - **«DORI»** — a frame at distance `L` with the width `resolution / px_per_m` (the camera parameter `camera_h_res_param_name`, if empty — the shared `camera_h_res_px`, section ⑤; and `auto_dori_level`): `angle = 2·arctan(frame_width / 2 / L)`;
   - **«авто»** (auto, the default) — DORI if the wall along the axis is farther than the range (a big room: a car park, a warehouse), otherwise «area».

   Then `f = sensor_width / (2·tan(angle/2))` within `auto_focal_min_mm`…`auto_focal_max_mm`. An example for a car park: `L = R = 20 m`, 1920 px, recognition 125 px/m → a 15.4 m frame, angle 42°, for a `1/2.8` sensor — `f ≈ 7.3 mm`. Without a resolution DORI is impossible — the focal length is calculated by area (the report notes it).
6. **Height above the calculation plane** `h = mounting_height − target_level_offset_mm` — the same plane (floor / faces / desktops) as in «Fields of view». The mounting height is a camera parameter or the elevation above the level; if there is none, `auto_default_height_mm` is written.
7. **Tilt** by `auto_tilt_mode`:

   ```
   ось (axis, default):  tilt = arctan(h / L)
   верх (top):           tilt = arctan(h / L) + vert.angle/2
   низ (bottom):         tilt = arctan(h / auto_max_near_zone_mm) − vert.angle/2
   ```

   «ось» (axis) — the centre of the frame at the target point at the far wall or at the range (the usual aiming practice: h = 3 m, L = 20 m → 8.5°). «верх» (top) — the top edge of the frame lands there instead (the camera looks steeper). «низ» (bottom) — the tilt from the desired dead zone. The vertical angle comes from the (already chosen) focal length and the sensor; if the optics aren't found — `auto_default_vfov_deg`.
8. **Warnings** (the status `ok_warn`, written anyway): the dead zone `h / tan(tilt + vert.angle/2)` is larger than `auto_max_near_zone_mm`; the tilt is larger than `auto_max_tilt_deg`; with the «by area» focal length — part of the room is outside the frame and the wall is farther than the range; with DORI — the needed detail level can't be reached (the lens doesn't give such a narrow angle).

### Taking other cameras into account

With `auto_consider_others = да` (yes) cameras are aimed **one by one** (in selection order). All cameras of the same categories in the active view that are **not selected** are taken into account up front — as they stand now; each selected one is added too once aimed. A camera's «coverage» is its sector (azimuth ± horizontal angle/2, from the dead zone to the far edge), clipped by its room — the same model as in «Fields of view». So with auto-rotation neighbouring cameras spread out in different directions, and the «by area» focal length doesn't widen for spots already covered. Without auto-rotation, this only affects the «by area» focal length.

**Important:** for this button `tilt_param_name` must be an **instance** parameter, not a type one — otherwise one run would change the tilt of all cameras of that type at once. If it is a type parameter — the status is `tilt_not_instance` and the camera is skipped. The same for the focal length: a type parameter isn't touched.

The order: **first «Aim at room» → then «Fields of view»**. The report for each camera shows the result: azimuth, distance to the wall, `L`, height, angles, tilt and mode, dead zone, how much the camera was rotated and how, the chosen focal length. Statuses: `ok` / `ok_warn`, `no_room` (no room found), `no_wall_hit` (no boundary met along the viewing axis — the room outline is open), `no_distance_param`, `missing_inputs` (no height, or the camera isn't above the calculation plane), `tilt_not_instance`/`tilt_readonly`.

### Checking auto-aiming by hand

A test camera: `sensor_format=6x4.5`, `auto_focal_min_mm=1`, `auto_focal_max_mm=50`, `auto_coverage_pct=100`, `auto_tilt_mode=ось`, `auto_rotate=да`, `auto_focal_mode=площадь`, `target_level_offset_mm=0`, height `3000 mm`, range `20000 mm`. Put it in a corner of a square 6×6 m room (slightly away from the walls) and point it anywhere. Expected:

```
azimuth     — along the room's diagonal (45° from the walls)
angle       ≈ 90° (the room corner)          -> focal length ≈ 6 / (2·tan45°) = 3.0 mm
vert.angle  = 2·arctan(4.5 / 6)            = 73.7°
L           = the diagonal ≈ 8.49 m
tilt        = arctan(3 / 8.49)             = 19.5°
dead zone   = 3 / tan(19.5° + 36.9°)       ≈ 2.0 m  -> a warning (> 1.5 m)
```

## All settings (Shift+click)

Saved to `%APPDATA%\pyRevit\LowLifeCameraFov_settings.json`; moved between projects with the «Export/Import settings…» buttons (`settings_transfer`). `*` — required (`sot_fov.require` in `script.py`, plus a check that «the sensor format is set one way or another» — by a parameter or the shared field), checked before cameras are picked. The values in Russian (`да`/`нет`, `авто`, `ось`, …) are typed as given.

| Section | Key | Values | Default |
|---|---|---|---|
| ⓪ What to pick | `camera_categories` * | BuiltInCategory names (`OST_SecurityDevices`, `OST_CommunicationDevices`, `OST_DataDevices`, `OST_ElectricalEquipment`, `OST_GenericModel`) and/or Russian category names, comma-separated | `OST_SecurityDevices` |
| ① Camera parameters | `focal_length_param_name` * | the focal length parameter name | *(empty)* |
| | `sensor_format_param_name` | the name of a text camera parameter, or empty | *(empty)* |
| | `sensor_format` * | `1/2.8`, `1/3`, `1/1.8`, `2/3`, `1` (by the format table, 16:9 frame); `1/3 4:3` — the same with an explicit aspect ratio; or `5.37x4.04` (mm, W×H); or `5.37` (width only, height by 16:9) — the shared value if there's no parameter above | *(empty)* |
| | `distance_param_name` * | the name of a «Length» type parameter | `УГО_ПВ_Дистанция до объекта` |
| | `angle_unit` | `авто` (auto) / `градусы` (degrees) / `радианы` (radians) — for tilt and rotation (not for the angle of view — it's calculated) | `авто` |
| | `height_param_name` | a parameter name, or empty | *(empty)* |
| | `rotation_param_name` | the name of the in-family rotation parameter, or empty | *(empty)* |
| | `tilt_param_name` | a parameter name, or empty | *(empty)* |
| | `rotation_zero_deg` | degrees from the family's «forward», counter-clockwise — where the camera looks at rotation 0 | `0` |
| | `rotation_clockwise` | `да` / `нет` (yes/no) — the rotation parameter grows clockwise | `нет` |
| | `rotation_range_deg` | `min-max`, for example `0-180`, or empty — the in-family rotation limits | *(empty)* |
| | `direction_offset_deg` | a number, degrees — a common extra rotation for all cameras | `0` |
| ② Plane and shape | `target_level_offset_mm` | mm above the level: `0` — the floor, `1500` — faces, `800` — desktops | `0` |
| | `draw_dead_zone` | `да` / `нет` — draw the cut-out under the camera (an annular sector) | `да` |
| | `ray_count` | an integer, rays per sector; 64–128 | `96` |
| ③ Room clipping | `clip_to_rooms` | `да` / `нет` | `да` |
| | `room_boundary` | `отделка` (Finish) / `центр` (Center) | `отделка` |
| ④ Appearance | `fill_type_name` | a `FilledRegion` type name, or empty (the first available) | *(empty)* |
| | `line_subcategory` | the «Lines» subcategory name for the outline (created) | `СОТ_Зона обзора` |
| | `zone_tag` * | the mark string in the zone's «Comments», written as `mark|Id` | `CCTV_FOV` |
| ⑤ DORI zones | `draw_dori` | `да` / `нет` | `нет` |
| | `camera_h_res_param_name` | the name of a camera parameter (usually a type one) with the resolution, or empty | *(empty)* |
| | `camera_h_res_px` | an integer, px: `1920`, `2560`, `3840` — shared, if the camera doesn't have the parameter above | *(empty)* |
| ⑥ Auto-aiming | `auto_rotate` | `да` / `нет` — turn the camera along the room's bisector | `нет` |
| | `auto_consider_others` | `да` / `нет` — take the coverage of other cameras in the view into account | `нет` |
| | `auto_focal_mode` | `авто` / `площадь` / `DORI` (auto / area / DORI) — how to pick the focal length | `авто` |
| | `auto_dori_level` | `обнаружение` / `наблюдение` / `распознавание` / `идентификация` (detection / observation / recognition / identification) or a number of px/m | `распознавание` |
| | `auto_coverage_pct` | %, the share of the room area (within the range) to keep in the frame when picking the focal length | `90` |
| | `auto_tilt_mode` | `ось` / `верх` / `низ` (axis / top / bottom) — how to calculate the tilt | `ось` |
| | `auto_default_height_mm` | mm — if the camera height can't be determined otherwise | `3000` |
| | `auto_default_vfov_deg` | degrees — if the vertical angle can't be determined otherwise | `30` |
| | `auto_focal_min_mm` | mm — the lower bound of the automatic focal length range (a continuous varifocal) | `2.8` |
| | `auto_focal_max_mm` | mm — the upper bound of the same range | `12` |
| | `auto_max_tilt_deg` | degrees — the «raise the camera» warning threshold by tilt | `60` |
| | `auto_max_near_zone_mm` | mm — the «raise the camera» warning threshold by dead zone; in the `низ` tilt mode — the desired dead zone | `1500` |
| ⑦ View from camera | `view3d_type_name` | the name of the `ViewFamilyType` for the 3D view created, or empty (the first available) | *(empty)* |

Boolean fields also accept `1/0`, `true/false`, `yes/no`, `вкл/выкл`.

### Table of optical sensor formats (`sensor_format`)

An «inch» format gives the **diagonal** of the active area; the width and height come from the diagonal and the frame's aspect ratio. By default the frame is **16:9** — IP surveillance cameras (1920×1080, 2560×1440, 3840×2160) almost always have it. For a 4:3 frame, add the ratio: `1/3 4:3` (any `A:B` will do). When in doubt, give `WxH` explicitly (from the sensor datasheet: the number of pixels × the pixel size).

| Format | Diagonal, mm | W×H at 16:9, mm | W×H at 4:3, mm |
|---|---|---|---|
| `1/4` | 4.50 | 3.92 × 2.21 | 3.60 × 2.70 |
| `1/3.6` | 5.00 | 4.36 × 2.45 | 4.00 × 3.00 |
| `1/3.2` | 5.68 | 4.95 × 2.78 | 4.54 × 3.41 |
| `1/3` | 6.00 | 5.23 × 2.94 | 4.80 × 3.60 |
| `1/2.9` | 6.23 | 5.43 × 3.05 | 4.98 × 3.74 |
| `1/2.8` | 6.46 | 5.63 × 3.17 | 5.17 × 3.88 |
| `1/2.7` | 6.72 | 5.86 × 3.29 | 5.38 × 4.03 |
| `1/2.5` | 7.18 | 6.26 × 3.52 | 5.74 × 4.31 |
| `1/2.3` | 7.66 | 6.68 × 3.76 | 6.13 × 4.60 |
| `1/2` | 8.00 | 6.97 × 3.92 | 6.40 × 4.80 |
| `1/1.9` | 8.46 | 7.37 × 4.15 | 6.77 × 5.08 |
| `1/1.8` | 8.93 | 7.78 × 4.38 | 7.14 × 5.36 |
| `1/1.7` | 9.50 | 8.28 × 4.66 | 7.60 × 5.70 |
| `2/3` | 11.00 | 9.59 × 5.39 | 8.80 × 6.60 |
| `1/1.2` | 13.30 | 11.59 × 6.52 | 10.64 × 7.98 |
| `1` | 16.00 | 13.95 × 7.84 | 12.80 × 9.60 |

An example, lens `f = 2.8 mm`: `1/3` → 86°, `1/2.8` → 90°, `1/2.7` → 93° horizontally; `1/3 4:3` → 81°.

The formula is for a lens without distortion. The rated angle of wide-angle lenses (2.8 mm and less) is sometimes another 10–15° larger (100–110°) because of barrel distortion: the frame edges are compressed and fit more of the scene. Such an addition isn't modelled here — if you need the rated width, pick `WxH` so that `2·arctan(W / (2·f))` gives the rated angle.

## «No camera can be picked» — what to check

1. **The camera family's category.** Select the camera in the model → the category is written at the top of the «Properties» palette. If it isn't «Security Devices» but, for example, «Communication Devices», «Data Devices», «Electrical Equipment» or «Generic Models», enter the corresponding name (`OST_CommunicationDevices` / `OST_DataDevices` / `OST_ElectricalEquipment` / `OST_GenericModel`) in the `camera_categories` field (Shift+click); several are allowed, comma-separated.
2. **The active view type** — a floor/ceiling plan or a drafting view. The button doesn't work on a 3D view, section, elevation, sheet, legend or schedule.
3. **Required settings** — `distance_param_name`, `focal_length_param_name`, `zone_tag` and the sensor format (`sensor_format` or `sensor_format_param_name`) are filled in.

## The report for each camera

After a run, the pyRevit output window prints a line for **each** selected camera: a marker (`OK` / `~` — built without clipping / `FAIL`), a clickable link to the element, the type name and mark, the status and details.

For built zones the details are a summary of the calculation: `азимут 137°, угол 72°, R 0.0–18.3 м; напр.: FacingOrientation + поворот 25.0°; обрезка по помещению: помещение (1 по XY) (312 сегм.)` (azimuth, angle, range; direction source + rotation; room clipping: room (1 by XY) (312 segments)). It shows whether the zone took the right direction and how the room was found (the number of segments includes inner outlines — «holes» from columns).

The statuses are printed in Russian:

| Status | Reason / what to do |
|---|---|
| `построена` (built) | the zone was created and clipped by the room |
| `построена (без обрезки — помещение не найдено)` (built without clipping — no room found) | there's no `Room` under the camera point in any link |
| `построена (без обрезки — обрезка дала пустой контур)` (built without clipping — clipping gave an empty outline) | the camera is right against a wall or a wrong room was picked up — built without clipping |
| `нельзя посчитать угол обзора (фокусное/матрица)` (can't calculate the angle of view (focal length/sensor)) | the details give the reason: the focal length parameter name isn't set, the parameter wasn't found on the camera, it isn't numeric, the focal length = 0, or the sensor format isn't set/recognised either on the camera or in the settings |
| `нет параметра дальности` (no range parameter) | the camera doesn't have the `distance_param_name` parameter |
| `вырожденная геометрия` (degenerate geometry) | the details specify: `расчётный угол обзора = 0…` (calculated angle of view = 0 — something's wrong with the focal length/sensor despite the parameters being found), `дальность = 0…` (range = 0 — empty / not «Length»), `не удалось определить направление [Facing=… / BasisY=… / …]` (couldn't determine the direction — vectors for diagnostics) |
| `нет точки вставки` (no insertion point) | the camera's `Location` isn't a `LocationPoint` |
| `ошибка создания` (creation error) | `FilledRegion.Create` rejected the outline — increase `ray_count` or simplify the room |

### If all zones look the same way

The camera is turned by a parameter inside the family rather than by rotating the instance. Enter the name of that parameter in `rotation_param_name` (Shift+click). To check: the azimuth of different cameras in the report should become different. If the zones are turned but the wrong way (by 90° or mirrored), set up the scale: `rotation_zero_deg` and `rotation_clockwise`.

### If rooms aren't found (all zones «without clipping»)

The report line after «без обрезки —» gives the reason:

| Text in the report | What it means |
|---|---|
| `в проекте нет связей (RevitLinkInstance)` (no links in the project) | the architectural model isn't loaded as a Revit link |
| `связи есть, но не загружены` (there are links but they aren't loaded) | the link is «Unloaded» — Manage Links → Reload |
| `в связях (N шт.) нет размещённых помещений` (no placed rooms in N links) | rooms aren't placed in the linked model, or it's the wrong link (MEP/structural instead of architectural) |
| `проверено помещений: N, точка вне всех контуров по XY` (N rooms checked, the point is outside all outlines in XY) | in plan the camera is outside rooms: moved into a wall/shaft by more than 90 mm, stands in a corridor without a room, or the link is offset/rotated relative to the site (a different coordinate system) |
| `помещение (из N по XY — ближайшее по высоте)` (room — of N by XY — nearest by height) | a room was found, but the camera's elevation didn't fall into the extent of any floor — check the mounting elevation and the rooms' «Base Offset»/«Limit Offset» |

Rooms are taken from **all** loaded links — there's no need to specify the file separately. The category is the link's standard «Rooms» (`OST_Rooms`).

### If the outline of a particular room is never built

It means neither `GetBoundarySegments` nor the fallback solid section (`_room_solid_rings`) worked — the room has no calculated geometry at all. Usually this means it's genuinely **not enclosed** (Revit shows a yellow cross instead of a fill on the plan: a gap in the walls, room separators not placed). It's fixed in the architectural model, not in the button's settings.

### Columns don't cast a shadow in the zone

A column's shadow isn't handled separately but comes straight from the `Room` boundary: the column must have a finish (in the architectural model) marked **«Room Bounding»** — then Revit itself cuts its outline out inside the `Room`, and `GetBoundarySegments` returns it as an extra inner outline. If there's no shadow:

- check in Revit itself that «Room Bounding» is on for the column finish (a property of the element wrapped around the column — not of the structural column as such);
- make sure the room was **recalculated** after that (move it or open its boundary editing and confirm) — Revit doesn't always update the outline itself;
- in the camera's report, look at the number of segments after «обрезка по помещению: … (N сегм.)» — it should grow when the room gets the column's inner outline.

### «Clipping gave an empty outline»

It means clipping by the room boundary degenerated the outline to nothing, and the button fell back to «without clipping» by itself (the status `ok_clip_failed`). A common cause was too dense a grid of vertices (a complex boundary, many inner outlines from columns) giving neighbouring zone outline points closer together than Revit is willing to accept for a line segment (`Line.CreateBound` threw an exception, and that used to abort building the whole outline). The threshold for merging close points has been increased (`_MIN_SEG_FT`, ~3 mm — with a margin above Revit's real minimum), and a single problematic segment no longer breaks the whole outline — it is skipped rather than cancelling the whole build. The zone is built in any case (the button doesn't crash).

## Units (in short)

- **Angles** (tilt, rotation): the «Angle» type → radians; the «Number» type → by the `angle_unit` field (by default «авто» = degrees for «Number»). The angle of view (horizontal/vertical) doesn't belong here — it isn't a parameter but a calculation result, in radians right away.
- **Lengths** (range / height / focal length): the «Length» type → Revit's internal feet are converted automatically; the «Number» type → treated as millimetres.

## View from camera

The fourth button of the panel, `SOT.panel/CameraPreviewView`. It writes nothing to the camera itself — it creates (or, on a re-run on the same camera, updates in place — idempotent by the view name `СОТ · {camera} · id{Id}`) a Revit 3D perspective view placed at the selected camera's point and looking where it looks: the same direction and tilt source as «Fields of view»/«Aim at room» (`_camera_azimuth`: `FacingOrientation` + `direction_offset_deg` + `rotation_param_name` by the `rotation_zero_deg`/`rotation_clockwise` scale; `tilt_param_name` for the downward tilt — if it isn't found, the view is horizontal and the report notes it). The eye height is the same as the mounting height for fields of view (`height_param_name`, or the insertion point elevation minus the level elevation, or `auto_default_height_mm` if nothing was found).

The camera itself and its nested families (base, housing) are **hidden** in this view — the eye stands at the camera's insertion point, inside its housing, and otherwise they would block the frame.

**Field of view.** Revit has no direct API to «set the camera's angle of view» — but a perspective view's crop box is physically a section of a pyramid with its apex at the eye point, so the ratio of the crop box's half-width/half-height to the section depth is the same at any depth. Revit lays out the perspective frame's X/Y on the `Max.Z` plane (the near one, negative): `Xmax = −Zmax·tan(hfov/2)`, `Ymax = −Zmax·tan(vfov/2)`. The button sets `Max.Z = −0.1 ft` (~3 cm) itself and calculates X/Y at that depth for the camera's calculated `hfov`/`vfov` (focal length + sensor format, the same optics as for fields of view); the far plane (`Min.Z`) stays standard. The depth used to be taken from the standard `Max.Z`, and at `|Max.Z| < 0.1 ft` it was replaced with 10 ft without changing `Max.Z` itself — the frame came out dozens of times wider, and the view showed almost half the building. The camera range (`distance_param_name`) isn't used for this — the angle doesn't depend on the depth it's measured at.

If the optics aren't set up on the camera (no focal length/sensor), the view is still created/repositioned, just with Revit's standard field of view (the status `ok_no_optics`).

**A caveat:** the relation `Xmax = −Zmax·tan(angle/2)` is taken from working Dynamo/API examples, but there's no live Revit in this environment. So the report for each camera prints what Revit ends up storing in the crop box (`[crop: X …, Y …, Z … фт -> по глубине |Max.Z| A°×B°]`). How to check:

1. Build «Fields of view» for the camera and open its 3D view.
2. The frame edges on the floor should coincide with the zone's side borders on the plan (it's handy to put two arbitrary elements on the zone border and see whether they land exactly on the frame edge).
3. If the frame is noticeably wider/narrower than the zone, send the report line with `[crop: …]`: the numbers show at what depth Revit actually lays out the frame; the fix is local (`build_camera_preview_view` in `lib/lowlife/sot_fov.py`).

## Ideas for a more accurate calculation (not implemented)

- `ReferenceIntersector` with `FindReferencesInRevitLinks = True` over all visible elements — honest ray tracing instead of the ready `Room` outline (it would take into account, for example, a column without a finish/«Room Bounding», furniture, etc.); a 3D view is needed.
- A Boolean intersection of solids (`BooleanOperationsUtils`) of the cone and the room volume — exact clipping taking the room/ceiling height into account.
