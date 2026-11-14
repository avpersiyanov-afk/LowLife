**English** | [Русский](../ar-task-annotations.md)

# AR task annotations

Available on the Tools panel under General. Places a text note with a leader
for every visible instance of a configured family type in the current model
on the active plan.

1. **Shift-click** the button and check the required family types. The searchable
   list includes loaded types with no placed instances.
2. Continue to text and spacing. Choose a Revit text type and enter the task text
   for each selected family type. Blank text disables creation and updates for
   that type. Enter `\n` for a line break.
3. Save, open the target plan and click the button normally.

The first run opens settings automatically. Settings are stored in
`%APPDATA%\pyRevit\LowLifeARTaskAnnotations_settings.json`; standard LowLife
settings export/import is available. Types are matched by category, family name
and type name, so separate types of one family can use different text.

Uses the equipment tag layout: stacks/columns, symbol bounds and nearby equipment,
tags and text as obstacles. Offset, gap, shoulder length and cluster distance are
paper millimetres scaled to the plan. Conflicts that cannot be avoided are reported.

Rerunning updates the tool's existing notes, text style and leader positions.
Pinned notes are skipped. Notes for disabled types are retained. Source identity
is stored on each note; manually copied duplicate notes cause an explicit error
instead of creating further duplicates. User notes and tags remain obstacles.

Notes are ordinary Revit text: rerun after moving a family to update the leader.
Linked elements are not included. One Undo reverts the operation; errors roll back
text and source metadata together.

Automated tests cover the adapter and shared layout outside Revit. Native text
creation, leader appearance and settings windows were not tested in Revit in this session.
