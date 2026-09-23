# -*- coding: utf-8 -*-
__title__ = u"Точки доступа\nна двери"
__doc__ = (
    u"Расставляет элементы точки доступа СКУД на двери выбранных помещений "
    u"активного вида: для каждого помещения выбирается тип точки доступа, "
    u"его состав ставится по мнемосхеме двери. Shift+клик — мнемосхема "
    u"двери и типы точек доступа."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from pyrevit import revit, forms, script as pyrevit_script

from lowlife.geometry import get_document_levels
from lowlife import skud_door_layout as layout
from lowlife import skud_door_placement as sdp
from lowlife import skud_door_placement_settings as sdps
from lowlife.skud_door_rooms_form import show_rooms_table

doc = revit.doc
view = doc.ActiveView
output = pyrevit_script.get_output()


# ------------------------------------------------------------
# НАСТРОЙКИ И ДАННЫЕ
# ------------------------------------------------------------

settings = sdps.get_settings_silent()
access_types = sdps.require_access_types(settings)
slots = settings["slots"]

rooms = sdp.collect_rooms_with_doors(doc, view)
if not rooms:
    forms.alert(
        u"На активном виде не найдено помещений — ни в текущей модели, ни в "
        u"связях (для связей нужен план этажа: помещения берутся с его уровня).",
        exitscript=True
    )

type_names = [t["name"] for t in access_types]
choice = show_rooms_table(rooms, type_names, settings["room_types"])
if choice is None:
    forms.alert(u"Операция отменена.", exitscript=True)

sdps.save_room_types(dict((room.key, choice.get(room.key, u"")) for room in rooms))

selected_rooms = [room for room in rooms if choice.get(room.key)]
if not selected_rooms:
    forms.alert(u"Ни одному помещению не выбран тип точки доступа — расставлять нечего.",
                exitscript=True)

items_by_type = {}
stale_by_type = {}
for access_type in access_types:
    items, stale = layout.composition_items(access_type, slots)
    items_by_type[access_type["name"]] = items
    stale_by_type[access_type["name"]] = stale


# ------------------------------------------------------------
# РАССТАНОВКА
# ------------------------------------------------------------

sorted_levels = get_document_levels(doc)
symbols = sdp.SymbolIndex(doc)
existing = sdp.ExistingIndex(doc)
processed_doors = set()
report = []
totals = {"created": 0, "duplicate": 0, "failed": 0, "doors": 0, "shared": 0}

with revit.Transaction(u"Точки доступа на двери"):
    for room in selected_rooms:
        type_name = choice[room.key]
        items = items_by_type.get(type_name) or []
        row = {"room": room, "type": type_name, "doors": 0, "created": 0, "duplicate": 0,
               "failed": 0, "shared": 0, "missing_types": set(), "failed_names": set()}

        for entry in room.doors:
            if entry.unique_key in processed_doors:
                row["shared"] += 1
                continue
            processed_doors.add(entry.unique_key)
            row["doors"] += 1
            result = sdp.place_access_point(doc, entry, items, symbols, sorted_levels, existing)
            row["created"] += result["created"]
            row["duplicate"] += result["duplicate"]
            row["failed"] += result["failed"]
            row["missing_types"].update(result["missing_types"])
            row["failed_names"].update(result["failed_names"])

        for key in ("created", "duplicate", "failed", "doors", "shared"):
            totals[key] += row[key]
        report.append(row)


# ------------------------------------------------------------
# ОТЧЁТ
# ------------------------------------------------------------

output.print_md(u"### Точки доступа на двери")
for row in report:
    room = row["room"]
    title = u"{} {}".format(room.number, room.name).strip() or u"(без номера)"
    line = u"- **{}** — тип «{}»: дверей обработано {}, поставлено {}, уже стояло {}, не удалось {}".format(
        title, row["type"], row["doors"], row["created"], row["duplicate"], row["failed"]
    )
    if row["shared"]:
        line += u"; дверей пропущено (уже обработаны с другим помещением): {}".format(row["shared"])
    if row["missing_types"]:
        line += u"; **нет в проекте типоразмеров**: {}".format(u", ".join(sorted(row["missing_types"])))
    if row["failed_names"]:
        line += u"; не удалось вставить: {}".format(u", ".join(sorted(row["failed_names"])))
    output.print_md(line)

used_types = set(row["type"] for row in report)
for type_name in sorted(used_types):
    stale = stale_by_type.get(type_name) or []
    if stale:
        output.print_md(
            u"- Тип «{}»: пропущены места, чьё семейство убрано с места на мнемосхеме: {}".format(
                type_name, u", ".join(u"{} : {}".format(f, t) for _k, f, t in stale)
            )
        )

forms.alert(
    u"Готово.\n\n"
    u"Дверей обработано: {}\n"
    u"Поставлено элементов: {}\n"
    u"Уже стояли (пропущено): {}\n"
    u"Не удалось вставить: {}\n"
    u"Дверей пропущено (общие с другим помещением): {}\n\n"
    u"Подробности — в окне вывода.".format(
        totals["doors"], totals["created"], totals["duplicate"], totals["failed"], totals["shared"]
    )
)
