[Русский](../rename-export-files.md) | **English**

# Rename export (RenameExportFiles)

The `ToolsExport.panel/RenameExportFiles` button («Rename export»). The logic is in `lib/lowlife/export_rename.py`; the button script is thin. Registered under the `Service` theme of the `_Themes.panel` switcher.

The automatic mode (`export_watcher.py`, described below) is **off by default** (`watch_explorer: false`, a commit made after complaints about side effects — the Bullzip PDF Printer «Create File» window appearing during pauses in batch export turned out to be unrelated to the hook, but the user still preferred running it by hand). Only the button works: press it by hand right after a ModPlus export. To turn the automatic mode back on — Shift+click → «Notice when the export finishes by itself…» → Yes.

## Why

Two sheets have to go under **one** number but with different names. Revit and ModPlus build the export file name from «sheet number + sheet name», so the same number causes a file name clash. The workaround: give the sheets different numbers — for example `0000` and `000` — and after export turn `0000` into `000`. Then on disk the two files differ only by the sheet name.

## What one run does

`run_after_export`:

1. **Asks for the export folder.** If a folder has been used before (`last_folder` in the settings), it shows it in a dialog with «Yes, this folder» / «Choose another…» / «Cancel»; «Yes» is the default button, confirmed with Enter. Otherwise — `forms.pick_folder`. The folder ModPlus put the files in can't be determined programmatically (the plugin isn't available in the development environment, and its config isn't read), so this is semi-automatic.
2. **Builds a plan** (`plan_renames`): in the folder (and subfolders, if enabled) it takes files with a matching extension (`.dwg`, `.pdf` by default) whose names contain `from_token` (`0000`), and replaces **every** occurrence in the name with `to_token` (`000`). If the target name is already taken by another file, the pair is marked `collision` and skipped.
3. **Shows the list** of «old → new» pairs (the first 12) and, if there are collisions, lists the skipped ones. Asks for confirmation (Yes/No).
4. **Renames** with `os.rename`. Nothing changes in the Revit model — no transaction is needed. At the end — a `forms.toast` with counters.

A normal click on the button = exactly this scenario, run by hand right after a ModPlus export.

## Auto-run

`export_watcher.install()` is called from `startup.py`, `hooks/doc-opened.py` and from the button scripts (`ensure_installed()` — in case the first two didn't run in this pyRevit build). Duplicates are cut off by a dictionary in `AppDomain.CurrentDomain` (shared by the whole Revit process — each pyRevit engine has its own `sys`, so a sys global didn't work: each engine subscribed to the static `ItemExecuted` and started its own poller, and the window asked twice). Plus an atomic lock file for starting the poller — `%APPDATA%\pyRevit\LowLifeExportRename_worker.lock`.

**The trigger is `Autodesk.Windows.ComponentManager.ItemExecuted`** (`clr.AddReference("AdWindows")`). A click on a ribbon button whose `Id`/`Text`/`Cookie` match `trigger_substrings` (by default `mprSheetExport` — ModPlus «Sheet export», id `CustomCtrl_%CustomCtrl_%ModPlus%Экспорт и Импорт%mprSheetExport`; `enabled` must be on) **immediately**, even before the modal export window opens, starts a background STA thread `_poll_and_rename`.

