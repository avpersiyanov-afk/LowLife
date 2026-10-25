[Русский](../detectors-to-slab.md) | **English**

# Detectors to slab (SPS.panel/DetectorsToSlab)

The «Detectors to slab» button on the fire alarm panel does two things — both at once or separately (chosen at launch):

1. **Moves fire detectors to the underside of the slab above them.**
2. **Labels on plans the slab height above the floor** in every room, shows where the slab is higher/lower than typical, and outlines rooms with a suspended ceiling with a filled region labelled «ПП» (suspended ceiling) and the ceiling height above the floor.

Slabs and ceilings are taken both from the model itself and from loaded links (architectural, structural), so different slab elevations in the building are handled by themselves — nothing needs to be set up per level.

## How it works

### Moving detectors

- Elements of the «Fire Alarm Devices» category are taken whose family or type name contains one of the words of the «Which devices to move» setting (by default — smoke, heat, flame, gas, ИП 212/ИП 101), except those with a word from «Exclude» (manual, ИПР, sounders, modules, isolators).
- Which detectors to move, the button asks after you choose the action:
  - **selected** — matching detectors among what was selected before the run; if nothing was selected before the run, after this window the button offers to pick detectors in the model (with a window or one by one, only matching ones can be picked; «Finish» on the options bar, Esc — cancel);
  - **all in the active view** — matching detectors visible in the current view; if it's a plan and «Move and label» is chosen, it is labelled too — the plan picker doesn't open;
  - **all on the levels of the chosen plans** — matching detectors whose level matches the level of one of the plans chosen next.
- For each detector, a ray goes up from a point above its level (the «Check point height» setting, 1500 mm by default) to the nearest slab («Floors», «Roofs» categories). The ray passes straight through a suspended ceiling («Ceilings» category) — the detector goes on the slab, not on the ceiling.
- The family's insertion point is raised/lowered to the underside of that slab (minus the «Offset from the slab underside», 0 by default). The offset-from-level/work-plane parameter is changed, or if there is none — the element itself is moved.
- **Flush-mounted** — if the family or type name has a word from the «Flush-mounted — place on the suspended ceiling» setting («встраив» by default), the detector is placed not on the slab but on the underside of the suspended ceiling above it (without an offset). If there's no suspended ceiling above it, it isn't moved and goes into the report.
- Face-hosted detectors (for example on a ceiling in a link) can't be moved in height — they're listed in the report and have to be re-placed by hand (or the family replaced with one not attached to a face).

### Column capitals

The elevation of the underside of the nearest slab above the detector is taken from the element's own geometry: the vertical from the point to where the ray hit is intersected with the slab body, and the underside is where it enters the body from below. For capitals modelled as floors attached to the slab, the ray (ReferenceIntersector) sometimes returns only the top face — without this refinement the elevation under a capital came out as its top.

The slab fills on the plan don't depend on the upward rays: the fill elevation is the elevation of the bottom face from the geometry, and the face visible from below is the lowest of the faces at the label point. Besides the slabs the rays hit, all structural floors (thicker than 150 mm — not floor finish) up to the highest face found are taken — so capitals that no ray hit get filled too. The ray at the label point goes only down — to the floor; if the floor there is more than 300 mm from the plan's typical floor (the median over all downward rays — at a column the floor slab has a hole and the ray falls lower), up to 4 more points inside the face are tried, and if none works, the typical floor is used. The same slab modelled in both the architectural and structural models (same elevation, extent and area) is filled once. Step lines are searched only along the edges of faces visible from below — finishes, screeds and duplicates don't enter the search. Columns are hidden from the ray (a ray going down above a column would hit the column bottom, below the floor). If the nearest thing above turns out to be a thin layer — the underside of the next floor's floor finish (thinner than 150 mm) — the point is checked as an opening (see below).

The report for each plan has a table of slabs above the floor: link, Id, type, underside elevation relative to the level, height above the floor, area and whether it was filled (or why not: less than 0.5 m², covered by a lower slab).

