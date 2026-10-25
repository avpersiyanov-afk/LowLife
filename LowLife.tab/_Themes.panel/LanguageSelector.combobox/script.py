# -*- coding: utf-8 -*-
"""Language switcher — relabels the LowLife ribbon in Russian or English.

Driven by the ComboBox event handler (pyRevit calls it by name). The choice is
remembered (i18n.save); startup.py puts it back after pyRevit rebuilds the ribbon.
"""
#pylint: disable=C0103,E0401

from lowlife.ribbon_language import switch


def __cmb_on_change__(sender, args, ctx):
    """Fired when the user picks another language."""
    current = sender.Current
    if current:
        try:
            switch(current.Name)
        except Exception:
            pass
