[Русский](../spellcheck.md) | **English**

# Spell check

The `SpellCheck` button («Spell check») on `Tools.panel`. Sends the texts of the model's text notes (`TextNote`) to AI and fixes spelling, grammar, punctuation and typos in them. Nothing changes without your confirmation: a list of corrections is shown first.

## Connecting the AI

The same as for the «Tasks from mail» button, and **shared** with it: if the AI is already set up there, spell check works right away. The options (Claude Code, Anthropic API, Codex CLI, OpenAI API) and installation instructions — [email-tasks.md](email-tasks.md#connecting-the-ai). You can change the option or model in the Shift+click of either button.

## How it works

1. **Scope.** Selected notes (if anything is selected), the current view or the whole model (all views and sheets; linked files aren't read).
2. **What is skipped.** Notes in groups (editing a group member outside group edit mode gives a Revit warning) and, in a workshared model, notes borrowed by another user or changed in the central model — otherwise Revit would cancel the whole transaction. They are listed in the report. Texts without letters (only digits and symbols) aren't sent.
3. **Request.** Identical texts are merged — the AI sees each one once, and the correction is then applied to all copies. Texts go in batches of about 6000 characters as `{"items":[{"id":…,"text":…}]}`, the answer is `{"fixes":[{"id":…,"text":…}]}` only for texts with errors.
4. **Filtering.** A correction too unlike the original text (similarity below 60 %) is treated as rewriting rather than fixing typos and isn't offered — it goes to the «Rejected» section of the report.
5. **Confirmation.** A «was → becomes» list with the final text; all items are ticked — untick the ones you don't want and press «Fix ticked».
6. **Writing.** In one «Проверка орфографии» transaction (undone with one Ctrl+Z). Only the changed words are replaced in a note, so bold, italic, underline and lists are kept. If a targeted replacement fails, the text is written whole — that note's formatting is reset; such notes are marked in the report.
7. **Report** — in the pyRevit output window: what was fixed (with links to the notes), what was skipped and why, AI errors. An AI answer that couldn't be parsed is saved to `%TEMP%\LowLifeSpellCheck\answer_*.txt`.

## Prompt

The standard one — `LowLife.tab/Tools.panel/SpellCheck.pushbutton/prompt.txt`: fix only errors, don't touch designations and tags (ВК-1, ЩО-1), abbreviations, numbers and units, references to standards, cable types, line breaks and the letter «ё». You can type your own text in the Shift+click — it is kept in `%APPDATA%\pyRevit\LowLifeSpellCheck_settings.json` (key `prompt`) and isn't lost when the extension updates; «Restore the standard prompt» brings back `prompt.txt`. Keep the answer format `{"fixes":[{"id":…,"text":…}]}` in your text.

## Limitations

- Only text notes are checked. The text of tags (taken from parameters), dimensions, schedules and families isn't touched.
- Project texts go to the chosen AI service — just like emails in «Tasks from mail».
- Only the pure logic can be checked in this repository (`tests/test_spellcheck_core.py`); writing in Revit is checked on a model.
