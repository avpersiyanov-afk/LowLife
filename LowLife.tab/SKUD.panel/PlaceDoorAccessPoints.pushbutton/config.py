# -*- coding: utf-8 -*-
"""Shift+клик по кнопке «Точки доступа на двери» — мнемосхема двери."""

from pyrevit import revit, forms

from lowlife import skud_door_placement_settings as sdps

doc = revit.doc

slots = sdps.get_settings_interactive(doc)

if slots is None:
    forms.alert(u"Операция отменена.", exitscript=True)

forms.alert(u"Настройки «Точки доступа на двери» сохранены.")
