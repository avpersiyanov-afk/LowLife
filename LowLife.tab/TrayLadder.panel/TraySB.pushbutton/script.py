# -*- coding: utf-8 -*-
__title__ = "Лоток\nСБ"
__doc__ = (
    u"Лоток СБ (Лестничный, тип содержит «СБ_ЛЛ_1.5_СЦ») — переключает "
    u"активный рабочий набор на содержащий «КНК» и запускает вставку "
    u"кабельного лотка этого типа."
)
__author__ = "Pipers"

from pyrevit import revit

from lowlife.cable_tray import run_create_cable_tray_button

doc = revit.doc
uidoc = revit.uidoc

run_create_cable_tray_button(doc, uidoc, u"СБ_ЛЛ_1.5_СЦ")
