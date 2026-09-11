# -*- coding: utf-8 -*-
"""Shift+клик по кнопке «Расстановка РМ, АМ, МДУ» — настройка пар расстановки."""

from pyrevit import revit, forms

from lowlife import companion_placement_settings as cps

doc = revit.doc

settings = cps.get_settings_interactive(doc)

if settings is None:
    forms.alert(u"Операция отменена.", exitscript=True)

forms.alert(u"Настройки «Расстановка РМ, АМ, МДУ» сохранены.")
