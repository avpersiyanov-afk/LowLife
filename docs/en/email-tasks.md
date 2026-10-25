[Русский](../email-tasks.md) | **English**

# Tasks from mail

The `EmailTasks` button («Tasks from mail») on `Mail.panel` («Mail»), registered under the `General` theme of the `_Themes.panel` switcher. It works without an open project (`__context__ = "zero-doc"`) and doesn't touch the Revit model.

> For people without Revit — the same function as a separate program `LowLifeMail.exe`: [email-tasks-app.md](email-tasks-app.md).

It goes through the classic Outlook «Inbox» for the last N days, hands the emails to AI — Claude or ChatGPT; the way of connecting is chosen in the settings (see [Connecting the AI](#connecting-the-ai)) — and saves a task list to Excel.

**Mail is only read**: emails aren't sent, opened, marked as read or moved — only the `ReceivedTime`, `Sender*`, `To`, `CC`, `Subject`, `Body` properties are read.

## What the computer needs

- Windows, **classic** Outlook (Exchange or any other profile). «New Outlook» (olk.exe) doesn't support COM — the button says so.
- Excel.
- One of the ways to connect the AI — see [Connecting the AI](#connecting-the-ai).
- Nothing needs to be installed for the button itself: only the IronPython stdlib and .NET (COM through `System.Type.GetTypeFromProgID` + `Activator`/`Marshal.GetActiveObject`, processes — `System.Diagnostics.Process`, HTTP — `System.Net.HttpWebRequest`).

## Connecting the AI

The way is chosen in the button settings (Shift+click → «AI connection»); each way has a link to its own section of this guide there. The connection is shared with the «Spell check» button ([spellcheck.md](spellcheck.md)): what's set up in one of them works in the other too.

| Way | What you need | How it is paid |
|---|---|---|
| [Claude — the Claude Code app](#claude-code-claude-subscription) | Install Claude Code and sign in to your Claude account | A Claude subscription (Pro, Max, Team, Enterprise) |
| [Claude — Anthropic API](#anthropic-api-key) | An API key from the Anthropic console | Separately from the subscription, by request volume |
| [ChatGPT — the Codex CLI app](#codex-cli-chatgpt-subscription) | Install Node.js and Codex CLI, sign in to your ChatGPT account | A ChatGPT subscription (Plus, Pro, Business, Enterprise) |
| [ChatGPT — OpenAI API](#openai-api-key) | An API key from the OpenAI console | Separately from the subscription, by request volume |

**App or key?** If you already have a Claude or ChatGPT subscription, the app is simpler: there's nothing to pay beyond the subscription, but it has to be installed once. An API key needs nothing installed, but every run costs money (usually cents: a few batches of emails of ~30,000 characters), and the balance in the developer console has to be topped up in advance. A ChatGPT subscription **doesn't** give access to the OpenAI API, just as a Claude subscription doesn't give access to the Anthropic API: they are different products with separate billing.

**Where the key is kept.** In the settings file `%APPDATA%\pyRevit\LowLifeEmailTasks_settings.json` on your computer, as plain text. Don't send this file to anyone or publish it. Instead of entering the key in the settings you can set an environment variable (`ANTHROPIC_API_KEY` or `OPENAI_API_KEY`) — the button uses it if the key field is empty:

```powershell
setx ANTHROPIC_API_KEY "sk-ant-..."
```

After `setx`, restart Revit — environment variables are read when a program starts.

### Claude Code (Claude subscription)

Claude Code is Anthropic's command-line program. It has to be installed once and signed in to your Claude account; no API key is needed, requests go under your subscription.

1. **Subscription.** You need an account on [claude.ai](https://claude.ai) with a paid subscription (Pro, Max, Team or Enterprise) — the free plan doesn't support Claude Code.
2. **Installation.** Open PowerShell (Start → «PowerShell») and run:

   ```powershell
   irm https://claude.ai/install.ps1 | iex
   ```

   The program goes to `%USERPROFILE%\.local\bin\claude.exe` — the button finds this folder by itself. If the installer asks for Git for Windows, install it from [git-scm.com](https://git-scm.com/downloads/win) and run the command again. Details — in the [official guide](https://docs.anthropic.com/en/docs/claude-code/setup).
3. **Sign in.** In a new PowerShell window run `claude`. On the first run a browser opens — sign in to your Claude account and allow access. When the window shows a prompt to type a request, you're signed in; close the window (`/exit`).
4. **Check.** In PowerShell run:

   ```powershell
   claude -p "Answer in one word: does it work?"
   ```

   A short answer should come back without asking you to sign in.
5. **Revit.** No need to restart Revit. Shift+click on the «Tasks from mail» button → «AI connection»: «Claude — the Claude Code app». The path found should be visible under the «Path to claude.exe» field. If no path is found (Claude Code is in another folder), enter the full path to `claude.exe` by hand — the `where.exe claude` command shows it.
6. **Model** — the alias `sonnet` (the default), `opus` or `haiku`, as for `claude --model`.

If the button says Claude Code isn't signed in, run `claude`, then `/login` and sign in again. If it says the version doesn't support the needed flags, run `claude update`.

### Anthropic API (key)

1. **Account.** Open the Anthropic developer console — [platform.claude.com](https://platform.claude.com) — and sign in or sign up. It's a separate dashboard from claude.ai, although you can sign in with the same email.
2. **Billing.** *Settings → Billing*: top up the balance (credits are bought in advance). Without money on the account requests are rejected — the button says «out of money or billing not set up».
3. **Key.** *Settings → API keys* → *Create Key*, give the key a clear name (for example «Revit — tasks from mail»). Copy the key (it starts with `sk-ant-`) — it is shown in full only once.
4. **Revit.** Shift+click on the button → «AI connection»: «Claude — Anthropic API», paste the key into the «Anthropic API key» field, «Save».
5. **Model** — `claude-opus-5-5` by default. You can give a full name (`claude-sonnet-5-5` — cheaper, `claude-haiku-4-5` — the cheapest and fastest) or a short `opus` / `sonnet` / `haiku`.
6. **Check** — turn on «Test mode» in the settings and press the button: it processes 6 made-up emails and should find 4 tasks.

The key can be revoked in the same place, *API keys* — for example if it got into the wrong hands.

### Codex CLI (ChatGPT subscription)

Codex CLI is OpenAI's command-line program. It has to be installed once and signed in to your ChatGPT account; no API key is needed, requests go under your subscription.

1. **Subscription.** You need a ChatGPT account with a Plus, Pro, Business or Enterprise subscription.
2. **Node.js.** Codex is installed through npm, so Node.js is needed first: download the LTS installer from [nodejs.org](https://nodejs.org) and install it with the default settings.
3. **Installing Codex.** In a **new** PowerShell window run:

   ```powershell
   npm install -g @openai/codex
   ```

   The program goes to `%APPDATA%\npm\codex.cmd` — the button finds this folder by itself. Details — in the [official guide](https://developers.openai.com/codex/cli).
4. **Sign in.** Run `codex login` — a browser opens; sign in to your ChatGPT account («Sign in with ChatGPT») and allow access.
5. **Check.** In PowerShell run:

   ```powershell
   codex exec --skip-git-repo-check "Answer in one word: does it work?"
   ```

   A short answer should come back without asking you to sign in.
6. **Revit.** Shift+click on the button → «AI connection»: «ChatGPT — the Codex CLI app». The path found should be visible under the «Path to codex» field; if not, enter it by hand (the `where.exe codex` command shows it).
7. **Model** — empty (the default): Codex takes the model from its own settings. You can give a name, as for `codex -m`.

If the button says Codex isn't signed in, run `codex login` again. If it says the version doesn't support the needed flags, update: `npm install -g @openai/codex@latest`.

### OpenAI API (key)

1. **Account.** Open the OpenAI developer console — [platform.openai.com](https://platform.openai.com) — and sign in or sign up. It's a separate dashboard from chatgpt.com.
2. **Billing.** *Settings → Billing*: add a payment method and top up the balance. A ChatGPT subscription doesn't count here.
3. **Key.** The [API keys](https://platform.openai.com/api-keys) page → *Create new secret key*, give it a clear name. Copy the key (it starts with `sk-`) — it is shown in full only once.
4. **Revit.** Shift+click on the button → «AI connection»: «ChatGPT — OpenAI API», paste the key into the «OpenAI API key» field, «Save».
5. **Model** — `gpt-5` by default; you can give another one, for example `gpt-5-mini` (cheaper).
6. **Check** — «Test mode» in the settings, as for the Anthropic API.

## How it works

1. **Reading mail** (`lib/lowlife/email_outlook.py`). The «Inbox» (or a subfolder from the settings) and, if «Including subfolders» is on, all nested folders. In each folder — only `MailItem`s (`Class == 43`), sorted by `ReceivedTime` descending, stopping at the first email older than the period; then the emails of all folders are merged into one list by date. The email's folder path is passed to Claude along with the email. For Exchange senders the SMTP address is taken through `Sender.GetExchangeUser().PrimarySmtpAddress` (fallbacks — a distribution list and MAPI properties). The email text is cut at conversation history markers («От:», «From:», «-----Original Message-----», «-----Исходное сообщение-----», «… пишет:», Outlook's `____` line) and to 4000 characters (`email_tasks_core.trim_body`). A safeguard — no more than 400 emails per run.
2. **Analysis by the AI** (`lib/lowlife/email_ai.py` picks the way by the `provider` key). Emails are split into batches of ≈30,000 characters, one call per batch; the request is the prompt from `prompt.txt` + today's date + the emails, plus a short system prompt «return only JSON».
   - **Claude Code** (`email_claude.py`): `claude -p --output-format json --model <model> --tools "" --max-turns 1 --no-session-persistence --strict-mcp-config --system-prompt <...>` (flags checked against `claude --help`, Claude Code 2.1). Timeout — 3 minutes.
   - **Codex CLI** (`email_codex.py`): `codex exec --skip-git-repo-check --sandbox read-only --ephemeral --color never -o <file> [-m <model>] -` (flags from the Codex CLI command reference; not checked on a live `codex`). The answer is read from the `-o` file. The system prompt goes as the first lines of the request — `codex exec` has no separate flag for it. Timeout — 5 minutes.
   - **Anthropic API**: `POST https://api.anthropic.com/v1/messages`, headers `x-api-key`, `anthropic-version: 2023-06-01`; `max_tokens` 16000, the system prompt in `system`. For models with a server-side fallback route on a safety filter refusal (`claude-opus-5-5`, `claude-opus-5`, `claude-sonnet-5-5`, `claude-fable-5-1`), `fallbacks: "default"` and the header `anthropic-beta: server-side-fallback-2026-07-01` are added. The `text` blocks are taken from the answer; a `stop_reason` of `refusal`/`max_tokens` is a batch error.
   - **OpenAI API**: `POST https://api.openai.com/v1/chat/completions`, `Authorization: Bearer <key>`, `system` + `user` messages; the answer is `choices[0].message.content`.

   For the programs (Claude Code, Codex) the request goes **through stdin in UTF-8** — not as an argument (the Windows command-line length limit); the process runs in a temporary folder `%TEMP%\LowLifeEmailTasks` so as not to pick up someone else's `CLAUDE.md`/`AGENTS.md`. The HTTP request to an API runs on a background thread (`email_ai_net.post_json`; in Revit — `email_ai_clr`, in the program without Revit — `email_ai_std`), timeout — 3 minutes. The pure logic (request bodies, parsing answers, turning HTTP errors into clear text) is in `email_ai_core.py`, covered by tests.
3. **Parsing the answer** (`email_tasks_core.parse_tasks_json`): the ``` wrapper is stripped and the JSON `{"tasks": [...]}` (or a bare array) is pulled out of the text. If the answer couldn't be parsed, it is saved to `%TEMP%\LowLifeEmailTasks\answer_*.txt`, and the other batches are processed further.
4. **The pyRevit output window** — a table of tasks, sorted by priority → due date → email date.
5. **Excel** (`lib/lowlife/email_tasks_excel.py`): `Documents\Задачи из почты\Задачи_YYYY-MM-DD_HHMM.xlsx`, opened after saving. Columns: No., Task, Requested by, Due, Priority, Status (a dropdown: Not started / In progress / Waiting for a reply / Done), Comment, Email subject, Sender, Email date (the column names are in Russian). Arial 10, a frozen header, autofilter, text wrapping. Conditional formatting: a row with the status «Done» — grey; an overdue date (and the status isn't «Done») — red; high priority — yellow.

## Prompt

Edited in the settings window (Shift+click → the «Prompt» field); the same for every way of connecting the AI. The standard text is in `LowLife.tab/Mail.panel/EmailTasks.pushbutton/prompt.txt`. While the text in the settings is empty or matches the standard one, `prompt.txt` is used — so prompt updates in new extension versions are picked up by themselves. Your own text is kept in the settings file (the `prompt` key) and isn't lost when the extension updates; «Restore the standard prompt» puts the `prompt.txt` text back.

Today's date and the emails themselves are added to the prompt automatically. It's important to keep the answer format in the prompt (`{"tasks":[{"email_id":…,"task":…,"requester":…,"deadline":…,"priority":…,"comment":…}]}`) — the answer is parsed by it.

The standard prompt is in Russian and asks for tasks in Russian; to get tasks in English, write your own prompt.

## Settings (Shift+click)

`%APPDATA%\pyRevit\LowLifeEmailTasks_settings.json` (the pyRevit configuration folder; like the extension's other buttons — a separate JSON file, not `pyrevit.script.get_config()`):

| Field (key) | Default | What it does |
|---|---|---|
| AI connection (`provider`) | Claude Code (`claude_cli`) | `claude_cli` / `anthropic_api` / `codex_cli` / `openai_api`, see [Connecting the AI](#connecting-the-ai) |
| Path to claude.exe (`claude_path`) | empty (auto-search) | PATH → `%USERPROFILE%\.local\bin\claude.exe` → `%APPDATA%\npm\claude.cmd` |
| Claude Code model (`claude_cli_model`) | `sonnet` | As for `claude --model` |
| Anthropic API key (`anthropic_api_key`) | empty (= `ANTHROPIC_API_KEY`) | A `sk-ant-…` key |
| Anthropic API model (`anthropic_api_model`) | `claude-opus-5-5` | A full name or `opus`/`sonnet`/`haiku` |
| Path to codex (`codex_path`) | empty (auto-search) | PATH → `%APPDATA%\npm\codex.cmd` → `%USERPROFILE%\.local\bin\codex.exe` |
| Codex model (`codex_cli_model`) | empty | As for `codex -m`; empty — from the Codex settings |
| OpenAI API key (`openai_api_key`) | empty (= `OPENAI_API_KEY`) | A `sk-…` key |
| OpenAI API model (`openai_api_model`) | `gpt-5` | An OpenAI model name |
| Period, days (`days`) | 3 | How many recent days to process |
| Unread only (`unread_only`) | no | `Items.Restrict("[UnRead] = True")` |
| «Inbox» subfolder (`subfolder`) | empty | For example `Проекты/Объект 1` |
| Including subfolders (`include_subfolders`) | yes | Also read all nested folders (of the Inbox or of the folder above) |
| Test mode (`test_mode`) | no | Emails from `test_emails.json` instead of Outlook |
| Prompt (`prompt`) | empty (= `prompt.txt`) | Your own prompt text, see above |

The window shows only the fields of the chosen way of connecting; saving also checks only that way (the program is found at the given path, there's a key in the field or in the environment variable). Keys are kept as plain text in this file. The Claude Code model from old versions (the `model` key) is moved to `claude_cli_model` automatically.

## Test mode

`test_emails.json` next to the script — 6 made-up emails: two tasks in one email (with a relative due date «by Friday» and a meeting «tomorrow at 10:00»), an email with an explicit due date and a second, non-urgent task, an advertising mailing, a «thank you» with quoted history (the history contains a request — it must be cut off), an automatic notification and an informational email «no action required». The email dates are set as «today minus `days_ago`», so relative due dates can always be checked.

The expected result: 4 tasks from two emails; the mailing/«thank you»/notification/informational email aren't tasks.

## Error messages

- classic Outlook not found / it's «new Outlook» without COM / Outlook isn't running or isn't available;
- subfolder not found;
- claude / codex not found (at the path from the settings or by auto-search);
- Claude Code / Codex not signed in; hit the subscription limit; the model isn't available; the program version doesn't know the needed flags; timeout;
- no API key given; the key was rejected (wrong or revoked); no access; out of money on the API account; rate limit; the service is overloaded; no connection (internet, proxy);
- the AI refused to process a batch (safety filter) or the answer was cut off at the length limit — an error for that batch, the others carry on;
- no emails for the period;
- couldn't parse the AI answer (the answer is saved to a file);
- an Excel error.

## Known limitations

- While the AI call is running, the progress window is updated through `Application.DoEvents()` (otherwise it «freezes» for minutes and «Cancel» doesn't work).
- The Codex CLI, Anthropic API and OpenAI API ways are written from the documentation and haven't been checked in a live Revit yet — on the first error, look at the «Details» text in the button's message.
- Outlook without an up-to-date antivirus may show the security window «A program is trying to access e-mail address information» — that's Outlook's protection against COM access; allow access.
- Only emails (`MailItem`) are read; meeting invitations (`MeetingItem`) aren't processed.
