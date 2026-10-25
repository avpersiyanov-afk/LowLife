[Русский](../tray-opening-boxes.md) | **English**

# Opening boxes for trays (Tools.panel → «Opening boxes for trays»)

Places a box (a temporary opening) at every spot where the selected cable tray passes through a wall or floor of the model chosen in the settings: this model, one of the loaded links (for example architectural or structural) or all at once (the default).

## How to use

1. Load a box family into the project: its family name contains «бокс» and its type name «временный» (the words can be changed in the settings). The family is unhosted (level-based) or work-plane-based. If several types fit, the button asks which one to place.
2. In a model with worksets you need a workset with «боксы» in its name: new boxes are created in it (several matching — the button asks, none — it stops with a hint).
3. Select the trays (or pick them with a window after pressing; fittings aren't taken) and press the button.

The box sits in the middle of the crossing of the tray axis with the wall/floor:

| Where | Width (family X axis) | Depth (Y axis) | Height (Z axis) |
|---|---|---|---|
| in a wall | the tray's footprint on the wall + 50 mm (for a tray at a right angle — tray width + 50) | wall thickness | tray height + 50 mm |
| in a floor | tray width + 50 mm | tray height + 50 mm | floor thickness |

In a wall, the box's X axis runs along the wall, in a floor — along the tray width; the box always stands level (it only rotates around the vertical). Through walls — only horizontal trays, through floors — only vertical ones; sloped trays and those passing through a wall at too sharp an angle are skipped (in the report).

The «Comments» parameter of each new box gets the Revit user name and the creation date and time (for example «ivanov 05.03.2026 09:07»).

Sizes are written to the box's instance parameters. If a size parameter in the family is a type parameter, the button creates a type «<type> WxDxH» (or takes an identical one already created).

If there's already a box at the crossing (any family with «бокс» in its name: its insertion point is close by or it covers the middle of the crossing), no new one is created there and the existing one isn't changed — the button shows a warning with the number of such spots, and the output window lists them. Everything is done in one transaction (Ctrl+Z undoes it all at once). The report is in the pyRevit output window.

## Settings (Shift+click)

- words in the box family and type names;
- words in the box workset name (by default «боксы»; empty — the active workset);
- where the family's insertion point is — the middle of the box or the middle of its bottom;
- the width/depth/height parameter names (by default «Ширина», «Глубина», «Высота»);
- how much bigger than the tray cross-section the box is (50 mm by default — in total, not per side) and thicker than the wall/floor (0 by default);
- the model to look for crossings in: only this one, one of the loaded links (the list of links comes from the open model; for a link placed several times, all instances are taken) or this model together with all links;
- what to cross (walls and/or floors);
- the tray slope tolerance and the largest angle of passing through a wall.

## Testing

The pure geometry (`lib/lowlife/tray_boxes_core.py`) is covered by `tests/test_tray_boxes_core.py`; the Revit part (`tray_boxes.py`) has only been checked by reading the code.
