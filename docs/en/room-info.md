[Русский](../room-info.md) | **English**

# Write room number — mask and settings

One button on the `Tools` panel — `RoomInfo` («Write room number»), registered under the `General` theme of the `_Themes.panel` switcher. There is no separate settings button any more: **Shift+click** (`EXEC_PARAMS.config_mode`) shows a menu of two items — **«Settings»** and **«Run over views»** (see below). It is a general tool, not tied to a discipline (SCS/ACS/fire alarm/voice alarm).

## What it does (RoomInfo)

When pressed, it starts picking elements in the model right away (`PickObjects` with the `lowlife.selection.pick_model_elements` filter — a window doesn't catch link elements, all annotation by `CategoryType.Annotation`, grids, levels, lines, reference planes, generic models, rooms/areas/zones, crop regions and views). Nothing needs to be selected beforehand.

For each selected element it looks, in all loaded links, for the Room the element's point/centre falls into, and writes to the target parameter a string assembled **by a mask** from that Room's parameters.

The room search has two passes: first an exact hit of the point inside a Room (`Room.IsPointInRoom`), and if there is none — the nearest Room whose outline is no more than 90 mm from the point horizontally (the `ROOM_TOLERANCE_MM` constant in `lib/lowlife/room_info.py`). The second pass covers the case where a family is placed recessed into a wall and its point/centre ends up a couple of centimetres outside the room outline. In height, the second pass checks that the point falls into the Room's volume (± the tolerance), so as not to pick up a room on the neighbouring floor.

## Settings (Shift+click → «Settings»)

Three fields, saved to `%APPDATA%\pyRevit\LowLifeRoomInfo_settings.json`:

1. **Element parameter** (`room_param_name`) — where to write the result in the active model. A shared parameter in your families.
2. **Mask for parameters from the adjacent model** (`room_mask`) — a template of the link Room's parameter names separated by commas and/or parentheses. Other text in the mask stays as it is.

   | Mask | Result |
   |---|---|
   | `Имя (Номер)` | `Офис (212)` |
   | `Имя, Номер` | `Офис, 212` |
   | `Номер` | `212` |
   | `Имя (Номер)`, number empty | `Офис` |

   `Имя` / `Номер` (case-insensitive; also `Name` / `Number`) are aliases of the native `ROOM_NAME` / `ROOM_NUMBER`. Any other token is looked up as a Room parameter by name (`get_string_param`, then `LookupParameter` → `AsString`/`AsValueString`). A token without a value drops out together with orphaned parentheses and commas (`_cleanup_mask_result`).

The default mask is `Имя (Номер)` (the button's former format).

3. **View name prefixes** (`view_name_prefixes`) — comma-separated, for example `1, 2, 20, 30, 60`. Optional. Used only in «Run over views» mode (see below): the list shows views whose name starts with one of these values. Empty — show all views.

## Run over views (Shift+click → «Run over views»)

A bulk mode without picking elements by hand:

1. `views_with_name_prefix` collects graphical views (not templates, not sheets/legends/schedules/browsers) whose name starts with one of `view_name_prefixes` and shows them as a multi-select list.
2. For each chosen view, `collect_model_elements` takes all model elements visible in the view (`FilteredElementCollector` by view), with the same filter as manual picking (`is_pickable_model_element` — no annotation, grids, lines, generic models, rooms, etc.).
3. Elements from all chosen views are merged by `Id` (duplicates aren't processed twice), then the usual `apply_room_info` pass runs in one transaction. The summary is the same plus «Views / Elements processed».

### Migration from the old field

There used to be a `room_number_param_name` field instead of the mask (the name of the room number parameter in the link), and the format was fixed as `Имя (Номер)`. When settings are loaded, if `room_mask` hasn't been saved yet but `room_number_param_name` exists, the mask is assembled automatically as `Имя (<old value>)` — the output doesn't change. This is done in `load_saved_values` of all four settings modules (`room_info_settings`, `scs_settings`, `sot_settings`, `fire_alarm_settings`).

## Where else the mask is used

`room_info.find_room_value(doc, point, mask)` (the Room search + `render_room_mask`) replaced the former pair `find_room_info` + `format_room_value`. Besides the «Write room number» button it is called by:

- the **SCS / CCTV / fire alarm** riser diagrams — the `room_mask` field in their own settings (`scs_settings` / `sot_settings` / `fire_alarm_settings`), used if the room parameter on the device is still empty;
- **ACS «Access point rooms»** (`AssignSkudRooms` → `lowlife.skud_room_info`) — takes `room_param_name` and `room_mask` from the same «Write room number» settings.

`find_room_param_value` (one particular Room parameter value, no mask) is left as it is — fire alarm uses it for the branch zone marker.

## How to use

1. **Shift+click → «Settings»** — fill in the target parameter and the mask (once, or when the project/shared parameters file changes); optionally the view prefixes.
2. A normal run: press «Write room number» — the button asks you to pick elements itself (with a window and/or clicks, `Enter` — done). Or **Shift+click → «Run over views»** — pick views from the list, and the room is set on all elements in them.
3. The button carries the data over and shows a summary (written / not found / no point / no parameter / write error).

Elements without a parameter to write or without a room found aren't counted as errors — the button reports how many there are and carries on with the rest.
