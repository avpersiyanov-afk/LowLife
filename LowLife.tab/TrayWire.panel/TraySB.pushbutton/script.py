# -*- coding: utf-8 -*-
__title__ = u"Лоток\nСБ"
__doc__ = (
    u"Лоток СБ (Проволочный) — переключает активный рабочий набор (по умолчанию содержащий «КНК») и запускает вставку кабельного лотка типа, в имени которого есть «СБ_ЛВ_1.5_СЦ». Shift+клик — настройки: текст имени типа лотка и рабочего набора."
)
__author__ = "Pipers"

from pyrevit import revit

from lowlife.cable_tray import run_tray_button

run_tray_button(
    revit.doc, revit.uidoc,
    "TrayWire", "TraySB", u"Лоток СБ (Проволочный лоток)",
    u"СБ_ЛВ_1.5_СЦ",
)
