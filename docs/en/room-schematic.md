[Русский](../room-schematic.md) | **English**

# Riser diagram draft (BuildRoomSchematic)

A button on the **Diagrams** panel (Schematic). Builds a rough draft of a riser diagram **by rooms**, not by placed devices (as the «Riser diagram» buttons for SCS/ACS/CCTV/fire alarm do). Handy at the start of a project, when there are no devices in the model yet but the diagram already has to be shown.

> [!WARNING]
> One of the diagram-building buttons — it has had little testing. The result can be undone with **Ctrl+Z**.

## How to use

1. Press the button. One window opens: floors on the left, the selected floor's rooms on the right (from the model and all links).
2. In the **«On diagram»** column, type how the room should be shown on the diagram. Empty — the room won't be on the diagram.
   - The same label on several rooms of a floor makes **one shared box** («Apartments», «Common areas», etc.).
   - You can select several rows and give them all a label at once.
3. Repeat for the other floors. Shortcuts:
   - a floor with the same set of rooms as one already filled in (a typical residential floor) **fills in by itself**;
   - labels can be copied from any floor — matched by room names.
4. Confirm — the button builds the diagram.

## Result

A drafting view «Структурная схема (черновик)»: a frame per floor and inside it a labelled box per label. There are no families or connection lines — the diagram is finished by hand from there.

Labels are remembered between runs, but the view itself is **rebuilt from scratch every time** — manual edits on it are lost on a re-run. If you've already started working on the diagram, rename or duplicate the view before running again.
