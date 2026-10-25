[Русский](../tray-section.md) | **English**

# Tray section (TraySection)

A button on the **Tray section** panel (ToolsTraySection). Draws on a drafting view a cable tray cross-section with the actual cable layout and a cable table — from Excel data.

## Source data

A .xlsx or .xlsm file (macros don't matter — the file is read directly, no Excel needed). The data comes from the **«сводные данные для плагина»** sheet — it is looked up by name among all sheets of the workbook (fallback — the «Сводный» sheet); if there is no such sheet, the button offers a list of sheets to choose from.

Columns — strictly in this order:

| Column | Data |
|---|---|
| A | cable tag |
| B | diameter |
| C | segment (merged cells carry down) |
| D | quantity |
| F | system |
| G | fill % |
| H | tray height |
| I | tray width |

## How to use

1. Open a drafting view.
2. Press the button and pick the file.
3. Tick the segments you need — they're built stacked top to bottom from one point, not overlapping.
4. Choose a mode: **«Section and table»**, **«Section only»** or **«Table only»**. To put the section and the table on different drafting views, run the button twice with different modes.
5. If a section is built, answer whether to show cable tags on the circles.
6. Pick the insertion point of the first segment in the view; the rest go below it.

## How cables are laid out

Cables are laid from the largest diameter to the smallest: each at the lowest point where it touches the bottom, the walls or cables already laid. All systems mixed together, tightly, left to right. Cables that didn't fit the tray height aren't silently dropped — a separate warning lists them.

The tray outline and cables are drawn at real size (scaled by the view), while the table and labels are «paper» size taking the view scale into account, so they read the same at any scale. Tags inside each segment are numbered from 1.
