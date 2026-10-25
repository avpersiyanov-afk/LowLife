[Русский](../loi-panel.md) | **English**

# LOI panel — filling and checking parameters

Four buttons of the **LOI** panel («LOI filling»): fill element parameters by context and check that everything is filled in. Model changes are undone with **Ctrl+Z**.

## Fill LOI

Copies parameter values from elements of the **«Masses»** category to every checked element that physically lies inside the mass solid (building, section, floor… — whatever is set on the «Masses»). The check is exact, by the solid: for point elements — the point falls inside, for linear ones (trays, pipes) — the line intersects the solid.

- An element in exactly one mass is filled in right away.
- An element in several masses at once (usually a linear one on a border) is **split** along the mass border by default, and each piece gets the values of its mass. Whatever couldn't be split goes to a conflict table where a source mass is chosen for each.

Settings (Shift+click):

1. **Which models to search for «Masses»** — the current file and/or specific loaded links (masses usually live in a separate architectural model).
2. **Parameters to copy** — one per line. The name must be the same on the «Mass» and on the target element.
3. **Which elements to check** — all in the active view, all in the document or only chosen family types.
4. **An element in several masses at once** — split it along the border or send it straight to the conflict table.

The [«SS1-8Mile»](ss1.md) button uses the same settings to fill LOI on the equipment it places.

## Fill floor

Writes a value by the **element's level** into one parameter (for example «Floor») — the level as given in the instance properties («Level»), not by the position on the plan. Goes through all elements of the document, regardless of the active view.

Settings (Shift+click):

- **The «Floor» parameter** — where to write. It can be created and bound to the right categories with the «Shared parameters» button (system «Fill floor»; the categories are chosen by hand, see [parameters.md](parameters.md)).
- **A «Level / Value» table** — all levels of the document; for each, enter what to write to its elements («1», «Этаж 1», «-1»…). An empty value — elements of that level are skipped.

Elements without a level are skipped. The report says how much was written and where writing failed (the element has no such parameter or it is read-only).

## LOI check

Checks whether elements of the chosen categories have the required parameters filled in (the value is looked up on the instance, then on the type), and builds:

- a schedule **«LOI проверка — <category>»** per category: «Type», «Family», «Floor» columns and the checked parameters, sorted floor → family → type. Running it again rebuilds the same schedule;
- **a 3D view «LOI проверка — незаполненные»** showing only elements with empty parameters (after the check the button asks whether to open it);
- **a report**: how many elements are missing each parameter and a list of them (clickable IDs).

Two modes:

- **Your own list** — in the settings, choose categories, then parameters line by line (as in the LOI requirements), then for each line the parameter name in the model (empty — the line itself).
- **By the «LOI requirements» appendix** — load the appendix in the settings (an Excel table saved as «XML Spreadsheet 2003») and choose sections. At launch the button asks for the stage: stage · design/working documentation · sub-stage (Б-1…, ПЭ-1…). Categories and parameters come from the appendix; each element is checked only for the parameters of its class (by the classifier code in the parameter named in the code column header) that are required at that sub-stage.

**The parameter for the «Floor» column** — in the settings; empty — the «Fill floor» button's parameter, and if that isn't set either — the element's level.

A parameter gets into the schedule only if it is a shared or project parameter bound to the category; otherwise it is shown in the report with the reason.

## Update level name

Assigns a reference level to selected family instances that have none and no host (for example, placed without a level). The level is chosen from a list or by height: the nearest level not above the element.

First the button simply tries to set the «Level» parameter — the element stays in place. If Revit won't let it change, after confirmation the instance is re-created with the level in the same place: the type, rotation/mirroring, instance parameters, workset and electrical circuits carry over, but **the element ID changes and the old element's tags are deleted**.

Elements with a level, hosted, nested and in groups are skipped. Afterwards the resulting elements are selected.
