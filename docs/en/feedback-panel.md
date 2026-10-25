[Русский](../feedback-panel.md) | **English**

# Feedback — the «Feedback» button on the Help panel

The button next to «About». The window: **Panel** (the first line is «General — LowLife as a whole») → a **Button** of that panel (or «The whole panel / don't know») → **Problem / Suggestion** → **Description** and an optional contact. Ctrl+Enter — send. You can only send with the personal data processing consent checkbox ticked: it isn't remembered and has to be ticked again for every message; without it «Send» is disabled. The Revit and Windows user names, the LowLife version (commit), the Revit version and the open model's file name are added to the message automatically.

The list of panels and buttons is built from the extension folders (`lib/lowlife/ribbon_catalog.py`: captions from `bundle.yaml`/`__title__`, order from `layout:`), so new buttons appear in it by themselves.

Messages go to **the author's Google Sheet** — separate from «Project notes». The web app (`docs/feedback/Code.gs`) only appends rows; you can't read other people's feedback through it — only the status of and the reply to your own (see «The author's reply» below). Without internet (or while the address isn't set) the message is saved to `%APPDATA%\pyRevit\LowLifeFeedback\queue.json` and goes out with the next send; re-sending doesn't create duplicates (checked by ID). The window doesn't wait for the sheet: «Send» closes it at once, and the message goes out in the background while you keep working.

Code: `lib/pnotes/feedback.py` (the window and sending; HTTP is shared with notes — `pnotes/core.py`), layout — `lib/pnotes/xaml/feedback.xaml`, the button — `LowLife.tab/Info.panel/Info.stack/Feedback.pushbutton`.

## Setting up the Google part (once, done by the author)

1. Create a new Google Sheet (on your own account).
2. **Extensions → Apps Script**, paste the whole `docs/feedback/Code.gs`, save.
3. Run the `setup` function and grant permissions («app not verified» — «Advanced → Go to project»). A «Обратная связь» sheet appears.
4. **Deploy → New deployment → Web app**, execute as «Me», access «Anyone» → copy the address ending in `/exec`.
5. Put it into `FEEDBACK_URL` in `lib/pnotes/feedback.py` and commit — after updating LowLife, every user's messages go to the sheet (including the ones queued locally).

To check before committing: put a `%APPDATA%\pyRevit\LowLifeFeedback\config.json` like `{"url": "https://script.google.com/macros/s/…/exec"}` on your machine — a personal address overrides `FEEDBACK_URL`.

The address ends up in a public repository, so there's no token (it would be visible anyway). Protection: the web app only appends rows, trims long fields, escapes values that look like formulas and accepts no more than 20 messages a minute. If spam starts — make a new deployment (the address changes) and update `FEEDBACK_URL`.

An email about every message: `NOTIFY_BY_EMAIL = true` in `Code.gs` (Google asks for permission to send mail).

The «Status» (a list: New / In progress / Done / Won't do / Duplicate), «Comment» and «Reply to the user» columns are filled in by hand; only the author sees «Comment», while the status and reply are visible to the sender (see below).

## The author's reply

To reply, write the text in the **«Reply to the user»** column of the message's row (and change «Status» if you like). The time is put in «Replied at» next to it by itself (a simple `onEdit` trigger in `Code.gs`). If you edit a reply, it becomes new again for the user.

How the reply reaches the user:

- Every sent message stays on the user's machine in `%APPDATA%\pyRevit\LowLifeFeedback\sent.json` (the last 100). Messages sent before this LowLife version aren't there — reply to those via the contact.
- LowLife asks the web app (the `replies` action) for the status and reply by the IDs of its own messages: in the background when Revit starts and when a model opens (no more than once every 3 hours; messages that didn't go out without a connection are re-sent along the way), and also every time the «Feedback» window opens and on the «Check replies» button.
- The window has a **«My messages»** tab: your messages with their status and the author's reply; when there's a new reply, the window opens straight on it, and the tab title shows «new replies: N».
- A new reply found by the background check — a Windows notification «LowLife — ответ автора» (author's reply); an unread reply also reminds you when a model opens (once per Revit session). A reply counts as read once the «My messages» tab has been opened.

A message ID is 16 random hex characters known only to the sender and you; the web app gives out the status and reply only for an exact ID (no more than 200 IDs per request, 120 requests a minute), so other people's replies can't be read this way. So don't write anything in a reply that isn't meant for the sender — that's what «Comment» is for.

When changing the script code: **Manage deployments → ✏️ → New version** (a new deployment gives a new address).

## Button usage statistics

Through the same web app LowLife collects which buttons are pressed: every time a LowLife button runs (from the ribbon or through «Search»), the time, panel and button, the Revit and Windows user names, the model file name and the LowLife and Revit versions are recorded. Model content isn't sent.

- How it's caught: `hooks/app-init.py` → `lib/pnotes/usage.py` subscribes to ribbon clicks (`Autodesk.Windows.ComponentManager.ItemExecuted`); a button Id of the form `CustomCtrl_%CustomCtrl_%LowLife%<panel>%<button>` is matched against `ribbon_catalog.list_buttons()` (the «Theme» list and other non-buttons don't count). «Search» runs buttons through `PostCommand` — it records such a run itself (the «Откуда» (source) column = «Поиск»).
- A click only appends a row to `%APPDATA%\pyRevit\LowLifeUsage\queue.json` and doesn't touch the network. Sending happens in the background, in batches: when 20 runs have piled up or the first is older than 30 minutes, and also when Revit starts. Without a connection the queue waits (no more than the last 5000 runs); re-sending the same batch doesn't duplicate rows.
- To switch it off: the «Send button usage statistics to the author» checkbox in the «About» window (takes effect at once; switching it off also erases anything not yet sent). Kept in `%APPDATA%\pyRevit\LowLifeUsage\config.json`.
- In the sheet: a «Запуски» (runs) sheet (a row per run) and «Статистика» (statistics) — QUERY formulas: buttons for all time and for the last 30 days, users (number of runs and the last one), runs by month. The sheets are created by themselves with the first batch (or by the `setup` function). Buttons missing from the statistics have never been pressed. The formulas adapt to the sheet's locale (in a Russian one the arguments are separated with «;»). The «Статистика» sheet is only created if it doesn't exist — to re-create it (for example after updating `Code.gs`), delete the sheet and run `setup`.

**After updating `Code.gs`** (the `usage` and `replies` actions were added), paste the new code into Apps Script and do **Manage deployments → ✏️ → New version** — the address stays the same. Until then the old web app answers «Неизвестное действие» (unknown action): runs pile up on users' machines and replies aren't checked. The «Reply to the user» and «Replied at» columns are added to the sheet by themselves on the first request (or by the `setup` function); don't change the order of the existing columns — the web app writes rows by position and refuses to work if a column is renamed.
