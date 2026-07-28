# -*- coding: utf-8 -*-
__title__ = "Адреса узлов"
__doc__ = "Нумерует адреса узлов маршрута по этажу, начиная от панелей/стояков"
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms

from lowlife.geometry import get_point
from lowlife.params import get_string_param, set_string_param
from lowlife.scs import classify_element, clear_stray_address_params
from lowlife import scs_settings
from lowlife.scs_settings import get_settings_silent
from lowlife.scs_addressing import (
    pt2, add_neighbor, get_floor_code_from_view, classify_point,
    find_nearest_real_node, find_best_real_node_for_offset,
    point_to_segment_distance_xy, line_parameter_xy
)

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

MM_IN_FOOT = 304.8
STRICT = 30.0 / MM_IN_FOOT
OFFSET = 210.0 / MM_IN_FOOT
MARKED_TOL = 150.0 / MM_IN_FOOT
END_TOL = 50.0 / MM_IN_FOOT


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

scs_settings.require(settings, ["route_type_id", "riser_type_id"])
# Имена параметров (addr_param_name, addr_prev_param_name) здесь не
# проверяются — их наличие/привязку в проекте проверяет и чинит кнопка
# «Параметры СКС» (SetupParameters).

ADDR_PARAM = settings["addr_param_name"]
ADDR_PREV_PARAM = settings["addr_prev_param_name"]
PANEL_KEYWORDS = settings["panel_keywords"]
PANEL_EXCLUDE_KEYWORDS = settings["panel_exclude_keywords"]

ROUTE_TYPE_ID = ElementId(int(settings["route_type_id"]))
RISER_TYPE_ID = ElementId(int(settings["riser_type_id"]))

choice = forms.alert(
    u"Перенумеровать все существующие адреса заново, "
    u"или пронумеровать только узлы с пустым адресом?",
    title=u"Режим нумерации",
    options=[u"Перенумеровать все", u"Только новые"]
)

if not choice:
    forms.alert(u"Операция отменена.", exitscript=True)

RENUMBER_EXISTING = (choice == u"Перенумеровать все")


# ------------------------------------------------------------
# ОЧИСТКА "ЧУЖИХ" АДРЕСОВ
# ------------------------------------------------------------
# У элементов, которые больше не являются маркерами маршрута/стояка
# (например, устройств, оставшихся с прежних запусков или после
# разделения на отдельные семейства панель/устройство/маршрут), могли
# остаться значения ADDR_PARAM/ADDR_PREV_PARAM. Если реальный узел
# маршрута сошлётся на такой "чужой" адрес, путь до него не найдётся —
# поэтому чистим их перед сбором элементов.

with revit.Transaction("Clear stray route addresses"):
    stray_cleared = clear_stray_address_params(
        doc, [ADDR_PARAM, ADDR_PREV_PARAM], set([ROUTE_TYPE_ID, RISER_TYPE_ID])
    )


# ------------------------------------------------------------
# СБОР ЭЛЕМЕНТОВ
# ------------------------------------------------------------

collector = FilteredElementCollector(doc, view.Id) \
    .OfCategory(BuiltInCategory.OST_GenericModel) \
    .WhereElementIsNotElementType()

lines = []
points = []

for el in collector:
    loc = el.Location

    if isinstance(loc, LocationCurve):
        c = loc.Curve
        lines.append({
            "id": el.Id.IntegerValue,
            "element": el,
            "p1": pt2(c.GetEndPoint(0)),
            "p2": pt2(c.GetEndPoint(1))
        })
        continue

    pt = get_point(el)
    if pt is None:
        continue

    type_id = el.GetTypeId()
    is_route = (type_id == ROUTE_TYPE_ID)
    is_riser = (type_id == RISER_TYPE_ID)
    is_panel = classify_element(el, [("panel", PANEL_KEYWORDS, PANEL_EXCLUDE_KEYWORDS)]) == "panel"

    if not (is_route or is_riser or is_panel):
        continue

    points.append({
        "id": el.Id.IntegerValue,
        "element": el,
        "point": pt2(pt),
        "is_route": is_route,
        "is_riser": is_riser,
        "is_panel": is_panel,
        "addr_original": get_string_param(el, ADDR_PARAM),
        "addr": get_string_param(el, ADDR_PARAM),
        "classification": None,
        "nearest_line_id": None,
        "neighbor_ids": [],
        "parent_id": None,
        "parent_addr": None,
        "write_value": None
    })

if not lines:
    forms.alert(u"Не найдены линейные элементы на активном виде.", exitscript=True)


# ------------------------------------------------------------
# КЛАССИФИКАЦИЯ И ГРАФ
# ------------------------------------------------------------

floor_code, level_name = get_floor_code_from_view(view)

for p in points:
    classify_point(p, lines, STRICT, OFFSET, MARKED_TOL, END_TOL)

all_points_by_id = dict((p["id"], p) for p in points)
lines_by_id = dict((l["id"], l) for l in lines)

panels = [p for p in points if p["is_panel"]]
risers = [p for p in points if p["is_riser"]]
route_points = [p for p in points if p["is_route"]]

real_nodes = [p for p in route_points if p["classification"] in ("NODE_STRICT", "NODE_ON_LINE", "NODE_NEAR_ENDPOINT")]
offset_nodes = [p for p in route_points if p["classification"] == "OFFSET_MARKER"]
unconnected_nodes = [p for p in route_points if p["classification"] == "UNCONNECTED"]

if not route_points:
    forms.alert(u"Не найдены узлы маршрута выбранного типа.", exitscript=True)

