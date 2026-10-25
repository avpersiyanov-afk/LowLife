[Русский](../ss1.md) | **English**

# SS1-8Mile — placing communication network equipment

The «SS1-8Mile» button (**SS1** panel) does this in one run on the ticked levels:

1. **Cross-connects** — two in every telecom (СС) shaft on every level the shaft passes through: in the centre of the shaft, at the given heights, turned with the shaft. The «Room» parameter gets the text from the settings («Ниша СС» by default).
2. **Cable entries** — by the door from the apartment hallway to the corridor/lobby (from the architectural link), on the wall face on the apartment side, facing the hallway. In a two-level apartment (one lot name on different levels) — only in the lower hallway. «Room» gets the lot name.
3. **Circuits** — from cross-connect No. 1 of the telecom shaft of its own section on the same level to every entry (if the section parameters aren't set — from the nearest shaft on the level).
4. **LOI filling** — cross-connects and entries get the «Masses» parameters copied by the settings of the «Fill LOI» button (see [loi-panel.md](loi-panel.md)).
5. **Entry tagging** (device address) by a mask.

Before placing, all instances of the chosen cross-connect and entry types on the ticked levels are deleted. Everything is one transaction; **Ctrl+Z** undoes it all.

## What to prepare

- **Telecom shafts** — instances of one «Generic Model» family whose type or instance has the «СС» checkbox (a Yes/No parameter) ticked; shafts of other systems have other checkboxes ticked.
- **Cross-connect and entry families** loaded into the project.
- **An architectural link** with «Прихожая» (hallway), «Коридор»/«Вестибюль» (corridor/lobby) rooms and the doors between them; apartment rooms have a «Lot name», and with several sections — a «Section number».
- **Parameters on the equipment**: «Room» and «Device address» — easiest to create with the «Shared parameters» button (system «SS1», see [parameters.md](parameters.md)).

## Settings (Shift+click)

The main window (dropdowns of the loaded families, each with a search by part of the name):

- **Telecom shaft** — the «Generic Model» family → the checkbox (a Yes/No parameter; «СС» is picked by itself if present).
- **Cross-connect** and **cable entry** — family → type.
- **Electrical circuit type** — Data by default.

The other fields:

| Field | What to enter |
|---|---|
| Apartment room where the entry is placed | «Прихожая» by default. |
| Neighbouring rooms | Comma-separated, «Коридор, Вестибюль» by default — the entry is placed by the door to one of them. |
| Room parameter «Lot name» | In the architectural link. The value is written to the entry; two-level apartments are found by it too. |
| Room parameter «Section number» and shaft parameter «Section number» | The circuit runs from cross-connect No. 1 of the shaft of the same section. Both empty — from the nearest shaft on the level. |
| Instance parameter «Room» | Cross-connects get the text below, entries — the lot name. Empty — not written. |
| Text for cross-connects | «Ниша СС» by default. |
| Heights, mm | Cross-connect No. 1 (1000), cross-connect No. 2 (1500), entry (2700 — the default in the launch window). |
| Entry offset from the wall face | Into the hallway; 0 — exactly on the face. |
| Height tolerance when matching levels, mm | A link door's level matches a model level if the elevations differ by no more than this; the same tolerance is used to check whether a shaft passes through a level. |
| Entry tagging parameter | The entry's «Device address» parameter. Empty — tagging isn't filled in. |
| Tagging mask | Letters are replaced by the values of their parameters, everything else stays as is: «A.B.C» → «3.1.45». The parameter for each letter — a line «A=Этаж; B=Секция; C=Номер квартиры». Letters can be typed in Russian (А = A). Values are taken from the entry (after LOI), otherwise from the hallway in the link. |

## Report

What was placed (cross-connects, entries, circuits) and warnings: «ВНИМАНИЕ» for hallways without a lot name (an entry is placed in each of them), for doors where the apartment side couldn't be determined, and for elements that didn't fall into any LOI «Mass».
