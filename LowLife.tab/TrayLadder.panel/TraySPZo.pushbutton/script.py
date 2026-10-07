# -*- coding: utf-8 -*-
__title__ = u"Лоток\nСПЗо"
__doc__ = (
    u"Лоток СПЗо (Лестничный) — переключает активный рабочий набор (по умолчанию содержащий «КНК») и запускает вставку кабельного лотка типа, в имени которого есть «СПЗо_ЛЛ_1.5_СЦ». Shift+клик — настройки: текст имени типа лотка и рабочего набора."
)
__author__ = "Pipers"

from pyrevit import revit

from lowlife.cable_tray import run_tray_button

run_tray_button(
    revit.doc, revit.uidoc,
    "TrayLadder", "TraySPZo", u"Лоток СПЗо (Лестничный лоток)",
    u"СПЗо_ЛЛ_1.5_СЦ",
)
