# -*- coding: utf-8 -*-

__title__ = u"Справочник\nкабелей"
__doc__ = (
    u"Ищет в модели справочник кабелей (ключевую спецификацию категории "
    u"«Электрические цепи», на которую ссылается параметр цепи «Проводник») "
    u"и выводит его строки."
)
__author__ = "Pipers"

import clr
from lowlife.i18n import tr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from pyrevit import revit, forms, script

from lowlife.wire_catalog import (
    DEFAULT_KEY_PARAM_NAME, count_circuit_usage, key_name, list_key_schedules,
    param_text, pick_wire_catalogs,
)

doc = revit.doc
output = script.get_output()
TITLE = tr(u"Справочник кабелей")

key_schedules = list_key_schedules(doc)
if not key_schedules:
    forms.alert(tr(u"В модели нет ни одной ключевой спецификации."), title=TITLE, exitscript=True)

catalogs = pick_wire_catalogs(key_schedules)
catalog_ids = set(ks.schedule.Id.IntegerValue for ks in catalogs)

output.print_md(tr(u"## Ключевые спецификации модели"))
summary = []
for ks in key_schedules:
    summary.append([
        output.linkify(ks.schedule.Id, ks.name),
        tr(u"цепи") if ks.is_circuit else tr(u"другая"),
        ks.key_param_name or u"—",
        len(ks.rows),
        tr(u"**да**") if ks.schedule.Id.IntegerValue in catalog_ids else u"",
    ])
output.print_table(
    summary,
    columns=[tr(u"Спецификация"), tr(u"Категория"), tr(u"Ключевой параметр"), tr(u"Строк"), tr(u"Справочник кабелей")],
)

if not catalogs:
    output.print_md(
        tr(u"**Справочник кабелей не найден:** нет ключевой спецификации категории "
        u"«Электрические цепи» со строками.")
    )
    script.exit()

usage = count_circuit_usage(doc, DEFAULT_KEY_PARAM_NAME)

for ks in catalogs:
    fields = ks.field_names()
    output.print_md(tr(u"## {} — {} строк").format(ks.name, len(ks.rows)))
    rows = []
    for row in ks.rows:
        rows.append(
            [key_name(row) or u"", output.linkify(row.Id)]
            + [param_text(row, n) for n in fields]
            + [usage.get(row.Id.IntegerValue, 0)]
        )
    output.print_table(
        rows,
        columns=[tr(u"Ключевое имя"), u"ID"] + fields + [tr(u"Цепей")],
    )
