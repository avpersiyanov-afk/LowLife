# -*- coding: utf-8 -*-
__title__ = "Лоток\nСС"
__doc__ = (
    u"Лоток СС (Лотки на кровле, Перфорированный, тип содержит "
    u"«СС_ЛП_1.5_ГЦ») — переключает активный рабочий набор на содержащий "
    u"«КНК» и запускает вставку кабельного лотка этого типа."
)
__author__ = "Pipers"

from pyrevit import revit

from lowlife.cable_tray import run_create_cable_tray_button

doc = revit.doc
uidoc = revit.uidoc

run_create_cable_tray_button(doc, uidoc, u"СС_ЛП_1.5_ГЦ")
