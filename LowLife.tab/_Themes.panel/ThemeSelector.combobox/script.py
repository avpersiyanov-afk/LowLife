# -*- coding: utf-8 -*-
"""Theme switcher — shows only the buttons of the selected discipline.

Driven entirely by ComboBox event handlers (pyRevit calls these by name;
there is no module-level code that runs on each selection change).
The choice is remembered (panel_themes.save_selected) — startup.py
puts it back after pyRevit rebuilds the ribbon (start, reload, update).
"""
#pylint: disable=C0103,E0401

from lowlife.panel_themes import apply_theme, save_selected


def __cmb_on_change__(sender, args, ctx):
    """Fired when user selects a different theme."""
    current = sender.Current
    if current:
        apply_theme(current.Name)
        try:
            save_selected(current.Name)
        except Exception:
            pass
