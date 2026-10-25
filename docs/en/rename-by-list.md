[Русский](../rename-by-list.md) | **English**

# Rename by list (RenameByList)

A button on the **Export** panel (ToolsExport). Renames exported files by a «current name → new name» table. The Revit model doesn't change — the button only works with files on disk.

A typical case: one folder holds `DWG` and `PDF` subfolders with files named by sheet number (`001.dwg` and `001.pdf`), and every pair needs a new name — in one list, not file by file.

## How to use

1. Press the button and pick the folder that holds **two subfolders** with paired files. If there are more than two subfolders, tick the two you need.
2. A table opens: the first column has all file names from both subfolders (without extension); type the new name in the second. Empty and unchanged rows are skipped.
3. Press **OK**.

All files with that name (regardless of extension) in the whole selected folder and its subfolders are renamed — so both `001.dwg` and `001.pdf` at once.

- The button won't accept characters that aren't allowed in file names — it tells you which rows have them.
- If a file with the new name already exists, that file is skipped — the final message says how many there were.
