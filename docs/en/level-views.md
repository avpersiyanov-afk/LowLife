[Русский](../level-views.md) | **English**

# Views by level

The «Views by level» button (**Tools** panel) creates plans on all (or chosen) model levels from the ticked view templates — for example «SCS floor plan», «Fire alarm floor plan» for every floor in one run.

## Window

- **View templates** — the list of the project's plan templates (floor, ceiling, structural). Tick the ones you need. For each, enter the **view groups and purposes** — one per line; a separate view is created for each (for example «СКС» and «СКС_Трассы» → two plans per level with one template).
- **Name mask** — what the view name is made of:

  | Placeholder | Gives |
  |---|---|
  | `{Уровень}` (Level) | the level name |
  | `{Группа вида и назначение}` (View group and purpose) | a line from the template's group list |
  | `{Шаблон}` (Template) | the view template name |
  | `{Отметка}` (Elevation) | the level elevation, for example «+3.300» |
  | `{Этаж}`, `{Корпус}`, `{Комментарий}` (Floor, Building, Comment) | parts of the level name by the level name pattern (from the «View range» button settings) |

  The placeholders are typed in Russian, as in the table. The default is `{Группа вида и назначение}_{Корпус}_{Этаж}_{Отметка}`. At the bottom of the window — a preview of the names on the first level; the button warns if different views get the same name.
- **«Choose levels for each template»** — after launch a list of levels opens for each template: which levels to create its views for (the choice is remembered). Without the tick — all levels.
- **«Align view range»** (on by default) — the range of the new views is set the way the «View range» button does it. If its setting isn't filled in yet, its window opens before creating. Ceiling plans and views whose range is controlled by the template keep their range — the report explains it.
- **«Save»** — save the mask, groups and elevations without creating views.
- **«Export/Import settings…»** — move settings between projects and computers.

## What it does

For each ticked template, a plan of the right kind (floor, ceiling or structural — by the template's kind) is created on every level with that template and a name by the mask. Visibility and links are set by the template itself.

- A view with the same name **on the same level** isn't created again — the template is assigned to it.
- A name taken by a view of **another** level, or already given out in this run, is an error in the report and the view isn't created. Fix the mask (for example, add `{Отметка}`).

Everything in one transaction — **Ctrl+Z** undoes it.
