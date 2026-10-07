# -*- coding: utf-8 -*-
__title__ = u"Лоток\nСПЗп"
__doc__ = (
    u"Лоток СПЗп (Лотки на кровле, Перфорированный) — переключает активный рабочий набор (по умолчанию содержащий «КНК») и запускает вставку кабельного лотка типа, в имени которого есть «СПЗп_ЛП_1.5_ГЦ». Shift+клик — настройки: текст имени типа лотка и рабочего набора."
)
__author__ = "Pipers"

from pyrevit import revit

from lowlife.cable_tray import run_tray_button

run_tray_button(
    revit.doc, revit.uidoc,
    "TrayRoof", "TraySPZp", u"Лоток СПЗп (Лотки на кровле)",
    u"СПЗп_ЛП_1.5_ГЦ",
)
