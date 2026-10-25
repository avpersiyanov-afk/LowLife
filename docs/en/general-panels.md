[Русский](../general-panels.md) | **English**

# The LowLife panel, your own panels, «Help», «Selection filter» and «Music»

## The LowLife panel

The first panel of the tab, visible under any theme: the small «Search» and «Create my panel» buttons one above the other, and the «Theme» and «Language» lists.

### Search

Finds any LowLife button and runs it — no need to remember which panel it's on.

1. Press «Search» and start typing a button name, a panel name or a word from a tooltip — in Russian or English. Case, «ё»/«е» and the wrong keyboard layout don't matter.
2. Pick a button in the list:
   - **Enter** — run it;
   - **Ctrl+Enter** — show it on the ribbon: the tab opens and the button blinks with an orange fill. The button appears even if the selected theme hides it (until the next theme switch);
   - **«To my panel»** — add it to [your own panel](#my-panels) (pick a panel or create a new one).

### Theme

A dropdown that leaves only the buttons you need on the ribbon:

| Theme | What is visible |
|---|---|
| My panel | only [your own panels](#my-panels), the «Help» panel and the LowLife panel (with this list, to get back to another theme) |
| SCS, ACS, CCTV, Voice alarm, Fire alarm, Fire automation, SS1 | the buttons of one discipline, including its circuits |
| Trays | the cable tray buttons |
| Electrical circuits | all circuit-building buttons (SCS/ACS/fire alarm/fire automation/general) |
| Settings | parameter settings of all disciplines |
| General | tools and music, not tied to a discipline |
| Service | rarely needed service buttons (export renaming, diagnostics) |

Panels with no buttons left under the selected theme are hidden too. A hidden button can be found and run through [«Search»](#search).

### Language

The «Язык / Language» list switches the ribbon between Russian and English: panel names, button captions and tooltips, and the theme names. The switch is instant, no pyRevit reload; the choice is remembered. Windows and messages are being translated panel by panel — until then some of them are still in Russian.

## My panels

Your own panels made of the LowLife buttons you need — for example «My circuits» with three buttons from different panels. Your panels sit on the LowLife tab right after the LowLife panel and are visible under any theme. You can have up to 8 of them.

1. Press **«Create my panel»** on the LowLife panel. On the left — your panels: **«New…»** creates a panel (any name except the names of LowLife's own panels), **«Rename…»**, **«Delete»**, **▲/▼** — the order of the panels on the ribbon.
2. On the right — all LowLife buttons with a search (as in «Search»). Pick a button and press **«← Add to panel»** (or double-click it) — it is added to the end of the selected panel. In the middle — the panel's buttons: **«Remove»**, **▲/▼** — the order.
3. You can do all the same **with the mouse**: drag a button from the list on the right to the right spot in the panel's button list or straight onto a panel on the left; a panel button — to another spot, to another panel on the left or back to the list on the right (remove it from the panel); a panel — higher or lower in the list of panels.
4. **«Save»** — LowLife offers to reload pyRevit: your panels appear on the ribbon after the reload (if you said no — press pyRevit → «Reload» when convenient).

A button can also be added straight from the [«Search»](#search) window — the **«To my panel»** button. The «Create my panel» button itself can't be put on your panel.

A button on your panel is a copy of the original: the same caption, icon, tooltip and command; Shift+click works (the button's settings are shared with the original). Your panels are ordinary pyRevit panels: the copies live in the extension folder (`LowLife.tab\MyPanel1.panel` …) and are refreshed from the original buttons on every pyRevit load. Your panels' settings are kept per user in `%APPDATA%\pyRevit\LowLifeFavorites_settings.json`: if the extension was reinstalled, the panels come back by themselves from the second pyRevit load. If a button was removed from LowLife, a message appears when saving and the window shows it greyed out — remove it.

## Help

The last panel of the tab — two small buttons. Visible under any theme, including «My panel».

### About

The button with the logo. Shows the extension version (the commit pyRevit installed it from), the supported Revit versions and your current one, links to the repository and to the [list of parameters](parameters.md). There is also the **«Show greeting when Revit starts»** checkbox (off by default) — see the [«Greeting»](tools-panel.md#greeting) button.

### Feedback

Tell the author about a problem or suggest an improvement: pick the panel and button, describe what happened and tick the consent to personal data processing (without it the message isn't sent). The author's replies are on the «My messages» tab. Details — [feedback-panel.md](feedback-panel.md).

LowLife also sends the author button usage statistics (which button, when, who — no model content) to see what to improve first. Switch it off with the checkbox in the «About» window.

## Selection filter

Selects elements in the active view of only the categories you need — you can safely catch everything with a window.

1. Set it up once: **Shift+click** — a list of the active view's categories opens; tick the ones you need and press «Save».
2. A normal click starts selecting by the saved categories right away: pick elements with clicks and/or a window, only elements of those categories are taken.
3. **Enter** (or right-click → «Finish») — done. The selection stays active in Revit, and you can keep working with it.

## Music

Control music without minimising Revit.

- **Previous track**, **Play / pause**, **Next track** — work like the Windows media keys, i.e. they control whichever player is active right now (a browser, Spotify, Yandex Music, etc.).
- **Quieter**, **Louder** — change the Windows system volume by one step.
