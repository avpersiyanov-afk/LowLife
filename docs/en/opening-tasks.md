[Русский](../opening-tasks.md) | **English**

# Opening tasks: VIS → KR

The “Opening tasks” panel in the General theme has two commands: VIS tasks and
KR tasks. No server or SQL is used. Save/synchronize models and reload links to
exchange releases and decisions.

## Separate AR exchange

The VIS action is “Issue VIS-KR tasks”; the KR action is “Accept KR tasks”.
For architecture, use “Drafts for AR”, select the AR model link, then select
the new drafts and choose “Issue VIS-AR tasks”. Save VIS and reload its link
in AR. Open the separate AR interface, configure the same project code and
use “Accept AR tasks”. AR also supports showing hosts, merging compatible
tasks, comments and withdrawal processing. Save AR, reload its link in VIS
and use “Confirm AR results”.

The VIS table has a recipient column and filter. AR has independent settings,
receipts and decision history. Only released tasks addressed to the current
recipient model are received. Legacy drafts default to KR; create new AR
drafts rather than readdressing an issued KR task. Direct rectangular wall/floor
openings are supported; automatic finish cutting from linked KR openings is
a separate workflow and is not implemented by this action.

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

## Role manifest

`opening_tasks_manifest.py` defines ribbon entry points and each role's allowed actions. VIS: place, issue, withdraw, confirm result, box 3D, views/register. KR: show host, accept, merge, comment, process withdrawal, structural view, slab plans, wall sections. Refresh/settings are common. Dispatch and execution both reject cross-role actions. Unknown roles do not fall back to KR. VIS labels now read Issue tasks and Confirm result. Close old windows and restart Revit after updating persistent interfaces.

## Exchange between separate models

VIS saves/synchronizes after issue. KR/AR reloads the VIS link, reviews tasks
and saves its own model. VIS then reloads the recipient link in Revit and
clicks “Refresh exchange”. The button reads loaded links; it does not reload
files from disk. The VIS table shows recipient response, reply revision,
comment and next action. Filter responses or select “Need attention” to find
outdated replies, comments, missing/modified openings and pending withdrawals.
An unavailable model is not treated as a deleted opening. Responses apply to
released revisions. Re-run placement after changing routes, review draft changes
and reissue. Confirm matching results after review. No separate database or
JSON file transfer is required.

## Google journal

Release, reissue, withdrawal, KR/AR decisions and VIS confirmation automatically
enqueue a snapshot after the Revit transaction commits. Each project code gets
a separate object tab with current status and full event history. Cancelled
operations and unchanged registries do not enqueue anything. The durable local
queue silently retries every minute while Revit is running, including with
closed task windows. It resumes automatically at startup/reload or document open.
Delivery failures show no notifications or status messages.
A failed earlier revision blocks later revisions of that model; other models
can still publish. Tokens never enter the queue.

Every user can open Sheet connection and enter the URL and department token once
in their Windows profile for all their models. No credentials are saved in RVT. Each token is scoped
to a role for a group, works across projects and models and is protected with Windows DPAPI. “Open spreadsheet”
is available to engineers. Google link sharing can grant Viewer access; a tab
link grants access to the entire spreadsheet, not just one project. Separate
Google files are needed when project visibility must be isolated.

See [deployment guide and Apps Script](../opening-journal/README.md).
The Google deployment still requires setup by its owner. Saving/synchronizing
RVT files and reloading links remain required even after automatic publication.

The “ГИП” tab summarizes each project, issuing discipline and KR/AR recipient:
release/review/comment dates, decision authors, current counts and completion.
Completion requires accepted current revisions, verified openings and processed
withdrawals. A new revision reopens review; a fully withdrawn group is not
reported as accepted. Publication dates show how current each side's data is.

Project codes come from Project Information through the tool's own
“Project code parameter” setting. Blank means the standard Project Number.
Notes settings, credentials and cache are not used.
When a new object's parts are first requested, Google creates НЧ/ПЧ directory
rows with the project code from the model. Only building/section numbers
need to be filled in.

The Google “Части объектов” catalog lists project, НЧ/ПЧ, building/section
number and enabled flag. Revit asynchronously loads only that project's choices
and remembers the selection per model and role. Placement/release require a
catalog selection; issued part assignments are immutable. Legacy assignments
create a new revision. Separate parts cannot be merged. Tables and the GIP
summary expose the part so НЧ/ПЧ and buildings/sections can be controlled separately.

## Box level from the intersected host

Floor openings use the pierced slab's level. Wall openings cast a vertical
downward ray against actual floor solids in the same selected KR or AR link;
other links and VIS geometry are excluded. A ray through a hole continues to
the next physical hit. Linked levels map to VIS by name and transformed project
elevation (1 mm tolerance), never by the nearest lower level. Missing/ambiguous
levels or hits and tilted links are reported as skipped boxes.

Repeated placement checks existing instance levels and changes them while
preserving location and ID. An unsupported family change is rolled back.
Resolution provenance is stored in box/task JSON and shown in the table;
a corrected issued level creates a new revision on reissue. The same rules
apply to the standalone tray box tool.


Group credentials replace per-model token issuance. Configure each Windows profile
once per role across all projects; model IDs continue to isolate publication streams and task
ownership in the journal. Project/model-bound legacy credentials remain supported with their original restrictions.
Release/review/withdrawal events store Revit and Windows usernames at action time;
queued retries retain the original identity. Publications show group and sender
separately. The department is obtained automatically from the token.


The Google token menu asks for a department once: ОВиК, ВК, ЭОМ, СС, АК, КР or АР.
The installer asks only for the Apps Script URL and department token.
Department and internal VIS/KR/AR mode are discovered automatically.
Initial Google setup creates all shared journal tabs with headers before any release;
project tabs appear after the first project publication. Repeat setup or rebuild
to repair missing views without removing publications or the parts catalog.
The saved engineering discipline fills new task records; older release records
remain unchanged until explicitly reissued. PowerShell uses UTF-8 with BOM.
