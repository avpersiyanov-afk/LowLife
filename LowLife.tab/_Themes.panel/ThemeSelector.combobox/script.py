# -*- coding: utf-8 -*-
"""Theme switcher — shows only the buttons of the selected discipline.

Driven entirely by ComboBox event handlers (pyRevit calls these by name;
there is no module-level code that runs on each selection change).
"""
#pylint: disable=C0103,E0401

from lowlife.panel_themes import apply_theme


def __cmb_on_change__(sender, args, ctx):
    """Fired when user selects a different theme."""
    current = sender.Current
    if current:
        apply_theme(current.Name)
