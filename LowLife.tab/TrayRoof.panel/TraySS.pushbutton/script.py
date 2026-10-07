# -*- coding: utf-8 -*-
__title__ = u"Лоток\nСС"
__doc__ = (
    u"Лоток СС (Лотки на кровле, Перфорированный) — переключает активный рабочий набор (по умолчанию содержащий «КНК») и запускает вставку кабельного лотка типа, в имени которого есть «СС_ЛП_1.5_ГЦ». Shift+клик — настройки: текст имени типа лотка и рабочего набора."
)
__author__ = "Pipers"

from pyrevit import revit

from lowlife.cable_tray import run_tray_button

run_tray_button(
    revit.doc, revit.uidoc,
    "TrayRoof", "TraySS", u"Лоток СС (Лотки на кровле)",
    u"СС_ЛП_1.5_ГЦ",
)
