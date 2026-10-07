# -*- coding: utf-8 -*-
__title__ = u"Лоток\nСПЗп"
__doc__ = (
    u"Лоток СПЗп (Проволочный) — переключает активный рабочий набор (по умолчанию содержащий «КНК») и запускает вставку кабельного лотка типа, в имени которого есть «СПЗп_ЛВ_1.5_СЦ». Shift+клик — настройки: текст имени типа лотка и рабочего набора."
)
__author__ = "Pipers"

from pyrevit import revit

from lowlife.cable_tray import run_tray_button

run_tray_button(
    revit.doc, revit.uidoc,
    "TrayWire", "TraySPZp", u"Лоток СПЗп (Проволочный лоток)",
    u"СПЗп_ЛВ_1.5_СЦ",
)
