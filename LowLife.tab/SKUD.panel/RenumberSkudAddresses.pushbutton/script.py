# -*- coding: utf-8 -*-
__title__ = "Адреса узлов\nСКУД"
__doc__ = (
    "Нумерует адреса узлов трассы СКУД по этажу, начиная от контроллеров/"
    "стояков, и записывает контроллерам и устройствам ближайший адресованный "
    "узел маршрута."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms

from lowlife.params import get_string_param
from lowlife.scs import clear_stray_address_params, is_excluded_device
from lowlife.scs_circuits import norm
from lowlife.skud import is_controller
from lowlife.route_addressing import (
    renumber_addresses, write_addresses, write_nearest_nodes, MM_IN_FOOT
)
from lowlife import skud_settings
from lowlife.skud_settings import get_settings_silent

doc = revit.doc
view = doc.ActiveView


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

skud_settings.require(settings, [
    "route_type_id", "riser_type_id",
    "workset_filter_key", "workset_param_name",
    "controller_workset_keyword", "controller_type_keyword",
    "circuit_panel_param", "nearest_segment_param"
])

ROUTE_TYPE_ID = ElementId(int(settings["route_type_id"]))
RISER_TYPE_ID = ElementId(int(settings["riser_type_id"]))

ADDR_PARAM = settings["addr_param_name"]
ADDR_PREV_PARAM = settings["addr_prev_param_name"]

CONTROLLER_WORKSET_KEYWORD = settings["controller_workset_keyword"]
CONTROLLER_TYPE_KEYWORD = settings["controller_type_keyword"]
WORKSET_PARAM_NAME = settings["workset_param_name"]
EXCLUDED_DEVICE_KEYWORDS = settings["excluded_device_keywords"]
CIRCUIT_PANEL_PARAM = settings["circuit_panel_param"]

config = {
    "route_type_id": ROUTE_TYPE_ID,
    "riser_type_id": RISER_TYPE_ID,
    "addr_param_name": ADDR_PARAM,
    "addr_prev_param_name": ADDR_PREV_PARAM,
    "nearest_segment_param": settings["nearest_segment_param"],
    "panel_keywords": settings["panel_keywords"],
    "panel_exclude_keywords": settings["panel_exclude_keywords"],
    "workset_param_name": WORKSET_PARAM_NAME,
    "workset_filter_key": settings["workset_filter_key"],
}

# Нумеруем всегда заново — как и «Адреса узлов» в СКС: адрес зависит от
# порядка обхода дерева, поэтому частичная нумерация давала бы разрыв
# между старыми и новыми адресами.
RENUMBER_EXISTING = True


# ------------------------------------------------------------
# ОЧИСТКА "ЧУЖИХ" АДРЕСОВ
# ------------------------------------------------------------

with revit.Transaction("Clear stray SKUD route addresses"):
    stray_cleared = clear_stray_address_params(
        doc, [ADDR_PARAM, ADDR_PREV_PARAM], set([ROUTE_TYPE_ID, RISER_TYPE_ID])
    )


# ------------------------------------------------------------
# НУМЕРАЦИЯ
# ------------------------------------------------------------

result = renumber_addresses(doc, view, config, RENUMBER_EXISTING)

if result.get("error"):
    forms.alert(result["error"], exitscript=True)

with revit.Transaction("Renumber SKUD Route Addresses"):
    changed, skipped = write_addresses(result["route_points"], config, RENUMBER_EXISTING)


# ------------------------------------------------------------
# БЛИЖАЙШИЙ УЗЕЛ ДЛЯ КОНТРОЛЛЕРОВ И УСТРОЙСТВ
# ------------------------------------------------------------

all_equipment = FilteredElementCollector(doc) \
    .OfCategory(BuiltInCategory.OST_ElectricalEquipment) \
    .WhereElementIsNotElementType() \
    .ToElements()

controllers = [
    e for e in all_equipment
    if is_controller(e, WORKSET_PARAM_NAME, CONTROLLER_WORKSET_KEYWORD, CONTROLLER_TYPE_KEYWORD)
]

controllers_by_name = {}
for c in controllers:
    cname = norm(c.Name)
    if cname:
        controllers_by_name.setdefault(cname, c)

all_circuits = FilteredElementCollector(doc) \
    .OfCategory(BuiltInCategory.OST_ElectricalCircuit) \
    .WhereElementIsNotElementType() \
    .ToElements()

devices_by_id = {}
for c in all_circuits:
    panel_name = norm(get_string_param(c, CIRCUIT_PANEL_PARAM))
    controller_el = controllers_by_name.get(panel_name)
    if controller_el is None:
        continue

    try:
        raw_devs = [x for x in c.Elements if x.Id != controller_el.Id]
    except:
        continue

    for d in raw_devs:
        if is_excluded_device(d, EXCLUDED_DEVICE_KEYWORDS):
            continue
        devices_by_id[d.Id.IntegerValue] = d

targets = list(controllers) + list(devices_by_id.values())

with revit.Transaction("Write SKUD Nearest Segment"):
    nearest_written = write_nearest_nodes(doc, result["route_points"], targets, config)


# ------------------------------------------------------------
# ОТЧЁТ
# ------------------------------------------------------------

def mm(v):
    return u"{:.0f}".format(v * MM_IN_FOOT)


def category_label(n):
    if n["is_panel"]:
        return u"Контроллер"
    if n["is_riser"]:
        return u"Стояк"
    return u"Маршрут"


all_points_by_id = result["all_points_by_id"]


def parent_label(n):
    pid = n.get("parent_id")
    if pid is None:
        return u"-"
    parent_obj = all_points_by_id.get(pid)
    if parent_obj is None:
        return u"ID {}".format(pid)
    return u"{} ({}, ID {})".format(
        parent_obj.get("addr") or u"без адреса", category_label(parent_obj), pid
    )


from pyrevit import script as pyrevit_script
output = pyrevit_script.get_output()

output.print_md(u"## Адреса узлов СКУД — подробный отчёт")

far_ids = set(s["id"] for s in result["far_sources"])
panels = result["panels"]
risers = result["risers"]

if panels or risers:
    output.print_md(u"### Контроллеры и стояки ({})".format(len(panels) + len(risers)))
    roots_table = []
    for n in panels + risers:
        roots_table.append([
            n["id"], category_label(n), mm(n["point"][0]), mm(n["point"][1]),
            u"Слишком далеко — не корень" if n["id"] in far_ids else u"Корень"
        ])
    output.print_table(
        table_data=roots_table,
        columns=[u"ID", u"Категория", u"X, мм", u"Y, мм", u"Статус"]
    )

ordered_routes = result["ordered_routes"]

output.print_md(u"### Узлы маршрута — в порядке нумерации ({})".format(len(ordered_routes)))
nodes_table = []
for i, n in enumerate(ordered_routes, start=1):
    nodes_table.append([
        i, n["id"], mm(n["point"][0]), mm(n["point"][1]),
        n.get("classification") or u"-",
        n.get("addr") or u"-",
        n.get("write_value") or u"-",
        parent_label(n)
    ])
output.print_table(
    table_data=nodes_table,
    columns=[u"#", u"ID", u"X, мм", u"Y, мм", u"Классификация", u"Адрес", u"Предыдущий адрес", u"Родитель"]
)

root_sources = result["root_sources"]

forms.alert(
    u"Готово.\n\n"
    u"Уровень: {}\n"
    u"Код этажа: {}\n"
    u"Корень: {}\n\n"
    u"Узлов маршрута всего: {}\n"
    u"Изменено: {}\n"
    u"Очищено чужих адресов: {}\n"
    u"Отброшено как слишком далёкие: {}\n\n"
    u"Контроллеров: {}\n"
    u"Устройств в цепях: {}\n"
    u"Записано «Ближайший узел маршрута»: {}\n\n"
    u"Подробности — в окне вывода pyRevit.".format(
        result["level_name"],
        result["floor_code"],
        (u"Контроллер" if root_sources[0]["is_panel"] else u"Стояк") if root_sources else u"Нет (все далеко)",
        len(result["route_points"]),
        len(changed),
        len(stray_cleared),
        len(result["far_sources"]),
        len(controllers),
        len(devices_by_id),
        nearest_written
    )
)
