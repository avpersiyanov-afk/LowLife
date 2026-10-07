# -*- coding: utf-8 -*-
__title__ = u"Лоток\nСС"
__doc__ = (
    u"Лоток СС (Неперфорированный) — делает активным рабочий набор лотков (по умолчанию «КНК») и запускает вставку лотка типа, в имени которого есть (по умолчанию) «СС_ЛН_1.5_СЦ». Shift+клик — общие настройки всех кнопок лотков (рабочий набор и имена типов)."
)
__author__ = "Pipers"

from pyrevit import revit

from lowlife.cable_tray import run_tray_button

run_tray_button(revit.doc, revit.uidoc, "TrayUnperforated", "TraySS")
