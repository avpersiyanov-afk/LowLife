# -*- coding: utf-8 -*-
__title__ = u"Расстановка\nРМ, АМ, МДУ"
__doc__ = (
    u"Ставит компаньона (РМ/АМ/МДУ и т.п.) рядом с каждым базовым объектом "
    u"на активном виде — со смещением и переносом выбранных параметров. "
    u"Пары «рядом с чем ставить -> что ставим» настраиваются через "
    u"Shift+клик по этой кнопке."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms, script as pyrevit_script

from lowlife.geometry import get_document_levels
from lowlife.companion_placement import collect_elements_by_type_ids, place_companions_for_pair
from lowlife import companion_placement_settings as cps

doc = revit.doc
view = doc.ActiveView
output = pyrevit_script.get_output()


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = cps.get_settings_silent(doc)
pairs = cps.require_valid_pairs(settings)

sorted_levels = get_document_levels(doc)


# ------------------------------------------------------------
# РАССТАНОВКА (по каждой настроенной паре)
# ------------------------------------------------------------

total_created = 0
total_duplicate = 0
total_no_point = 0
total_failed = 0
report_rows = []

with revit.Transaction("Place companion devices"):
    for pair in pairs:
        base_type_ids = set(symbol.Id for symbol in pair["base_symbols"])
        base_elements = collect_elements_by_type_ids(doc, view, base_type_ids)

        result = place_companions_for_pair(doc, base_elements, pair, sorted_levels)

        total_created += len(result["created"])
        total_duplicate += result["skipped_duplicate"]
        total_no_point += result["skipped_no_point"]
        total_failed += result["failed"]

        report_rows.append((
            pair["name"], len(base_elements), len(result["created"]),
            result["skipped_duplicate"], result["skipped_no_point"], result["failed"]
        ))


# ------------------------------------------------------------
# ОТЧЁТ
# ------------------------------------------------------------

output.print_md(u"### Расстановка РМ, АМ, МДУ — по парам")
for name, base_count, created_count, dup_count, no_point_count, failed_count in report_rows:
    output.print_md(
        u"- **{}** — базовых объектов на виде: {}, поставлено: {}, уже "
        u"стояло (пропущено): {}, без точки расположения (пропущено): {}, "
        u"не удалось создать: {}".format(
            name, base_count, created_count, dup_count, no_point_count, failed_count
        )
    )

forms.alert(
    u"Готово.\n\n"
    u"Поставлено компаньонов: {}\n"
    u"Уже стояли (пропущено): {}\n"
    u"Без точки расположения (пропущено): {}\n"
    u"Не удалось создать: {}".format(
        total_created, total_duplicate, total_no_point, total_failed
    )
)