### Openings in slabs

Above an opening (a shaft, a void) the ray passes through the floor's slab and hits the slab of one of the floors above — the height would come out huge, and a «step» would be drawn around the opening. So if the slab found is above the next level, the button checks 4 points around at the «Largest opening size» distance (2500 mm by default). If at all points that have a slab (at least two) it's lower, the point is above an opening: the height is taken from the slab around the opening (both for the detector and for the room label), and the slab above doesn't enter the step search. High zones (double-height rooms, etc.) are wider than this size, and at least one point around lands at the same height — they don't count as openings. A narrow high zone (narrower than the opening size) may be taken for an opening — then reduce this size. How many points turned out to be above openings is in the report.

### Elevations on plans

**Slab fills.** Each slab above the floor — the bottom face of a slab the rays from this level hit — is filled with a hatch along its outline (with openings), coloured by height above the floor: one height — one colour. Inside — the label «Пер. +4,400» (the height of the slab underside above the floor at that point) and «Δ +0,650» if the height differs from the typical one. The typical height is the one with the largest slab area on the plan. A step shows as a change of hatch colour even where no red line was found. Faces under 0.5 m² (capitals, niches) aren't filled; nor is a face covered by a lower slab. The fill types are created by themselves: «LowLife пер. +4,400» (the hatch is the project's «diagonal» one, the colour is updated on every run). The report has the slab area for each height. Fills can be switched off in the settings.

