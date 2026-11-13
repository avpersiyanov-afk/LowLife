[Русский](../model-filter.md) | **English**

# Worksets and links filter

The button is on the Tools panel under the General theme. Restart Revit after first installation
so the dockable panel can be registered at extension startup.

## View visibility

The two sections list host user worksets and Revit link instances. Checked means shown,
unchecked means hidden, and a grey square indicates a mixed group. Worksets use view-local
visibility overrides; links use individual instance hiding. Closed worksets, unloaded links
and template-controlled worksets are disabled, with an explanation in the row tooltip.
Links remain available in projects without worksharing.

Search matches groups and full names, including the wrong keyboard layout. Ctrl+click adds
groups to the selection; Shift+click selects a range. Settings (also Shift+click on the ribbon
button) provides separate masks: `*` matches text, `?` a character and `{part}` captures a
grouping part. For example, `{building}_*` groups names by building.

Presets store masks and visibility per model. Identically named workset/link groups remain
independent. Apply to views copies the current configuration to selected views. Categories,
templates and crop boundaries may further restrict visibility. The panel does not open
worksets or reload linked documents.

## Workset management

Manage worksets opens the rule editor for the current workshared project. These operations
affect the whole project, unlike the visibility checkboxes.

1. Add rules manually, select existing worksets with From host model, or import workset names
   from loaded linked models with From links.
2. Choose an action and source/target:
   - **Create** creates a missing user workset; existing worksets are left as they are.
   - **Rename** renames a workset. An occupied target name is rejected; use a transfer to merge.
   - **Transfer elements** moves instances to the target workset, creating it when missing.
     The source workset remains.
3. Preview shows specific names and element counts. Apply to project executes the entire plan
   in one transaction; assignment or commit errors roll back the transaction.

Rules run from top to bottom. Sources use the same full-name masks. In targets, `{1}` is
the full source name and `{2}` is the first captured part. For example, `Old_{part}` → `New_{2}`.
Closed worksets, invalid names, conflicts and read-only elements block application with an
explanation. Model changes after preview require a fresh preview. Search hides rule rows
without excluding them from the plan.

Save rules stores configuration without modifying the model. Export/import settings transfers
JSON rules between projects. The file contains `workset_rules`, a list of objects with `action`
(`create`, `rename`, `map`), `source` and `target`. Button data is stored in
`%APPDATA%\pyRevit\LowLifeModelFilter_settings.json`.

## Manual Revit checks

- Compare checkboxes with Visibility/Graphics on plans and 3D, including global workset visibility.
- Check closed worksets, unloaded links and template-controlled worksets.
- Check matching names across sections, masks, search, Ctrl/Shift, presets and copying to views.
- Switch views/documents and undo; verify refresh and that another view cannot be changed by a queued click.
- Create/rename a workset and transfer elements in a test model; check Undo.
- Test name conflicts, closed worksets and inaccessible elements: no partial changes.
- Test chained A → B → C transfers, creation from link worksets and JSON import/export.

Automated tests exercise planning, current states and rollback using API substitutes.
They do not exercise WPF, pane registration or a real Revit model.
