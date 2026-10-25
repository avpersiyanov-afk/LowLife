[Русский](../tray-tags.md) | **English**

# Tray tags (Tools.panel → «Tray tags»)

Places and arranges cable tray tags on the active plan/section/elevation the same way as [«Equipment tags»](equipment-tags.md): neatly, without overlaps or crossing leaders, in a stack/column at one offset with shoulder leaders.

## How to use

Two modes, as in «Equipment tags». The button asks which one you need; if only tags are selected beforehand, the first one starts right away.

- **«Arrange selected tags»** — select tray tags (or trays: then all their tags in this view are taken), or pick them with a window after pressing. Only these tags move; no new ones are created.
- **«Tag trays»** — select trays (or pick them with a window after pressing). A tag is placed on every tray without a tag in this view and arranged right away; existing tags are left alone. If the project has several tray tag types, the button asks which one to place (the last chosen one comes first in the list).

What isn't tagged:

- **fittings** (elbows, tees, transitions) — neither the selection nor the window takes them; only straight tray segments are used;
- **sloped trays** — the axis is tilted from the horizontal by more than the tolerance (0.5° by default), including vertical segments. The report says how many were skipped.

Everything is done in one transaction (Ctrl+Z undoes it all at once).

Shift+click — settings (its own file, not shared with «Equipment tags»):

| Setting | Default | Meaning |
|---|---|---|
| Tag offset from the tray, mm | 3 | Distance from the tray edge to the stack/column of tags; if there isn't enough room, 2× and 3× are tried |
| Gap between tags, mm | 1 | Spacing between neighbouring tags |
| Leader shoulder length, mm | 3 | The horizontal part of the leader in front of the tag |
| «Nearby» — if tray midpoints are closer than, mm | 8 | Trays closer than this get tags as one block |
| Sloped — if steeper than, degrees | 0.5 | Steeper trays aren't tagged |

Millimetres are on the sheet and are multiplied by the view scale.

## How it is arranged

- The tag points to the **middle of the visible part** of the tray (taking the view's crop region into account), and the leader starts **at the tray edge** — whatever the tray's direction in the view, including diagonal.
- **Parallel trays of one run** (midpoints closer than «nearby») get tags as one block: the tag points spread along the run like a staircase, and the tags stack above (below) a horizontal run or in a column beside a vertical one — at one offset; leaders don't cross or lie on top of each other.
- From there — the same layout as «Equipment tags»: trying sides and offsets, with no overlaps on other tags, texts, trays and fittings in the view. If there's no clean option, the least bad one is placed and the report says how many overlaps/crossings remain.
- Two-line tags (types with «/» in the name) are handled the same way as in «Equipment tags».

## Limitations

- The leader end is free (`Free`) so it sits exactly on the tray edge opposite the tag. It doesn't follow the tray when the tray moves — after editing the run, run «Arrange selected tags».
- The layout logic and tray geometry are covered by tests outside Revit (`tests/test_tag_layout.py`, `tests/test_tray_tags_core.py`); the Revit part (`tray_tags.py`) has only been checked by reading the code.
