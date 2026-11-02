[Русский](../schedules-panel.md) | **English**

# Schedules panel (ToolsSchedules) — schedules and Excel

The «Model → JSON» and «JSON → model» buttons are described separately — [json-snapshot.md](json-snapshot.md). This page is about working with schedules.

## Export to Excel

Exports a schedule to .xlsx so you can edit the values in Excel. Neither Excel nor extra libraries are needed.

1. Open the schedule (if the active view isn't a schedule, the button asks which one to export).
2. Press the button and choose where to save the file.

No ID field is required in the Revit schedule: export automatically adds **«Revit ID»** as the first column. It links each row to a model element — **don't change it**. Key schedules are also supported. Parameter values follow in schedule columns. Type parameter headers have a **`[Type] `** prefix; keep it when editing.

Groups are expanded into individual elements. Editing a type parameter affects every instance of that type, including instances outside the schedule. Conflicting values for the same type parameter in different Excel rows are skipped and reported.

Manual tables stored in the schedule header (including LowLife room explications) also support export and import. Their cells use **`[Cell] 1`**, **`[Cell] 2`**, etc.; «Revit ID» stores a row reference. Keep these headers and references. Merged cells export their top-left value. Only existing cell text is updated; inserting/deleting rows, merges and Excel formatting are not imported. If the structure or original row text changed in Revit after export, the row is skipped with an error; export again.

## Import from Excel

Loads edits from a .xlsx (exported with «Export to Excel») back into the model.

1. Press the button and pick the file.
2. The button finds elements by the «Revit ID» column and parameters by column headers, and writes only the values that changed.

Rules:

- **empty cells are skipped** — they don't erase the value in the model;
- writable instance and type parameters are written; calculated fields, read-only parameters, linked elements and element references are not written;
- import requires the automatically added «Revit ID» column; arbitrary tables without identifiers are not matched by row position;
- numbers with units are read in the project's current units — as they appear in Excel.

Everything is written in one transaction (one **Ctrl+Z** undoes it), with a report at the end: how many values were changed, what was skipped and why (read-only, parameter or element not found, write errors).

## Split schedule

Splits a schedule on a sheet into segments of a given height — the same as dragging the schedule split grip, but straight into the number of parts you need.

1. Open the sheet and click the schedule on it (the instance on the sheet, not in the Project Browser).
2. Press the button and enter the height of one segment on the sheet, in mm (for example 180).
3. The button shows how many segments you'll get, the header height and the whole table height, and asks for confirmation.

The first segments get the given height (as far as a whole number of rows allows), the last one gets the rest. The header repeats on every segment. If the schedule is already split, the button offers to join it and split again. The button doesn't merge the schedule back into one part — use Revit's own tools for that.
