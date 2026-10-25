[Русский](../cable-catalog.md) | **English**

# Cable catalog (Cables panel, ToolsCables)

The **cable catalog** is the key schedule of the «Electrical Circuits» category whose rows the circuit «Wire» parameter refers to. Each row is one cable (a key name + its own parameters: type, name, cross-section…). LowLife circuit buttons (SCS, ACS, fire alarm, voice alarm, fire automation, «Circuit (general)», «Place relay, control modules») let you pick a catalog row in their settings and write it to the circuit's «Wire» when building.

## How the buttons find the catalog

1. The key schedules of the «Electrical Circuits» category are taken.
2. If some of them have «Wire» as the key parameter — only those.
3. If there are several and the button's settings define a **cable catalog row marker** (a parameter that only rows of the right schedule have), the list is narrowed to the schedules with that parameter.

The circuit parameter the cable is written to is the key parameter of the schedule found; there's no need to specify it separately.

## Buttons

- **Cable catalog** — a report: all key schedules of the project (which are recognised as the cable catalog) and, for the catalog, a table of rows: key name, ID, schedule columns and the **number of circuits** where the row is already set. Doesn't change the model.
- **Edit catalog** — a table window: edit values and add new cables (the empty row at the bottom or «Copy row» — a copy of the selected one as a starting point). Everything is written in one transaction on «Save». Rows can't be deleted — circuits may refer to them. Calculated and read-only columns aren't editable. If there are several catalogs, the button asks which one to open.
- **Export catalog** — to .xlsx (no Excel needed): a «Key name» column and all schedule columns.
- **Import catalog** — from a .xlsx of the same format (the first row is headers, the «Key name» column is required). Rows are matched **by key name**: found ones are updated, new ones added, the project's other rows are left alone. Columns that aren't in the project's schedule are skipped.

## Moving the catalog to another project

1. In the source project — «Export catalog».
2. In the new project, create an «Electrical Circuits» key schedule with the same fields (it can be empty) and «Wire» as the key parameter.
3. «Import catalog» — the rows are added by key name.
