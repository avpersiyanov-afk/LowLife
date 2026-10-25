[Русский](../notes-panel.md) | **English**

# Notes.panel — «Project notes»

The **Notes** panel on the LowLife tab: notes, tasks and reminders on a project, kept in the team's shared Google Sheet. The connection to the sheet goes through a Google Apps Script web app (`docs/notes/Code.gs`).

Code: `lib/pnotes/` (`core.py` — settings, HTTP, project information, the queue; `ui.py` — windows; `xaml/` — window layouts), the buttons — `LowLife.tab/Notes.panel/`, reminders on opening — at the end of `hooks/doc-opened.py`.

The sheet's sheets, menus, statuses and column names are in Russian (they are what `Code.gs` creates); the English names below are translations.

## Buttons

- **Note** — Type → Section → Text, plus an optional due date, «assigned to» and linking the selected elements. The project code and name, the view, the model and the author are filled in automatically. Ctrl+Enter — save, Esc — cancel.
- **Summary** — all notes of the current project, including from other models with the same project code. Filters by status/type/section/author, a search, «Only mine», the «Done / In progress / Not relevant / Reopen» buttons, double-click or «Show elements» — select the linked elements in the model; **«Open view / sheet»** — open the view or sheet the note was created on (looked up by view name / sheet number and name in the same model). **«✎ Edit»** — fix the type, section, text, due date and «assigned to» of the selected note (the sheet marks «Изменено» (changed) and «Кто изменил» (changed by); the author, project and linked elements don't change; an unsent note is edited in the local queue). **«Answer / decision»** — write an answer to the «Решение» (decision) column (and mark it «Done» right away). A **Question** (type «Вопрос») can't be closed without an answer: «✓ Done» on an unanswered question opens the answer window right away; unanswered questions are highlighted orange in the «Решение» column.
- **Setup** — the connection address and token + an analysis of «Project Information»: what is filled in, which parameter counts as the project code, which as the name, which values to save with every note. The parameter choice is shared by the whole team (kept on the sheet's «Настройки» (settings) tab).

**Reminders when a model opens**: overdue notes and notes due soon + those assigned to you — no more than once per Revit session per project. Without a network or a configured connection the hook silently does nothing and doesn't get in the way of opening the model.

**Without internet** a note isn't lost: it is first written to `%APPDATA%\pyRevit\ProjectNotes\queue.json` and goes to the sheet with the next note or when the summary opens (the summary shows such notes in italics with the status «Не отправлено» (not sent)).

## Connecting a new team or company

Each team's notes are kept in **its own** Google Sheet: a company that installs LowLife creates a sheet for itself — it has nothing to do with anyone else's notes. You need to make the sheet once (about 10 minutes) and give the staff two values: the web app **address** and the **token**.

You'll need:
- a Google account the sheet will work under. A shared work account is better than an employee's personal one: if that account is deleted, notes stop working for everyone;
- the sheet script — the file [`docs/notes/Code.gs`](../notes/Code.gs) of this repository. Anyone who has LowLife installed already has it on their computer: `%APPDATA%\pyRevit\Extensions\LowLife.extension\docs\notes\Code.gs`. In Revit, links to the script and to this guide are in the **Notes → Setup** window.

### Step 1. Create the sheet

1. Open <https://sheets.new> — an empty Google Sheet is created.
2. Name it (top left), for example «Заметки Revit» (Revit notes).

The sheet must be new: the script creates the «Заметки», «Настройки», «Сводка», «Все проекты», «Сроки» sheets itself (notes, settings, summary, all projects, due dates). If there's already a «Заметки» sheet, rename it.

### Step 2. Paste the script

1. Open [`docs/notes/Code.gs`](../notes/Code.gs) on GitHub and press the two-squares icon («Copy raw file») to the right above the code — the whole code is copied. (Or open the local `Code.gs` in Notepad and copy everything.)
2. In the sheet: **Extensions → Apps Script**. An editor opens with the text `function myFunction() { … }`.
3. Select it (**Ctrl+A**), delete it, paste the copied code (**Ctrl+V**) and save (**Ctrl+S** or the floppy icon).

### Step 3. Initial setup and the token

1. Above the code, next to the **▶ Run** button, pick the **`setup`** function in the list and press **▶ Run**.
2. Google asks for permissions: **Review permissions** → choose the account → on the «Google hasn't verified this app» screen press the small **«Advanced»** link → **«Go to … (unsafe)»** → **Allow**. It's your own script; the warning is normal.
3. The script creates the sheets and a **token** — a long string of letters and digits. It is shown in the «Execution log» at the bottom of the editor (and in a pop-up in the sheet). Copy it. Later the token can always be seen in the sheet menu **Заметки Revit → Показать токен** (show token).

There's no need to create the token separately — `setup` makes it; it is kept in the script properties and is the same for all staff.

### Step 4. Publish the web app — get the address

1. In the Apps Script editor, top right: **Deploy → New deployment**.
2. Next to «Select type» press the gear ⚙ → **Web app**.
3. Fill in:
   - **Description** — anything, for example «v1»;
   - **Execute as** — **Me**;
   - **Who has access** — **Anyone**.
4. **Deploy** (if it asks for permissions again — as in step 3).
5. Copy the **Web app URL** — it ends in **`/exec`**. That's the address.

### Step 5. Connect Revit for the staff

1. An employee installs LowLife in pyRevit (Extensions → Add from GitHub URL, the link to this repository) or updates it, then pyRevit → **Reload**.
2. In Revit: the LowLife tab → **Notes → Setup** → paste the **address** and **token** → **Check connection** (it should say «✓ Связь есть» — connected).
3. **Once per team** someone chooses in the same window which «Project Information» parameter is the project code and which is the name, and presses **«Save for the whole team»** (the choice is written to the «Настройки» sheet).

The address and token are saved only on that computer, in `%APPDATA%\pyRevit\ProjectNotes\config.json`. Give them to the staff personally (email, messenger) — **don't publish them**: with the address and token anyone can read and write notes.

> For the administrator: to avoid typing them in by hand, put a `config.json` (following `config.example.json`) into the root of the LowLife extension folder on each computer — the fields fill in by themselves. **Don't commit it to the repository**: it is public, and `/config.json` is in `.gitignore`. A personal file in `%APPDATA%` overrides the shared one.

If the project code parameter in the model is empty, the file name is used (of the central model if the model is workshared) — better fill in the parameter, otherwise notes from different models of one project end up under different codes.

### Sheet access and security

- Revit works with the sheet **through the script**, on behalf of the owner («Execute as: Me»), so the sheet itself can be closed: **Share → Restricted**. Staff don't need access to the sheet to work from Revit.
- The deployment must keep «Who has access: **Anyone**» — Revit can't sign in to a Google account; only the token lets it in. If your organisation's Google Workspace doesn't allow choosing «Anyone», this way of connecting won't work.
- To view the sheets in a browser — the **Viewer/Commenter** role. **Editor** — only for trusted people: they can see the script code and the token.
- To change the token (it leaked, an employee left): Apps Script → ⚙ **Project settings** → «Script properties» → delete `TOKEN` → in the sheet, **Заметки Revit → Первичная настройка** (initial setup) creates a new one. The address doesn't change; give out the new token again.

### Updating the script

When `Code.gs` changes in the repository:
1. Copy the new code, replace the whole text in Apps Script with it, and save.
2. **Deploy → Manage deployments → ✏️ → Version: New version → Deploy**. Exactly this way: a **new** deployment gives a new address that would have to be given to everyone again.
3. In the sheet, **Заметки Revit → Первичная настройка** re-creates the summary sheets; notes, «Настройки» and the token aren't touched.

## What to adjust later

- The «Настройки» sheet: the «Типы», «Разделы», «Сотрудники» columns (types, sections, staff — Revit user names: Options → General → Username), how many days before the due date to remind, whether to remind when a model opens.
- The status can be changed right in the sheet — «Изменено» and «Кто изменил» fill in by themselves.
- The **«Сводка»** (summary) sheet — everything about one project: in cell B2 pick the project code from the dropdown, in B3 — «Открытые» (open) or «Все» (all). Below — counters by status (total / open / in progress / done / cancelled / overdue) and the project's notes table sorted by due date; done ones are highlighted green, cancelled grey, overdue dates red.
- The **«Все проекты»** (all projects) sheet — open notes, projects × sections; the **«Сроки»** (due dates) sheet — overdue and the next 3 days across all projects. Everything is updated by formulas.
- The **«Решение»** (decision) column on the «Заметки» sheet — the answer to a question / the decision taken; it can also be typed right in the sheet («Изменено» and «Кто изменил» fill in by themselves). In sheets created before it appeared, the column is added at the end with the next request from Revit or by «Первичная настройка».
- After updating `Code.gs`, the sheets are re-created through the sheet menu «Заметки Revit → Первичная настройка» (notes and «Настройки» aren't touched).

## Troubleshooting

- **«Таблица ответила не данными, а страницей»** (the sheet answered with a page, not data) — the wrong URL (it needs `/exec`) or the web app's access isn't «Anyone».
- **«Неверный токен»** (wrong token) — compare it with the sheet menu «Заметки Revit → Показать токен».
- **«Неизвестное действие: …»** (unknown action) — the code was updated in Apps Script but no new deployment version was released: **Manage deployments → ✏️ → New version**.
- **«Access error» when running `setup` / no «Advanced» link** — the organisation's Google Workspace forbids unverified scripts; you need another account or the Workspace administrator's permission.
- **«Нет связи с Google Таблицей»** (no connection to the Google Sheet) — internet or a proxy to `script.google.com`; meanwhile notes pile up locally. One-off connection drops and Google error answers are retried automatically once, so the message means the sheet didn't answer on the second attempt either.
- **How the windows work without waiting for the network.** «Summary», «Note» and «Setup» open right away with the last saved copy (of the team settings and the project's notes), and fresh data from the sheet is loaded in the background: «Summary» shows «Обновление из таблицы…» (updating from the sheet) meanwhile. So edits of the «Настройки» sheet (types, sections, staff) reach the windows from the next opening. Only the very first run on a computer, when there's no copy yet, waits for the sheet to answer.
- **A note goes out in the background.** «Save» closes the window at once: the note is written to the computer and sent to the sheet while you keep working. If there's no connection, it stays in the queue (in «Summary» — with the status «Не отправлено») and goes out with the next note or when the summary opens; the new note window shows how many notes are still waiting to be sent.
- **Changes in the summary don't wait for the sheet either.** A status, an edit or an answer is visible in the summary at once and goes to the sheet in the background; if the sheet didn't accept it, the change is rolled back and a message appears. While changes are being sent, the summary doesn't close — it closes by itself as soon as they're saved.
- **`#ERROR!` «Синтаксическая ошибка в формуле» (formula parse error) on the «Сводка»/«Все проекты»/«Сроки» sheets** — an old version of the script wrote formulas with commas, while in a Russian sheet locale the arguments are separated with «;». Paste a fresh `Code.gs` (Apps Script → replace the whole text → save), then in the sheet run «Заметки Revit → Первичная настройка» — the summary sheets are re-created; notes and «Настройки» aren't touched.
- **The «Notes» panel didn't appear** — pyRevit → Reload after updating LowLife.

Personal data on the computer: `%APPDATA%\pyRevit\ProjectNotes\` — `config.json` (address and token), `settings_cache.json`, `notes_cache.json`, `queue.json`, `state.json`.
