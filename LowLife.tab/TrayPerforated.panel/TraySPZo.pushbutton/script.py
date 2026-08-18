# -*- coding: utf-8 -*-
__title__ = "Лоток\nСПЗо"
__doc__ = (
    u"Лоток СПЗо (Перфорированный, тип содержит «СПЗо_ЛП_1.5_СЦ») — "
    u"переключает активный рабочий набор на содержащий «КНК» и запускает "
    u"вставку кабельного лотка этого типа."
)
__author__ = "Pipers"

from pyrevit import revit

from lowlife.cable_tray import run_create_cable_tray_button

doc = revit.doc
uidoc = revit.uidoc

run_create_cable_tray_button(doc, uidoc, u"СПЗо_ЛП_1.5_СЦ")
