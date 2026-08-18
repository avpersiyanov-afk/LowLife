# -*- coding: utf-8 -*-
__title__ = "Лоток\nСПЗп"
__doc__ = (
    u"Лоток СПЗп (Лестничный, тип содержит «СПЗп_ЛЛ_1.5_СЦ») — переключает "
    u"активный рабочий набор на содержащий «КНК» и запускает вставку "
    u"кабельного лотка этого типа."
)
__author__ = "Pipers"

from pyrevit import revit

from lowlife.cable_tray import run_create_cable_tray_button

doc = revit.doc
uidoc = revit.uidoc

run_create_cable_tray_button(doc, uidoc, u"СПЗп_ЛЛ_1.5_СЦ")