**The background thread `_poll_and_rename`** (off Revit's UI thread — on a network share this takes seconds, and on the UI thread it froze Revit):

- if neither `export_root` nor `last_folder` is set (the first run on the machine), it **immediately** asks for the export root folder (`FolderBrowserDialog`) and remembers it as `export_root`; cancel — exit (it doesn't hang for 15 min, the lock is released);
- every `POLL_INTERVAL` (2 s) it looks at the subfolders of `export_root` and/or the folders next to `last_folder` (`_bases_to_watch`) for a **new** subfolder created after the click (`_newest_subdir_since`, only `listdir`+`stat`);
- once found, it waits for a sign that the export has finished:
  - **the ModPlus window closed.** `_modplus_window_open` lists the titles of the Revit process's visible top-level windows (Win32 through `ctypes`, from the background thread — not from the UI thread); while a window with one of `MODPLUS_WINDOW_SUBSTRINGS` (`modplus`/`экспорт`) in its title is visible, renaming is NOT started, even if the folder temporarily stops changing (between sheets of a big batch). Once the window was seen and has disappeared → `STABLE_CYCLES_AFTER_WINDOW` (2) quiet polls are enough;
  - **fallback** (the window wasn't caught — `ctypes` failed / a different name): `_folder_sig` (mtime + the number of matching and of all files in the folder and its first-level subfolders) doesn't change for `STABLE_CYCLES` (5) polls in a row, there are already files in the folder (any>0) and at least `MIN_SETTLE` (10 s) has passed;
- then `_do_rename`: `plan_renames` →
  - something to rename → a WinForms yes/no `MessageBox` → `apply_renames` (re-reading the plan) → a final `MessageBox`;
  - only collisions (target names taken) → a window with an explanation;
  - no files with `from_token` at all → a «nothing to rename» window (only if `notify_nothing`, off by default) or quietly into the log.
  `MessageBox`/`FolderBrowserDialog` work from the background thread and don't block Revit;
- if no new folder appears within `ARM_WINDOW` (15 min), it asks for the folder (`FolderBrowserDialog`).

The search runs **in parallel** with the export itself, so the renaming window appears a few seconds after ModPlus has finished writing the files.

The `Idling` subscription is left only to clear a stuck flag (`WORKER_STUCK_AFTER` = 10 min); it doesn't touch the renaming logic.

Limitations:

- if the ModPlus window wasn't caught by its title AND ModPlus pauses between files longer than `STABLE_CYCLES`×`POLL` (10 s), the fallback may decide too early that the export has finished. `MODPLUS_WINDOW_SUBSTRINGS` is adjusted in the code to the real window title (see `poll: жду… окно_ModPlus=` in the log);
- it isn't checked during development (no Revit) — only a simulation of the pure logic.

Turning it off: Shift+click on the button → «Notice when the export finishes by itself…: no» (the `watch_explorer` key). In an emergency: an empty file `%APPDATA%\pyRevit\LowLifeExportRename_OFF` — `install` then does nothing (a Revit restart is needed to drop subscriptions already in place).

## Settings (Shift+click)

`EXEC_PARAMS.config_mode` → `export_rename.configure()`: the automatic mode (`watch_explorer`), arming on click (`enabled`), substrings for recognising the export button (`trigger_substrings`), `from_token` / `to_token`, extensions, **the ModPlus export root (`export_root`)**, walking subfolders, whether to show a window for an empty export (`notify_nothing`). Kept as plain JSON in `%APPDATA%\pyRevit\LowLifeExportRename_settings.json` (the same approach as `scs_settings.py`, not `pyrevit.script.get_config()`).

## The «Catch command id» diagnostic button

`Tools.panel/CaptureExportCommand`, `lib/lowlife/command_probe.py`. A normal click subscribes to `ComponentManager.ItemExecuted` and writes the `Id`/`Text`/`Cookie` of every pressed ribbon button to `%APPDATA%\pyRevit\LowLifeExportRename_commands.log` after a marker line; Shift+click shows what was caught after the last marker. That's how the id of «Sheet export» was obtained (the user's Revit journals aren't written). It is kept in the extension in case another button needs to be identified.

## Why not a pyRevit command hook

The first attempt — `hooks/command-after-exec.py` **without** a `[command_id]` in the name (hoping it fires after any command) — **this pyRevit build doesn't register such a hook**: `Failed registering hook script command-after-exec.py | Адресат вызова создал исключение` (the call target threw an exception). The form with the exact id in the name — `hooks/command-after-exec[<id>].py` — might have worked, but the id of «Sheet export» contains `%`, spaces and Cyrillic (`CustomCtrl_%CustomCtrl_%ModPlus%Экспорт и Импорт%mprSheetExport`), and such a file name is a risk. `ItemExecuted` from `startup.py` (see above) is simpler and has already been checked with the diagnostic button.
