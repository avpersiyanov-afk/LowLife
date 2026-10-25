[Русский](../equipment-tags.md) | **English**

# Equipment tags (Tools.panel → «Equipment tags»)

Places and arranges equipment tags (`IndependentTag`) on the active plan/section/elevation so that they stand neatly and don't overlap.

## How to use

The button has two modes. It asks which one you need; if only tags are selected beforehand, the first one starts right away.

- **«Arrange selected tags»** — select tags (or equipment: then all its tags in this view are taken), or pick them with a window after pressing. Only these tags move, no new ones are created, and the other tags in the view are obstacles.
- **«Tag equipment»** — select equipment (or pick it with a window after pressing). A table opens: a row for every family without a tag in this view, with a tag type from the matching category or «— don't tag —». The choice is remembered per family until the next run. Tags are placed only for the ticked rows and arranged right away; existing tags are left alone.

Everything is done in one transaction (Ctrl+Z undoes it all at once).

Shift+click — settings (mm on the sheet, multiplied by the view scale):

| Setting | Default | Meaning |
|---|---|---|
| Tag offset from the equipment | 3 | Distance from the equipment extent to the column/stack of tags; if there isn't enough room, 2× and 3× are tried |
| Gap between tags | 1 | Spacing between neighbouring tags |
| Leader shoulder length | 3 | The horizontal part of the leader in front of the tag |
| «Nearby» — if closer than | 8 | Equipment closer than this gets tags as one block |

## How it is arranged

- **Side by side horizontally** (or a single element) — tags in a stack one above the other above the equipment (or below it), with right-angled leaders: vertically from the element and a horizontal shoulder to the tag. The order in the stack keeps leaders from crossing.
- **One above the other** — tags in a column to the side at one offset, each opposite its element; if they don't fit, they spread apart with a gap.
- **A grid** (several rows and columns in one cluster) — cut into rows.
- For each cluster the sides (right/left, top/bottom) and offsets are tried; the option chosen has no overlaps with tags already placed, other equipment of the same categories, other tags and texts, and no crossing leaders. If there's no clean option, the least bad one is placed and the report says how many overlaps/crossings remain.

## Two-line tags

A tag family counts as two-line if at least one of its types has «/» in its name (for example «Марка/Длина»). Types of such a family with «/» are arranged as full two-line tags; types **without** «/» — as tags with only the top line: only the top half of the tag is counted in the layout, and a neighbouring tag or leader may cross into the empty bottom line. Stacks of such tags come out twice as dense. Families where no type has «/» are arranged by their full extent.

Revit brings the leader to the middle of the tag's full height. For a tag with only the top line that's the line between the two rows, so the leader shoulder is set at the height of that line rather than the middle of the text. Otherwise there'd be a kink in front of the tag.

## Limitations

- The leader starts at the **symbol**, not at the family: whatever the element actually draws in this view is taken, the leader end is put on the edge of the symbol's extent, and the symbol's extent itself counts as «occupied» — tags don't go on top of it. Symbolic lines are visible in the element's geometry. A nested annotation (that's how most devices' symbols are made) isn't exposed by Revit in the geometry, and its extent in the view merges with the 3D body. So in a temporary copy of the view (rolled back, nothing stays in the model) the button measures the element at 1:1000 and 1:2000: the annotation grows with the scale, the body doesn't, and from the two measurements the symbol extent is recalculated to the view's scale.
- If an element has **no symbol** in the view (neither lines nor an annotation), the tag goes to the family itself, as in Revit: the family's extent in the view is counted, the leader points at the insertion point, and its end is attached to the element — Revit puts it on the family itself and moves it along. Such elements are listed in the report as «Без УГО — марка к семейству» (no symbol — tag to the family).
- For elements with a symbol the leader end is free (`Free`): only then does it sit exactly on the symbol's edge with a straight kink. Revit's own tools can't attach to a nested symbol: Revit always puts an attached end on the 3D body, and a family's reference planes can't be tagged. So LowLife does the attaching. The button remembers in the tag where the leader end is relative to the device. A background handler (registered when Revit starts) moves the end along when the device is moved, rotated or mirrored, while the kink and the tag stay in place, like a Revit attached leader. If you drag the leader end by hand, the new spot is remembered. Limitations:
  - it only works for people who have LowLife installed; for everyone else the model opens without warnings, but the leader end doesn't follow when the device moves;
  - tags borrowed by another user in worksharing aren't moved;
  - if the symbol moved inside the family (by an offset parameter) while the device itself stayed in place, the leader end won't follow — run «Arrange tags» again.
- The tag size is taken from its extent in the view, so tags with long text spread apart correctly. Where Revit brings the leader to the tag is decided by the tag family.
- The layout logic is covered by tests outside Revit (`tests/test_tag_layout.py`); the Revit part (`equipment_tags.py`) has only been checked by reading the code.
