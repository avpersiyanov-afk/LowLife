# -*- coding: utf-8 -*-
from pyrevit import revit, script, forms, EXEC_PARAMS
from Autodesk.Revit.DB import FilteredElementCollector
from Autodesk.Revit.DB.Electrical import ElectricalSystem
from lowlife import circuit_load

__title__ = u"Нагрузка\nцепей"
__doc__ = u"Показывает нагрузку, запас по току и падение напряжения электрических цепей."

if EXEC_PARAMS.config_mode:
    forms.alert(u"Настройки рассчитываемого кабеля задаются в коде проекта: section_mm2 и resistance_ohm_mm2_m.")
    script.exit()

systems = list(FilteredElementCollector(revit.doc).OfClass(ElectricalSystem).WhereElementIsNotElementType())
records = [circuit_load.circuit_record(system, {"section_mm2": 2.5}) for system in systems]
records.sort(key=lambda row: (row["panel"], row["number"], row["id"] or 0))
if not records:
    forms.alert(u"В проекте нет электрических цепей.", exitscript=True)
output = script.get_output()
output.print_md(u"## Нагрузка электрических цепей")
summary = circuit_load.summarize(records)
output.print_md(u"Всего цепей: **{}**, суммарная нагрузка: **{:.0f} VA**, перегружено: **{}**, падение выше 5%: **{}**".format(
    len(records), float(summary["load_va"]),
    summary["overloaded"], summary["drop_over_5"]))
output.print_table([[(r["number"] or str(r["id"])), r["panel"], r["name"], r["element_count"],
                     "{:.0f}".format(r["load_va"]), "{:.1f}".format(r["current_a"] or 0),
                     "{:.1f}".format(r["length_m"] or 0), r["wire"] or u"—",
                     "{:.1f}".format(r["reserve_a"]) if r["reserve_a"] is not None else u"—",
                     "{:.2f}%".format(r["voltage_drop_pct"]) if r["voltage_drop_pct"] is not None else u"—"]
                    for r in records],
                   columns=[u"Цепь", u"Панель", u"Имя", u"Элементы", u"Нагрузка VA", u"Ток A", u"Длина м", u"Кабель", u"Запас A", u"Падение"])
