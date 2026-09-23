# -*- coding: utf-8 -*-
__title__ = u"Точки доступа\nна двери"
__doc__ = (
    u"Расставляет элементы точки доступа СКУД на двери выбранных помещений "
    u"активного вида: для каждого помещения выбирается группа (из неё — "
    u"только типы семейств), расстановка — по мнемосхеме двери. "
    u"Shift+клик — мнемосхема двери."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from pyrevit import revit, forms, script as pyrevit_script

from lowlife.geometry import get_document_levels
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
slots = sdps.require_active_slots(settings)

rooms = sdp.collect_rooms_with_doors(doc, view)
if not rooms:
    forms.alert(
        u"На активном виде не найдено помещений — ни в текущей модели, ни в "
        u"связях (для связей нужен план этажа: помещения берутся с его уровня).",
        exitscript=True
    )

group_types = sdp.list_model_group_types(doc)
if not group_types:
    forms.alert(
        u"В проекте нет модельных групп. Соберите группу с составом точки "
        u"доступа (считыватель, замок, ...) и запустите кнопку снова.",
        exitscript=True
    )

choice = show_rooms_table(rooms, sorted(group_types.keys()), settings["room_groups"])
if choice is None:
    forms.alert(u"Операция отменена.", exitscript=True)

sdps.save_room_groups(dict((room.key, choice.get(room.key, u"")) for room in rooms))

selected_rooms = [room for room in rooms if choice.get(room.key)]
if not selected_rooms:
    forms.alert(u"Ни одному помещению не выбрана группа — расставлять нечего.", exitscript=True)


# ------------------------------------------------------------
# СОСТАВ ГРУПП (вне основной транзакции — может временно вставлять группу)
# ------------------------------------------------------------

members_by_group = {}
for group_name in set(choice[room.key] for room in selected_rooms):
    members_by_group[group_name] = sdp.read_group_members(doc, group_types[group_name])


# ------------------------------------------------------------
# РАССТАНОВКА
# ------------------------------------------------------------

sorted_levels = get_document_levels(doc)
existing = sdp.ExistingIndex(doc)
processed_doors = set()
report = []
totals = {"created": 0, "duplicate": 0, "failed": 0, "doors": 0, "shared": 0}

with revit.Transaction(u"Точки доступа на двери"):
    for room in selected_rooms:
        group_name = choice[room.key]
        members = members_by_group.get(group_name) or []
        row = {"room": room, "group": group_name, "doors": 0, "created": 0, "duplicate": 0,
               "failed": 0, "shared": 0, "unmatched": set(), "failed_names": set(),
               "empty_group": not members}

        for entry in room.doors:
            if entry.unique_key in processed_doors:
                row["shared"] += 1
                continue
            processed_doors.add(entry.unique_key)
            if not members:
                continue
            row["doors"] += 1
            result = sdp.place_access_point(doc, entry, members, slots, sorted_levels, existing)
            row["created"] += result["created"]
            row["duplicate"] += result["duplicate"]
            row["failed"] += result["failed"]
            row["unmatched"].update(result["unmatched"])
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
    line = u"- **{}** — группа «{}»: дверей обработано {}, поставлено {}, уже стояло {}, не удалось {}".format(
        title, row["group"], row["doors"], row["created"], row["duplicate"], row["failed"]
    )
    if row["empty_group"]:
        line += u"; **в группе нет семейств (не удалось прочитать состав)**"
    if row["shared"]:
        line += u"; дверей пропущено (уже обработаны с другим помещением): {}".format(row["shared"])
    if row["unmatched"]:
        line += u"; нет места на мнемосхеме для: {}".format(u", ".join(sorted(row["unmatched"])))
    if row["failed_names"]:
        line += u"; не удалось вставить: {}".format(u", ".join(sorted(row["failed_names"])))
    output.print_md(line)

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