**Rooms** (of links and the model, level matching the plan's level, the tolerance is in the settings) are checked at several points: for suspended ceilings only — no more than 3 (the room point and a 2×2 grid in big rooms), for labels in all rooms — the room point and a grid of up to 3×3. Rooms whose name contains a word from «Don't check rooms…» (by default stairwells, parking spaces) are skipped entirely — no rays, no labels. What to label in rooms is the «Labels in rooms» setting:

- **only suspended ceilings** (the default) — if the upward ray met a ceiling below the slab, the room is outlined with a filled region along its outline labelled «ПП +2,700» — the ceiling height above the floor;
- **all rooms** — also «Пер. +3,300» (a range if there are several heights) and «Δ» in every room, with a list of those differing from the typical one in the report;
- **none** — rooms aren't checked at all (faster; but then slabs for fills and steps are found only by the rays from detectors).

### Slab step line

Only the bottom horizontal faces of slabs that the rays from detectors and rooms hit as the nearest slab above (from this plan's level; there's no upper height limit — high zones above the next level count too) are taken — floor finishes, next-floor slabs and other link floors aren't gone through. If the edges of two faces with different elevations (a difference of 20 mm or more) run parallel and no farther apart in plan than the «Largest gap between the edges of neighbouring slabs» (600 mm by default — so slabs separated by a wall or a beam on the axis are found too), a line is drawn between them — along the middle of their shared stretch. Before drawing, each line is checked on both sides: the slabs visible from below there really must be at different heights, so edges of the next floor's finish and slabs lying on top of each other don't produce lines. The check uses the already read face geometry, without rays: «which face is visible from below at a point» is looked up through a spatial index (outlines are laid out into cells and strips in advance), so even thousands of checks take fractions of a second.

Pieces of one line (each pair of edges gives its own) are joined into one line before the check; a long line is checked in parts of ~3 m, and only the confirmed parts are drawn. If there are more than 20,000 lines, the longest ones are checked and the number of unchecked ones is in the report. At the end of the report — the time of each stage of the plan (rays in rooms, slab faces and rays down to the floor, steps, creating fills and lines). The step search can be switched off in the settings («Draw slab step lines» — «нет»): labels and suspended ceilings remain, and it's faster on large models.

Lines are drawn in the «LowLife — перепад плиты» line style («Lines» subcategory, red; created by itself, the weight is taken from the settings and updated on every run). How much the slab changed elevation is visible from the fill labels on both sides of the line («Пер. …», «Δ …»).

Labels are created with a separate text type «LowLife — отметки перекрытий» (created by itself as a copy of the default text type; the font and size can be changed in its properties), and filled regions are marked in «Comments» («LowLife ПП …», «LowLife пер. …»). A re-run deletes the previous run's labels, slab fills, suspended ceiling regions and step lines on the plan and draws them again — manual texts and lines of other styles aren't touched.

## Settings (Shift+click)

| Field | Default | What it sets |
|---|---|---|
| Words in the family or type name | дым, тепл, пламен, газ, ИП 212, … | which devices count as detectors (empty — all devices of the category) |
| Exclude if the name contains | ручн, ИПР, ИП 535, оповещ, модул, изолятор | what not to move |
| Flush-mounted — place on the suspended ceiling | встраив | detectors with this word in the family/type name go on the underside of the suspended ceiling |
| Insertion point offset from the slab underside, mm | 0 | how far below the slab to put the insertion point |
| Check point height above the level, mm | 1500 | where the rays up/down start — above the floor and below the suspended ceiling |
| Largest opening size in a slab, mm | 2500 | a zone surrounded by a lower slab and narrower than this is an opening (0 — don't check) |
| Room level matching tolerance, mm | 300 | a link room counts as on the plan's level if the level elevations differ by no more than this |
| Fill the slabs above the floor with a hatch by elevation | yes | slab fills with labels |
| Labels in rooms | suspended ceilings only | suspended ceilings / all rooms / none |
| Don't check rooms whose name contains | лестнич, машиномест, машино-мест, парковочн | rooms without labels or rays |
| Height rounding, mm | 10 | heights differing by less are one elevation |
| Labels | «Пер. {h}», «Δ {d}», «ПП {h}» | label texts; `{h}` — height above the floor, `{d}` — the difference from the typical one |
| Draw slab step lines | yes | «нет» — no step search |
| Red step line weight | 10 | the weight of the «LowLife — перепад плиты» style lines (1–16) |
| Largest gap between the edges of neighbouring slabs, mm | 600 | how far apart in plan the edges of slabs at different elevations may be for a step to be drawn between them |
| Filled region type | empty — the first non-masking one | the region type for rooms with a suspended ceiling |

## Speed

Slabs above and below a point are found by geometry, without a 3D view. At the start of a run the extents of all floors, roofs and ceilings of the model and links are laid out into a grid in plan; for a point, the elements above and below it are taken from it (up to 60 m above and 30 m below), and it's checked which of their horizontal faces the point falls into: bottom faces above the point are the underside of a slab or ceiling, top faces below it are the floor. Each element's faces are read once (the report has the face reading time), and Revit isn't queried at every point at all — hundreds of detectors are checked in seconds plus the face reading time. Elements with sloped faces (ramps, pitched roofs) are checked by intersecting the vertical with the body. This used to create a 3D view, and on a big model with links preparing it took about 30 seconds every run; now nothing is created in the model. Demolished elements are ignored; links rotated other than around the vertical are skipped (listed in the report). The same point isn't checked twice. All checks are done before the button changes anything in the model (moving detectors, labels, lines). Steps are searched only along slabs the rays hit, and only between nearly parallel edges. The report for each plan has step search counters (slabs under rays, edges, candidates, not confirmed by rays, drawn), and at the end — the time of each stage (moving detectors, each plan), so you can see what takes the most.

## Diagnostics

If no more than 30 detectors are selected before the run, the report gets a «Rays above the selected detectors» section: for each — what the ray up and down hits (distance, elevation relative to the level, category, type, element Id, link) and what slab height above the floor the button worked out from that. This helps understand where an unexpected elevation came from (a capital, an opening, a floor finish).

## Limitations

- It works only on floor/ceiling plans with a level; labels are placed at the room point.
- A slab that doesn't fall under the ray (for example an opening or a shaft right above the detector) won't be found — such detectors and rooms are listed in the report.
- Beams aren't taken into account: the detector goes on the slab, not on the underside of a beam.
