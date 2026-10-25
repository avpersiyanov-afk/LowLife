[Русский](../soue-typical-floor.md) | **English**

# Voice alarm — «Typical floor» placement

The «Voice alarm — typical floor» button (**Voice alarm** panel, SOUE) places speakers in every room of the linked architectural models on the ticked levels:

- **in apartments** — one speaker per lot, on a hallway wall (or in the first room found from the list in the settings). In a two-level apartment — on the lower level. The apartment's other rooms aren't equipped;
- **in the other rooms** (except excluded ones) — the number, positions, the speaker itself and its power tap are chosen by an acoustic calculation: the sound level at least the room noise + 15 dB at a height of 1.5 m. Wall speakers go on walls and columns; under a suspended ceiling — ceiling speakers.

All changes in one transaction — undone with **Ctrl+Z**.

## What to prepare

- **An architectural link** with rooms: apartment rooms have the «Lot name» parameter filled in.
- **Speaker families** loaded into the project. For automatic selection the type (or a placed instance) needs these parameters:
  - SPL sensitivity (1 W/1 m), dB — a number or text «87 дБ»;
  - transformer power taps, W — all of them separated by «/»: «1,5 / 3 / 6»;
  - version «Настенный»/«Потолочный» (wall/ceiling) — if there's no such parameter, the version is looked for in the family/type name («настен», «потол»).

  All project types that have an SPL parameter take part in the selection — the «Project speakers…» button in the settings shows what was found.
- **A «Room» parameter** on speakers — optional, if the room should be written (see [parameters.md](parameters.md)).

## Settings (Shift+click)

The main window:

- **Apartment speaker** — family (with a name search) → type, mounting (wall/ceiling) and height.
- **Height of wall speakers** in the other rooms.
- **«Project rooms: noise and exclusions…»** — a table of all unique room names from the links: a category from the catalog, noise level N (by hand or by category), «exclude». It has a search, a «no noise level» filter, Excel export and import. New names get a suggestion by part of the name (shafts, niches, loggias are suggested for exclusion).
- **«Project speakers…»** — what was found for automatic selection.
- **«Parameters and offsets…»**:

| Field | What to enter |
|---|---|
| Where to place the speaker in an apartment | Rooms by priority, comma-separated: «Прихожая, Холл». |
| Room parameter «Lot name» | A parameter of the link's rooms. A lot that has a room from the list above is an apartment. |
| SPL / power taps / version | Speaker parameter names (type or instance). |
| Power if there's no parameter, W | 1.5 by default. |
| Offset from wall corners / from doors and windows, mm | 300 and 200 by default. |
| Height tolerance when matching levels, mm | A link room's level matches a model level if the elevations differ by no more than this. |
| Instance parameter «Room» | In apartments the lot name is written, elsewhere the room name. Empty — not written. |

## How it is calculated

- **Speaker range**: P0 = SPL + 10·lg P, the required level Nreq = N + 15, rmax = 10^((P0 − 6 − Nreq)/20); in plan R = √(rmax² − (h − 1.5)²), where h is the mounting height.
- **Positions**: the room is covered with a grid of calculation points (0.5 m step); candidates are along walls and column faces outside door and window zones (wall speakers) or grid nodes (ceiling speakers). A point is covered by a speaker no farther than R, in line of sight and, for a wall speaker, in front of the wall. The set chosen has the fewest uncovered points, then the fewest units, then the lowest total power.
- **Type and tap** are tried among all suitable project speakers; the chosen tap is written to the instance's power parameter if it is writable.
- **Ceiling**: a suspended ceiling is searched upwards from the room point (in the link); if there is one — a ceiling type in its plane, otherwise a wall one.

## Running

1. Press the button and tick the levels (all by default).
2. The button shows room names without a noise level for you to fill in; those left without noise are skipped.
3. If there are already speakers on the levels, the button asks: delete them and place again, or equip only the rooms without speakers.
4. The report has a table by room: level, category, noise, mounting, height, range, count, uncovered points.
