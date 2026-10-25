[Русский](../email-tasks-app.md) | **English**

# Tasks from mail — the program without Revit

`LowLifeMail.exe` is the same function as the «Tasks from mail» button in Revit ([email-tasks.md](email-tasks.md)), but as a separate program: for people who don't have Revit. It goes through the classic Outlook «Inbox» for the last N days, hands the emails to AI — Claude or ChatGPT — and saves a task list to Excel.

**Mail is only read**: emails aren't sent, opened, marked as read or moved.

## What you need

- Windows 10 or 11.
- **Classic** Outlook with your mail profile. «New Outlook» (olk.exe) won't do — it doesn't have the interface programs need; you can switch back with the «New Outlook» toggle in the top right corner of the Outlook window.
- One of the ways to connect the AI — see below.
- Excel — to open the result. The program writes the file itself without Excel.

Nothing but the program itself needs to be installed: Python and everything else is already inside `LowLifeMail.exe`.

## How to download

1. Open the [Releases](https://github.com/avpersiyanov-afk/LowLife/releases) page and find the latest «Задачи из почты mail-v…» release.
2. Download `LowLifeMail.exe` and put it wherever is convenient (for example on the desktop or in «Documents»). There is no installer — this is the program.
3. On the first launch Windows may show «Windows protected your PC»: the program doesn't have a paid digital signature. Press «More info» → «Run anyway». If an antivirus or the administrator blocks it, ask them to add the file to the exceptions.

A new version — just download the new `LowLifeMail.exe` over the old one; the settings are kept.

## First launch: connecting the AI

Press **«Settings»** → «AI connection» and choose a way:

| Way | What you need | How it is paid |
|---|---|---|
| Claude — the Claude Code app | Install Claude Code and sign in to your Claude account | A Claude subscription (Pro, Max, Team, Enterprise) |
| Claude — Anthropic API | An API key from the Anthropic console | Separately from the subscription, by request volume |
| ChatGPT — the Codex CLI app | Install Node.js and Codex CLI, sign in to your ChatGPT account | A ChatGPT subscription (Plus, Pro, Business, Enterprise) |
| ChatGPT — OpenAI API | An API key from the OpenAI console | Separately from the subscription, by request volume |

Step-by-step instructions for each way are in the general guide: [Claude Code](email-tasks.md#claude-code-claude-subscription), [Anthropic API](email-tasks.md#anthropic-api-key), [Codex CLI](email-tasks.md#codex-cli-chatgpt-subscription), [OpenAI API](email-tasks.md#openai-api-key). Where it says «Revit. Shift+click on the button», press «Settings» in the program; in the settings window each way also has a link to its own instructions. There's no need to restart the program after installing Claude Code or Codex.

**Check.** Turn on «Test mode» in the settings, save and press «Process mail»: the program takes 6 built-in made-up emails instead of Outlook and should find a few tasks. If it works — turn test mode off.

## Working

Use the **Русский / English** list in the main window to select the interface language.
The choice is saved, and captions update immediately. Email content, the prompt and
Excel data keep their original text. Language selection is disabled while mail is being analyzed.

1. Start classic Outlook (if it isn't running, the program starts it in the background by itself).
2. Press **«Process mail»**. At the bottom you can see what's going on: reading emails, then processing in batches («part 1 of 3»). «Cancel» stops processing.
3. The tasks found appear in the table (click a row — details at the bottom), and the Excel file is saved to `Documents\Задачи из почты\Задачи_<date>.xlsx` and opens by itself. «Open Excel» and «Open folder» take you back to it.

In Excel each task has a «Status» column with a dropdown (not started / in progress / waiting for a reply / done); overdue tasks are highlighted red, high priority yellow, done ones grey.

The other settings — the period (how many days to process), unread only, an «Inbox» subfolder, including subfolders, the prompt — are the same as for the button in Revit; details in the [general guide](email-tasks.md#settings-shiftclick).

## Where the settings are kept

`%APPDATA%\LowLife\LowLifeEmailTasks_settings.json`. If the button in Revit is already set up on the computer (`%APPDATA%\pyRevit\LowLifeEmailTasks_settings.json` exists), the program uses its file — they share the settings.

An API key, if you entered one, is kept in this file as plain text. Don't send the file to anyone. Instead you can set the `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` environment variable and leave the key field empty (after `setx`, restart the program).

## If something is wrong

- **«Classic Outlook not found» / «Couldn't connect to Outlook»** — start classic Outlook (not the «new» one) and try again. Outlook and the program must run as the same user: if one of them runs «as administrator» and the other doesn't, they won't connect.
- **Claude Code / Codex «not signed in» or «not found»** — see the [Error messages](email-tasks.md#error-messages) section of the general guide.
- **The AI answer couldn't be parsed** — it is saved to `%TEMP%\LowLifeEmailTasks\answer_*.txt`; the other batches are processed further.
- A question or an error — write to the LowLife author.
