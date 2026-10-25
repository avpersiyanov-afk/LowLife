[Русский](../detector-access.md) | **English**

# Detector access (SPS.panel/DetectorAccess)

The «Detector access» button on the fire alarm panel checks whether every fire detector can be reached from the floor (from a stepladder) for maintenance, and shows the result on plans:

- each detector's **access zone** is circled: **green** — accessible, **red** — not, with the reason as a label («Нет доступа: перекрыт: Воздуховоды» — no access: blocked: ducts);
- for an inaccessible one the **nearest spot** it can be moved to is searched: a green circle of the free zone is drawn there, an orange **move arrow** from the detector, and the label «Перенести ПИ на 650 мм» (move the detector by 650 mm).

After the run the inaccessible detectors are selected; the full list with reasons and the obstacles found is in the output window.

## Running

1. (Optional) select detectors — then only they are checked.
2. Press the button and tick the floor plans to show the access zones on. Without a selection, all detectors on the levels of those plans are checked.
3. A re-run deletes the previous run's circles, arrows and labels on the plan and draws them again.

Detectors are picked the same way as in «Detectors to slab»: the «Fire Alarm Devices» category, a word from «Which devices to check» in the family or type name and none of the «Exclude» words. It's convenient to move the detectors to the slab/ceiling with that button first and then check access with this one.

## What is checked

For each detector, rays going up and down (from a point at the «Check point height» above the level, including architectural/structural link elements) find the floor, the slab and the suspended ceiling above it. Then, in order:

| Result | When |
|---|---|
| above a suspended ceiling | the detector is above the suspended ceiling found under it — it can't be reached from the floor (a hatch is needed) |
| no floor under it | the ray down didn't find a floor or went more than 1 m below the level (a shaft, an opening, a double-height space) |
| sits at the floor | the detector point is less than 0.5 m above the floor — it hasn't been raised to the slab/ceiling yet |
| blocked by building services | the **access zone** — a cylinder of the «Access zone radius» (500 mm by default) from the floor up to the detector — has ducts, pipes, trays, conduits, their fittings and accessories, flex ducts/pipes, mechanical or electrical equipment (in the model and links) or elements of the categories from the «More obstacle categories» setting. If the obstacle is right under the detector (within a 100 mm circle) — «перекрыт» (blocked), otherwise «зона доступа: …» (access zone: …) |
| too close to a wall | the zone is free, but in plan the detector is closer than the «Smallest distance from the detector to a wall» (500 mm by default) to its room boundary. If the detector is also blocked by services, both reasons are in the label («зона доступа: Трубы; до стены 300 мм») |
| too high above the floor | the detector is above the «Largest detector height above the floor» (if set) |
| accessible | none of the above |

The distance to the wall is measured to the room boundary (a room of the architectural link or the model) — walls, and also room separators if the room boundary is defined by them. Detectors outside rooms aren't checked by this rule.

The top of the checked volume is the detector point minus «Don't count as an obstacle what is right at the slab/ceiling» (150 mm by default): luminaires, grilles and conduits tight against the ceiling next to the detector don't block access, while a duct or tray hung under the slab does. Services above a suspended ceiling don't block a ceiling-mounted detector either.

Obstacles are taken with their real position in plan: straight segments of pipes, ducts, trays and conduits as a strip along the axis the width of the cross-section (with insulation), so a duct running diagonally in plan doesn't «occupy» its whole rectangular extent. Fittings, accessories and equipment — by their extent.

## A new spot

For «blocked by building services», «too close to a wall» and «no floor under it», the nearest point is searched (in rings around the detector with the «Search step», no farther than «Look for a free spot no farther than») where:

- the access zone is free of obstacles;
- the point is in the same room as the detector (rooms of links and the model) and no closer than the «Smallest distance from the detector to a wall» to its boundary — if the detector is in a room at all;
- there is floor under it at the same height (±300 mm);
- above it is the same mounting surface at the same height (±100 mm): for a slab-mounted detector — a slab with no suspended ceiling, for a ceiling-mounted one — a suspended ceiling.

If there's no such point, the report says «свободного места в радиусе … мм не найдено» (no free spot within … mm). The button doesn't move detectors — it only shows where to.

## Graphics on the plan

- circles — detail lines in the styles «LowLife — зона доступа ПИ» (green), «LowLife — нет доступа к ПИ» (red), the arrow — «LowLife — перенос ПИ» (orange); the styles are created by themselves, and their colour and weight can be changed in «Line Styles» (they're reset on the next run);
- labels — the text type «LowLife — доступ к ПИ» (created as a copy of the default text type; the font and size can be changed in its properties).

A re-run finds and deletes the previous run's graphics by these styles and the text type; manual lines and texts of other types aren't touched.

## Settings (Shift+click)

| Field | Default | What it sets |
|---|---|---|
| Words in the family or type name | дым, тепл, пламен, газ, ИП 212, … | which devices to check (empty — all devices of the category) |
| Exclude if the name contains | ручн, ИПР, ИП 535, оповещ, модул, изолятор | what not to check |
| Access zone radius under the detector, mm | 500 | a circle in plan that must be free of services from the floor up to the detector; circled on the plan |
| Don't count as an obstacle what is right at the slab/ceiling, mm | 150 | how far below the detector the checked volume ends |
| More obstacle categories | empty | Revit category names, comma-separated, for example «Мебель, Осветительные приборы» (furniture, lighting fixtures); names not found are in the report |
| Smallest distance from the detector to a wall, mm | 500 | closer to the room boundary — «too close to a wall»; a new spot is searched no closer than this (0 — don't check) |
| Largest detector height above the floor, mm | 0 — don't check | higher — «too high above the floor» |
| Check point height above the level, mm | 1500 | where the rays up/down start — above the floor and below the suspended ceiling |
| Look for a free spot no farther than, mm | 3000 | 0 — don't look for a new spot |
| Search step, mm | 100 | the step of the search rings |
| Labels | «Нет доступа: {r}», «Перенести ПИ на {d} мм» | `{r}` — the reason, `{d}` — the move distance in plan |

## Limitations

- Walls, columns and beams aren't counted as obstacles in the access zone (walls only count through the distance to the room boundary) (beams can be added with the «Structural Framing» category — but by their extent, so sloped ones give extra).
- The extent of fittings and equipment is a rectangle aligned with the model axes: equipment rotated in plan takes a bit more room than it really does.
- Code-required distances from the detector to luminaires, ventilation grilles, etc. aren't checked — only access from the floor.
