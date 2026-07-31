# -*- coding: utf-8 -*-
__title__ = "Параметры СПС"
__doc__ = "Настройки СПС: рабочий набор, обозначение панели, параметры адреса, цепей и длин."
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms

from lowlife import fire_alarm_settings

fire_alarm_settings.set_system("SPS")

doc = revit.doc

settings = fire_alarm_settings.get_settings_interactive(doc)

if settings is None:
    forms.alert(u"Операция отменена.", exitscript=True)

forms.alert(u"Настройки СПС сохранены.")