for line in lines:
    pts_on_line = []

    for node in real_nodes:
        d, t_raw = point_to_segment_distance_xy(node["point"], line["p1"], line["p2"])
        if d <= OFFSET and -0.05 <= t_raw <= 1.05:
            t = line_parameter_xy(node["point"], line["p1"], line["p2"])
            pts_on_line.append((t, node))

    pts_on_line.sort(key=lambda x: x[0])

    for i in range(len(pts_on_line) - 1):
        n1 = pts_on_line[i][1]
        n2 = pts_on_line[i + 1][1]
        if n1["id"] != n2["id"]:
            add_neighbor(n1, n2)


# ------------------------------------------------------------
# КОРНИ (ПАНЕЛИ/СТОЯКИ)
# ------------------------------------------------------------

root_sources = panels if panels else risers

root_real_nodes = []

for src in root_sources:
    best_real = find_best_real_node_for_offset(src, lines_by_id, real_nodes, OFFSET)

    if best_real is None:
        best_real, _ = find_nearest_real_node(src, real_nodes)

    if best_real and best_real["parent_id"] is None:
        best_real["parent_id"] = src["id"]
        root_real_nodes.append(best_real)

root_ids = set()
unique_roots = []
for n in root_real_nodes:
    if n["id"] not in root_ids:
        root_ids.add(n["id"])
        unique_roots.append(n)


# ------------------------------------------------------------
# BFS
# ------------------------------------------------------------

queue = []
visited = set()

for root in unique_roots:
    queue.append(root)
    visited.add(root["id"])

idx = 0
ordered_real_nodes = []

while idx < len(queue):
    current = queue[idx]
    idx += 1
    ordered_real_nodes.append(current)

    neighbor_objs = [all_points_by_id[nid] for nid in current["neighbor_ids"] if nid in all_points_by_id]
    neighbor_objs.sort(key=lambda n: (n["point"][0], n["point"][1], n["id"]))

    for nb in neighbor_objs:
        if nb["id"] not in visited:
            visited.add(nb["id"])
            nb["parent_id"] = current["id"]
            queue.append(nb)


# ------------------------------------------------------------
# ПОРЯДОК НУМЕРАЦИИ
# ------------------------------------------------------------

ordered_routes = []
added_ids = set()

for n in ordered_real_nodes:
    if n["id"] not in added_ids:
        ordered_routes.append(n)
        added_ids.add(n["id"])

for n in sorted(offset_nodes, key=lambda n: (n["point"][0], n["point"][1], n["id"])):
    if n["id"] not in added_ids:
        ordered_routes.append(n)
        added_ids.add(n["id"])

for n in sorted(unconnected_nodes, key=lambda n: (n["point"][0], n["point"][1], n["id"])):
    if n["id"] not in added_ids:
        ordered_routes.append(n)
        added_ids.add(n["id"])


# ------------------------------------------------------------
# АДРЕСА
# ------------------------------------------------------------

def is_empty(s):
    return s is None or unicode(s).strip() == u""


if RENUMBER_EXISTING:
    num = 1
    for n in ordered_routes:
        n["addr"] = u"{}.{}".format(floor_code, num)
        num += 1
else:
    num = 1
    used_addrs = set()

    for n in ordered_routes:
        if not is_empty(n["addr_original"]):
            n["addr"] = n["addr_original"]
            used_addrs.add(n["addr"])

    for n in ordered_routes:
        if is_empty(n["addr_original"]):
            while True:
                candidate = u"{}.{}".format(floor_code, num)
                num += 1
                if candidate not in used_addrs:
                    n["addr"] = candidate
                    used_addrs.add(candidate)
                    break

for n in real_nodes:
    if n["parent_id"] is not None and n["parent_id"] in all_points_by_id:
        parent_obj = all_points_by_id[n["parent_id"]]
        n["parent_addr"] = parent_obj["addr"] if parent_obj["is_route"] else parent_obj["addr_original"]
    else:
        n["parent_addr"] = None

    n["write_value"] = n["parent_addr"] if n["parent_addr"] is not None else u""

for n in offset_nodes:
    best_real = find_best_real_node_for_offset(n, lines_by_id, real_nodes, OFFSET)

    if best_real is None:
        best_real, _ = find_nearest_real_node(n, real_nodes)

    if best_real and not is_empty(best_real["addr"]):
        n["write_value"] = best_real["addr"]
    else:
        n["write_value"] = u""

for n in unconnected_nodes:
    n["write_value"] = u""


# ------------------------------------------------------------
# ЗАПИСЬ
# ------------------------------------------------------------

changed = []
skipped = []

with revit.Transaction("Renumber Route Addresses"):

    for p in route_points:
        do_write = RENUMBER_EXISTING or is_empty(p["addr_original"])

        if do_write:
            set_string_param(p["element"], ADDR_PARAM, p["addr"] if p["addr"] else u"")
            set_string_param(p["element"], ADDR_PREV_PARAM, p["write_value"])
            changed.append(p)
        else:
            skipped.append(p)


forms.alert(
    u"Готово.\n\n"
    u"Уровень: {}\n"
    u"Код этажа: {}\n"
    u"Корень: {}\n"
    u"Режим: {}\n\n"
    u"Узлов маршрута всего: {}\n"
    u"Изменено: {}\n"
    u"Пропущено (уже был адрес): {}\n"
    u"Очищено чужих адресов: {}".format(
        level_name,
        floor_code,
        u"Панель" if panels else u"Стояк",
        choice,
        len(route_points),
        len(changed),
        len(skipped),
        len(stray_cleared)
    )
)
