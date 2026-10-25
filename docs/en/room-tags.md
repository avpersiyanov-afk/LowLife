[Русский](../room-tags.md) | **English**

# Room tags from a link (RoomTags)

The `ToolsRooms.panel/RoomTags` button («Room tags»). The rooms (Room) live in the linked architectural model, but the tags are needed in our document on the active plan. The logic is in `lib/lowlife/room_tags.py`; the button script is thin.

## What one run does

It works on the active view (`ViewPlan` — a floor/ceiling plan; on other views the button says so and exits). **Shift+click** (`EXEC_PARAMS.config_mode`) instead of the active view opens a multi-select list of all project plans (no templates) — tags are updated on all chosen plans at once in one transaction.

The user picks a tag type from a list — all loaded types of the «Room Tags» category (listed through `Family.GetFamilySymbolIds` so as not to lose types not placed yet — see the pitfalls in `CLAUDE.md`).

Then, in one transaction:

1. **Deletes tags that show «?».** Such a tag used to be repaired in place (moving the head, re-creating it with the head/shoulder carried over if needed) — the code was more complex, and in practice the difference from «just delete it and let step 3 place a new one with a correct head» didn't justify it. Simplified on 2026-09-17. A «?» tag is any of:
   - `_resolve_tag_room` returned `dead` — `TaggedRoomId` doesn't resolve to a Room (the link was removed from the project or the room disappeared in the link);
   - `RoomTag.IsOrphaned == True`;
   - `_room_ok(room)` == False — it isn't a Room (the id was taken by another element after the rooms were re-created), or the Room isn't placed (no `Location`) / isn't enclosed (`Area == 0`);
   - **the tag's anchor point has left its own room's boundaries** (`_tag_anchor_in_room`, any distance) — a known Revit pitfall: such a tag shows «?» and Revit doesn't recalculate it itself (for example, the architect trimmed the room outline). The anchor point is `tag.Location.Point` (`_tag_anchor`), **not** `TagHeadPosition`: with a leader, the head (the text bubble) and the anchor point diverge — the head can visually sit inside the room (the leader reaches back there) while the anchor itself is already outside. The check by `TagHeadPosition` stayed in the code until 2026-09-17 and that's exactly why it didn't catch such cases at all — a tag with a leader stayed «?» after any number of re-runs; it was caught with the `DiagnoseRoomTag` diagnostic button (see below) from a user's complaint with a screenshot. Earlier (before the first fix on 2026-09-17) there was also a 1000 mm tolerance from the room's bounding box (`_HEAD_ESCAPE_TOL_MM`) — removed too; the anchor's distance from the room doesn't matter.

   To examine a particular stuck tag without repairing it in place there is `ToolsRooms.panel/DiagnoseRoomTag` (doesn't change the model, only reads and prints `room_tags.diagnose_tag(doc, tag)` for the selected tag — the `TaggedRoomId` resolution, the room's area/point, the tag's own `Location.Point` and `TagHeadPosition`, local coordinates and the `IsPointInRoom` result).

   (There was also a heuristic «under the tag head in the link lies a different room than the one it refers to» — but it gave false positives on normal tags and moved them to a randomly found neighbouring room, so the original was left without a tag and got a second one from step 3. Removed on 2026-09-11 together with `_find_link_room_at`/`_recreate_stale_tag`, which aren't needed anywhere after giving up in-place repair.)

   The view's tags are collected by two collectors — a view-scoped `FilteredElementCollector(doc, view.Id)` **plus** a general collection filtered by `OwnerViewId == view.Id` (orphaned tags sometimes drop out of the view scope), de-duplicated by `Id`.

   `link_unloaded` (the link the tag looks at is currently unloaded) — **left alone**: there's no way to tell whether the reference is alive. Counted separately (`stats["link_unloaded"]`).
2. **Unifies the type** of all remaining (non-«?») room tags in the view to the chosen one (one tag style on the sheet).
3. **Adds missing tags** for link rooms that fall on the view's level (centre elevation within `_LEVEL_TOL_MM` = 1500 mm of the view level's elevation) and in the crop region (if it's on), but aren't tagged yet — including those freed in step 1.

Tags for link rooms are created the only way available — `doc.Create.NewRoomTag(LinkElementId(link.Id, room.Id), UV, view.Id)` (the API has no `IndependentTag.Create` equivalent for rooms).

## Working around the underlay pitfall

With an underlay on, Revit refuses to place a room tag («point is not in a room») or puts it on a room from the underlay. Before working, the button turns off the active view's underlay (`SetUnderlayBaseLevel(InvalidElementId)`) and in a `finally` block puts back the previous underlay base/top levels.

## Resilience to errors on individual tags/rooms

Processing each tag (in step 1) and each link room (in step 3) is in its own `try/except`; a failure on one doesn't stop the pass over the rest and is counted in `stats["errors"]`. This matters because the whole pass over the view runs in one transaction — an unhandled exception from `run()` would roll the whole transaction back, undoing the fixes already made, and silently look like «the button didn't fix anything». The button script additionally wraps the call to `room_tags.run` in `try/except`: if something still escapes as an exception, it shows a `forms.alert` with the traceback instead of a silent rollback; if `errors` in the statistics is non-zero, it shows their number.

## Result

Otherwise the button works silently — there is no report window. `room_tags.run` still returns a statistics dict (`added`, `deleted`, `retyped`, `already`, `link_unloaded`, `orphan_unresolved`, `out_of_view`, `room_no_point`, `errors`) in case the summary is needed again.
