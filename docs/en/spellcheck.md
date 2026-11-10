[Русский](../spellcheck.md) | **English**

# Spell check

The `SpellCheck` button («Spell check») on `Tools.panel`. Checks text notes, sheet names, title blocks, generic annotations and manual schedule header cells with AI. Equipment and other model family parameters are excluded before reading parameters. Corrections are previewed before applying them.

## Connecting the AI

The same as for the «Tasks from mail» button, and **shared** with it: if the AI is already set up there, spell check works right away. The options (Claude Code, Anthropic API, Codex CLI, OpenAI API) and installation instructions — [email-tasks.md](email-tasks.md#connecting-the-ai). You can change the option or model in the Shift+click of either button.

## How it works

1. **Sources and scope.** Choose notes, sheet names, title blocks, generic annotations and/or manual schedules, then selected elements, current view or whole model. Links are excluded. For title blocks and generic annotations, choose filled instance/type text fields. **Type edits affect all instances of that type**, including outside the scope. Each placed type is checked once. Current-view scope includes a sheet name only when that sheet is active. Notes and annotations are collected on the view/sheet itself without traversing viewports. Manual tables are multi-row schedule headers, including LL explications. On a sheet, each placed schedule is checked once; open schedules and selected schedule instances are supported. Manual cells use the existing schedule import to validate original text, table structure and merged cells before writing.
2. **What is skipped.** Notes in groups (editing a group member outside group edit mode gives a Revit warning) and, in a workshared model, notes borrowed by another user or changed in the central model — otherwise Revit would cancel the whole transaction. They are listed in the report. Texts without letters (only digits and symbols) aren't sent.
3. **Request.** Identical texts are merged — the AI sees each one once, and the correction is then applied to all copies. Texts go in batches of about 6000 characters as `{"items":[{"id":…,"text":…}]}`, the answer is `{"fixes":[{"id":…,"text":…}]}` only for texts with errors.
4. **Filtering.** A correction too unlike the original text (similarity below 60 %) is treated as rewriting rather than fixing typos and isn't offered — it goes to the «Rejected» section of the report.
5. **Confirmation.** A resizable two-column window shows the full original text with errors in red on the left and the corrected text with changes in green on the right. Text wraps to the column width. The source is shown below each row; all destinations are available in its tooltip. Checkboxes, select-all and a selected count control which corrections are applied. Untick unwanted rows and press «Fix ticked».
6. **Writing.** In one «Проверка орфографии» transaction (undone with one Ctrl+Z). Only the changed words are replaced in a note, so bold, italic, underline and lists are kept. If a targeted replacement fails, the text is written whole — that note's formatting is reset; such notes are marked in the report.
7. **Report** — in the pyRevit output window: what was fixed (with links to the notes), what was skipped and why, AI errors. An AI answer that couldn't be parsed is saved to `%TEMP%\LowLifeSpellCheck\answer_*.txt`.

## Prompt

The standard one — `LowLife.tab/Tools.panel/SpellCheck.pushbutton/prompt.txt`: fix only errors, don't touch designations and tags (ВК-1, ЩО-1), abbreviations, numbers and units, references to standards, cable types, line breaks and the letter «ё». You can type your own text in the Shift+click — it is kept in `%APPDATA%\pyRevit\LowLifeSpellCheck_settings.json` (key `prompt`) and isn't lost when the extension updates; «Restore the standard prompt» brings back `prompt.txt`. Keep the answer format `{"fixes":[{"id":…,"text":…}]}` in your text.

## Limitations

- Read-only parameters are excluded. Group members and unavailable workshared elements are skipped. Before writing, availability and the original text are checked again. Sheet names and parameter values are written to their exact original fields; sheet numbers stay unchanged.
- Dimension text, ordinary schedule bodies and text inside the family editor are excluded. Ordinary schedule element parameters are never scanned.
- Project texts go to the chosen AI service — just like emails in «Tasks from mail».
- The pure logic (`tests/test_spellcheck_core.py`) and adapter with an API substitute (`tests/test_spellcheck_targets.py`) are tested here; actual writes require a Revit model.
