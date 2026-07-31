# -*- coding: utf-8 -*-
__title__ = "Цепи шлейфов"
__doc__ = (
    "Создаёт по одной электрической цепи на каждый шлейф СОУЭ и подключает "
    "её к своей панели. Шлейф определяется по адресу устройства вида "
    "\"панель.шлейф.номер\" (например 3.1.2)."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms

from lowlife import fire_alarm_settings
from lowlife.fire_alarm_buttons import build_loop_circuits

fire_alarm_settings.set_system("SOUE")

doc = revit.doc

settings = fire_alarm_settings.get_settings_silent()

fire_alarm_settings.require(settings, [
    "workset_param_name", "workset_filter_key",
    "designation_param", "device_address_param", "panel_designation_key",
    "circuit_panel_param", "circuit_number_param", "circuit_number_format",
    "circuit_system_type",
    "load_name_param",
])

build_loop_circuits(doc, settings)
