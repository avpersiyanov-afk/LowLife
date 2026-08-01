# -*- coding: utf-8 -*-
__title__ = "Длины\nшлейфов"
__doc__ = (
    "Считает длину каждого шлейфа СОУЭ по координатам устройств (ветви от "
    "изоляторов не возвращаются назад), записывает её в цепь, маркирует "
    "устройства и проставляет им предыдущий адрес."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms

from lowlife import fire_alarm_settings
from lowlife.fire_alarm_buttons import calc_loop_lengths

fire_alarm_settings.set_system("SOUE")

doc = revit.doc

settings = fire_alarm_settings.get_settings_silent()

fire_alarm_settings.require(settings, [
    "workset_param_name", "workset_filter_key",
    "designation_param", "device_address_param", "panel_designation_key",
    "circuit_number_param", "circuit_number_format",
    "length_coef", "wire_length_param",
])

calc_loop_lengths(doc, settings)
