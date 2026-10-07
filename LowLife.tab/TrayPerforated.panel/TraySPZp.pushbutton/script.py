# -*- coding: utf-8 -*-
__title__ = u"Лоток\nСПЗп"
__doc__ = (
    u"Лоток СПЗп (Перфорированный) — делает активным рабочий набор лотков (по умолчанию «КНК») и запускает вставку лотка типа, в имени которого есть (по умолчанию) «СПЗп_ЛП_1.5_СЦ». Shift+клик — общие настройки всех кнопок лотков (рабочий набор и имена типов)."
)
__author__ = "Pipers"

from pyrevit import revit

from lowlife.cable_tray import run_tray_button

run_tray_button(revit.doc, revit.uidoc, "TrayPerforated", "TraySPZp")
