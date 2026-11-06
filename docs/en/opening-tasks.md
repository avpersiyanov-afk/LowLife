[Русский](../opening-tasks.md) | **English**

# Opening tasks: VIS → KR

The “Opening tasks” panel in the General theme has two commands: VIS tasks and
KR tasks. No server or SQL is used. Save/synchronize models and reload links to
exchange releases and decisions.

## Setup

Shift-click each command. Set the same project code, and a writable text instance
parameter for box JSON (required for VIS, optional for KR). VIS also sets its discipline, box family, size parameters,
host filter parameter, EIR clearance and optional ZNP increase. Names are project
settings, never hardcoded. These settings are separate from the original tray tool.
VIS must link KR; KR must link VIS. Tasks target the actual model and host identity.
Do not duplicate a model with its identifiers for another project.

## VIS

- Place/update boxes on selected straight trays, ducts, pipes and conduits.
  Round/oval profiles use a rectangular envelope. Duct/pipe insulation is included.
  As in the tray tool, wall crossings must be horizontal and floor crossings vertical.
  Fittings, flexible/curved runs and rolled rectangular profiles are reported for review.
- Select the KR link instance, box type and workset. EIR clearance is per side.
  ZNP adds to both opening dimensions; automatic values use the larger dimension
  including clearance: ≤300 mm → 50; ≤600 → 100; otherwise 150 mm.
- Updating own drafts preserves their GUID by source/host/link identity.
- Select boxes and explicitly issue them. Preview revisions, movement/size changes,
  host-local centers and dimensions. Identical releases are idempotent.
- Working edits never change an issued snapshot. Save/sync and reload links to deliver it.
- Explicitly withdraw tasks, including tasks whose box was physically deleted.
  Missing selections or unloaded links never automatically withdraw tasks.
- Reload KR and confirm its results. Only current accepted revisions whose actual
  opening matches the stored KR decision can be confirmed.

## KR

The inbox reads only official immutable release snapshots for the current project
and KR model. States include new, changed, accepted, rejected, withdrawn,
missing_opening and opening_modified. Select a task to show its host.

Accept separately creates native rectangular Revit wall/floor openings. Merge and
accept creates a bounding rectangle only for the same host and orientation, with
size preview and explicit confirmation. Existing openings are replaced atomically
only on confirmation. Reaccepting an unchanged group does not duplicate it.
Updating a merged opening requires all its tasks and the merge action; splitting
an existing group is not automated.

Comments/rejections are revision-specific. Implemented openings cannot be silently
rejected. Withdrawal removal requires confirmation and all tasks of a merged opening
to be selected and withdrawn. Native opening JSON is stored in Extensible Storage
and the registry, and also in the configured parameter if bound to its category.

No extra clearance is added by KR. Straight walls and rectangular wall/floor openings
are supported. Beams, columns, family cutting, arbitrary profiles and AR finish
cutting are outside these two commands.

## Data and validation

Box JSON stores task GUID, owner, source, target, revision, UTC issue time, author
and geometry in target-model local millimeters. DataStorage retains issue snapshots,
withdrawals, KR decisions and VIS confirmations, including deleted boxes.
Link transforms are applied at issue time, not again in KR. Tilted/inverted links
are rejected. Worksharing requires ownership of the registry element. Use normal
model backups; JSON is not protected against deliberate manual edits.

Protocol tests run without Revit; connector adapter tests use a substitute API.
Native openings, UI and worksharing still require a Revit 2024 pilot on model copies.

Actions are available inside role interfaces: VIS boxes, Issue to KR, Withdraw tasks, Confirm KR, KR inbox, Accept separately, Merge openings, KR comments, Process withdrawal.

The ribbon now has VIS and KR modeless interfaces only. Search, status filters and multi-selection operate on a cached list. Actions use ExternalEvent and verify the active document; KR revisions are re-read before applying selected tasks. Refresh reloads current data. Settings are available inside each window and through Shift+click.

## KR slab plans and wall sections

The KR interface provides Slab plans for every level, with view ranges covering
slabs containing accepted openings. Wall sections creates one full-wall section
for each straight wall of the selected tasks, or all walls with accepted project
openings when no rows are selected. These are native Revit sections, not Elevation
views. Existing managed views are updated by UniqueId. If a wall rotates or moves
behind the old section plane, delete the outdated section and run again. Accepted
openings receive blue overrides; manually modified openings receive orange overrides,
to the extent supported by native Opening graphics. Revit runtime validation is required.

## Table and filters

Role windows now use a sortable table with task number, status, discipline, source model, host level, host kind, issue, revision, date and sizes. Status/discipline/level/host/issue filters combine with search and the attention-only checkbox. Reset restores the full list. Select visible selects only currently filtered rows. Filtering never changes releases or withdraws hidden tasks. Double-click opens VIS box preview or the KR host. The detail card compares issued/previously accepted and current dimensions, VIS displacement and KR comments. Newly issued tasks have stable model-local numbers; legacy releases retain their short-GUID alias until a changed reissue.

## Selection, merge preview and annotations

Placement now uses an ISelectionFilter for supported straight trays, ducts, pipes and conduits with permitted slope and profile. Actual host intersections are computed after selection; eligibility does not guarantee a crossing. Merge shows blue source rectangles and an orange combined envelope, in wall X/Z or floor X/Y projection, before any model change.

Translation-only updates attempt to retain the existing Opening and its IDs in a subtransaction, checking the resulting geometry and annotations. Replacement checks tagged elements, dimension references, dependencies and a rolled-back trial deletion. Replacement affecting annotations is blocked for manual review. Automatic rebuilding of dimension references after contour changes is not provided. Protocol scenarios and substitute-API annotation checks do not replace a real Revit pilot.

## Preview fallback and valid names

VIS 3D preview no longer requires a prepared KR structural view. It uses that view when present, otherwise ByHostView with category restrictions, transparency and section box. In fallback mode, linked elements in the permitted box/source categories may also appear; a prepared structural view remains optional for strict linked category control. Generated view/schedule/filter names are sanitized, including the prohibited pipe character, before collision checks.
