[Русский](../families-panel.md) | **English**

# Families panel (ToolsFamilies) — families from a catalog

Two buttons work with one **.rfa catalog folder** (for example, a network folder with the department's family library). The catalog path is shared by both buttons and remembered; to change it — **Shift+click** on either of them.

Every family loaded from the catalog gets a hidden mark with the catalog file's date. «Update/check families» uses it to tell whether the family in the model is out of date.

## Load families

Loads the chosen families (or individual types) from the catalog into the model.

1. Press the button (the first time — point it to the catalog folder).
2. Choose catalog sections — folders with .rfa, several allowed. «Cancel» — all sections.
3. Tick the files you need in the table. Columns: file name, folder, whether it's already in the model, file date; click a header to sort.
   - **green** — new families;
   - **grey** — already loaded: they will be reloaded.
4. Checkboxes at the bottom:
   - **«Choose types»** — the button opens each ticked .rfa, reads its types and lets you tick the ones you need; only they are loaded. Without it the whole family is loaded;
   - **«Overwrite type parameter values»** — only affects families already in the model (the same as the choice in Revit's own reload dialog).
5. Confirm loading.

## Update/check families

One window to see which of the model's families have fallen behind the catalog, and to update them.

1. Press the button and choose categories (several allowed).
2. The table shows, for each model family, its category, **status**, the date in the model, the date of the similar catalog file and how similar the name is:
   - **green** «up to date»;
   - **orange** «no mark» — the family wasn't loaded through these buttons, there's no date to compare;
   - **red** «outdated» — the catalog file is newer.
3. If the wrong catalog file was matched — double-click the row or press «File…» and pick the right file by hand. Even a file with a different name updates exactly this family instead of creating a new one.
4. Tick the families to update and set the checkboxes:
   - **«Overwrite type parameter values»** — like «Overwrite the existing version and its parameter values» in Revit's own dialog;
   - **«Rename»** — give the family the catalog file's name.
5. Confirm. Just closing the window changes nothing.

Each family reload is a separate undo step (**Ctrl+Z**).
