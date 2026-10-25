[Русский](../circuits-panels.md) | **English**

# Electrical circuits — general buttons

Buttons of the CircuitsSKUD, CircuitsGeneric and CircuitsDelete panels. SCS circuits, fire alarm/fire automation loop circuits and isolator circuits are described on their systems' pages: [SCS](scs-panel.md#scs-circuits-circuitsscspanel--buildcircuitsscs), [fire alarm/voice alarm/fire automation](fire-alarm-panels.md).

All these buttons are gathered on the ribbon under the «Electrical circuits» theme (the «Theme» list on the LowLife panel). Changes are undone with **Ctrl+Z**.

## ACS circuits

Builds ACS circuits by hand: a separate circuit from the controller to each device («home run», no intermediate nodes).

1. Press the button.
2. Select the controller and the devices **together**, with a window and/or clicks, in any order; confirm with Enter or «Finish». The controller is the element of the «Electrical Equipment» category — there must be exactly one in the selection. Link elements can't be selected.
3. Choose the circuit type — Security is first in the list by default.

At the end — how many devices were selected, how many circuits were created and how many errors there were; error details are in the pyRevit output window. A common error is a device that already belongs to another circuit: delete such circuits first (the [«Delete circuits in view»](#delete-circuits-in-view) button).

## Circuit (general)

Builds «panel → devices» circuits for any system — everything that depends on the discipline is set in the settings.

1. Set the button up once (**Shift+click**, see below).
2. Press the button and select the panel and devices together — with a window and/or clicks, in any order. The panel is the element of the «Electrical Equipment» category, exactly one. Annotations, links, grids, levels, text, detail lines and generic models don't get into the selection even if the window catches them.

What the button writes:

- **circuit type** — from the settings; if empty there — from the device connector (Data as the fallback);
- **cable** — a cable catalog row into the circuit's built-in «Wire» parameter, if one is chosen in the settings (optional; about the catalog — [cable-catalog.md](cable-catalog.md));
- **«Load Name»** — assembled from the connected device's parameters by a list with a separator (for example «Розетка.Каб-1»). For each parameter the instance value is taken first; if it's empty — the type value.

Settings (**Shift+click**):

| Field | What it sets |
|---|---|
| Electrical circuit type | Data, Security, Communication, etc. — picked from a list or typed |
| Cable catalog row marker | optional: a parameter by which the button tells catalog rows from other elements |
| Cable for circuits | optional: the catalog row set on all circuits |
| Device parameters for the load name | a comma-separated list of parameter names, in order |
| Load name separator | the text between the values, a dot by default |
| How to build circuits | **a separate circuit per device** (each with its own load name) or **all devices in one circuit** (the load name isn't filled in) |

## Delete circuits in view

Deletes every electrical circuit that has at least one element — a device or a panel — visible in the active view.

Needed to remove stray or test circuits: Revit won't add an element that already belongs to another circuit, so the circuit-building buttons (loops, SCS, ACS) give an error on such elements.

1. Open a view where the elements you need are visible.
2. Press the button — the output window lists the circuits (by «Circuit Number», if set).
3. Confirm the deletion.

## Highlight unconnected

Highlights in red, in the active view, every element with electrical connectors (devices, panels, isolators, etc.) that has no circuit yet — handy so as not to miss a device.

- The highlight doesn't get in the way: circuits can be created right away with any LowLife button or Revit's own command. As soon as an element gets a circuit, its highlight goes away by itself.
- Running it again in the same view recalculates the highlight (for example, after devices were added to the view).
- **Shift+click** — clear the highlight the button placed in the active view without waiting for circuits.
