# -*- coding: utf-8 -*-
__title__ = "Узлы трассы"
__doc__ = "Расставляет панели/узлы маршрута/стояки в точках трассы кабеля"
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Structure import StructuralType
from pyrevit import revit, forms

from lowlife.geometry import (
    get_point, get_curve_data, point_key, points_close,
    is_point_on_curve, sort_points, get_document_levels, find_level_for_elevation,
    get_element_level
)
from lowlife.params import get_double_param, set_double_param, set_string_param
from lowlife.scs import detect_cable_type, classify_element, merge_nodes, resolve_category
from lowlife import scs_settings
from lowlife.scs_settings import get_settings_silent

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

tolerance = 0.01
point_on_curve_tolerance = 0.05
merge_tolerance = 0.1


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

scs_settings.require(settings, [
    "panel_type_id", "route_type_id", "riser_type_id",
    "family_filter", "route_param_value", "route_param_value_riser",
    "device_cable_type_value"
])
# Имена параметров (cable_param_name, route_param_name,
# offset_param_names) здесь не проверяются — их наличие/привязку в
# проекте проверяет и чинит кнопка «Параметры СКС» (SetupParameters).

FAMILY_FILTER = settings["family_filter"]
CABLE_PARAM_NAME = settings["cable_param_name"]
ROUTE_PARAM_NAME = settings["route_param_name"]
ROUTE_PARAM_VALUE = settings["route_param_value"]
ROUTE_PARAM_VALUE_RISER = settings["route_param_value_riser"]
# Форсированный тип прокладки для панелей/стояков (точек-концов, а не
# узлов посреди трассы) — устройства больше не отдельная категория,
# семейство в их точках не ставится, поэтому DEVICE в названии не осталось.
ENDPOINT_CABLE_TYPE_VALUE = settings["device_cable_type_value"]
PANEL_KEYWORDS = settings["panel_keywords"]
PANEL_EXCLUDE_KEYWORDS = settings["panel_exclude_keywords"]
RISER_KEYWORDS = settings["riser_keywords"]
RISER_EXCLUDE_KEYWORDS = settings["riser_exclude_keywords"]
OFFSET_PARAM_NAMES = settings["offset_param_names"]

TYPE_ID_BY_CATEGORY = {
    "panel": ElementId(int(settings["panel_type_id"])),
    "route": ElementId(int(settings["route_type_id"])),
    "riser": ElementId(int(settings["riser_type_id"])),
}

symbols_by_category = {}
for category_name, type_id in TYPE_ID_BY_CATEGORY.items():
    symbol = doc.GetElement(type_id)
    if symbol is None:
        forms.alert(
            u"Не найден выбранный тип для категории «{}». "
            u"Откройте настройки и выберите тип заново.".format(category_name),
            exitscript=True
        )
    symbols_by_category[category_name] = symbol

placed_type_ids = set(t.IntegerValue for t in TYPE_ID_BY_CATEGORY.values())


# ------------------------------------------------------------
# ОСНОВНОЙ КОД
# ------------------------------------------------------------

generic = FilteredElementCollector(doc, view.Id) \
    .OfCategory(BuiltInCategory.OST_GenericModel) \
    .WhereElementIsNotElementType() \
    .ToElements()

segments = []
segments_by_id = {}

for el in generic:
    try:
        fam_name = el.Symbol.Family.Name
    except:
        continue

    if FAMILY_FILTER not in fam_name:
        continue

    curve, p1, p2 = get_curve_data(el, view)
    if curve is None:
        continue

    data = {
        "element": el,
        "id": el.Id.IntegerValue,
        "curve": curve,
        "p1": p1,
        "p2": p2
    }
    segments.append(data)
    segments_by_id[data["id"]] = data

if not segments:
    forms.alert("Сегменты трассы не найдены.", exitscript=True)

all_endpoints = []
for s in segments:
    all_endpoints.append(s["p1"])
    all_endpoints.append(s["p2"])

split_points_by_segment = {}

for s in segments:
    pts = [s["p1"], s["p2"]]
    for pt in all_endpoints:
        ok, projected = is_point_on_curve(s["curve"], pt, point_on_curve_tolerance)
        if ok and projected is not None:
            exists = False
            for ex in pts:
                if ex.DistanceTo(projected) <= tolerance:
                    exists = True
                    break
            if not exists:
                pts.append(projected)

    split_points_by_segment[s["id"]] = sort_points(s["curve"], pts)

graph = {}
node_points = {}
segment_ids_by_node = {}

for s in segments:
    pts = split_points_by_segment[s["id"]]
    for i in range(len(pts) - 1):
        a = pts[i]
        b = pts[i + 1]

        if a.DistanceTo(b) <= tolerance:
            continue

        k1 = point_key(a, tolerance)
        k2 = point_key(b, tolerance)

        node_points[k1] = a
        node_points[k2] = b

        if k1 not in graph:
            graph[k1] = []
        if k2 not in graph:
            graph[k2] = []

        if k2 not in graph[k1]:
            graph[k1].append(k2)
        if k1 not in graph[k2]:
            graph[k2].append(k1)

        if k1 not in segment_ids_by_node:
            segment_ids_by_node[k1] = set()
        if k2 not in segment_ids_by_node:
            segment_ids_by_node[k2] = set()

        segment_ids_by_node[k1].add(s["id"])
        segment_ids_by_node[k2].add(s["id"])

# Панели и стояки ищем среди одних и тех же категорий элементов,
# различаем по ключевым словам (classify_element). Устройства отдельной
# точкой вставки больше не считаются — им достаточно ближайшего узла
# маршрута, а линию к ним подводят прямо (см. SyncCircuitsAndLengths).
candidate_categories = [
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_ElectricalEquipment
]

all_candidates = []

for cat in candidate_categories:
    all_candidates.extend(
        FilteredElementCollector(doc, view.Id)
        .OfCategory(cat)
        .WhereElementIsNotElementType()
        .ToElements()
    )

classify_rules = [
    ("riser", RISER_KEYWORDS, RISER_EXCLUDE_KEYWORDS),
    ("panel", PANEL_KEYWORDS, PANEL_EXCLUDE_KEYWORDS),
]

marked_points = []

for el in all_candidates:
    category = classify_element(el, classify_rules)
    if category is None:
        continue

    pt = get_point(el)
    if pt is None:
        continue

    nearest_key = None
    nearest_dist = None

    for k, p in node_points.items():
        try:
            d = pt.DistanceTo(p)
            if nearest_dist is None or d < nearest_dist:
                nearest_dist = d
                nearest_key = k
        except:
            pass

    marked_points.append({
        "element": el,
        "point": pt,
        "node_key": nearest_key,
        "category": category
    })

raw_nodes = []

for nk, neighbors in graph.items():
    # Включая узлы с одним соседом — иначе свободные концы линий
    # (не примыкающие ни к другой линии, ни к панели/стояку)
    # не получают узел маршрута вообще.
    raw_nodes.append({
        "point": node_points[nk],
        "node_key": nk,
        "source_type": "graph_node",
        "category": "route",
        "segment_ids": list(segment_ids_by_node.get(nk, []))
    })

for m in marked_points:
    raw_nodes.append({
        "point": m["point"],
        "node_key": m["node_key"],
        "source_type": "marked_point",
        "category": m["category"],
        "segment_ids": list(segment_ids_by_node.get(m["node_key"], [])) if m["node_key"] in segment_ids_by_node else [],
        "device": m
    })

insert_nodes = merge_nodes(raw_nodes, merge_tolerance, points_close)

for node in insert_nodes:
    node["category"] = resolve_category(node.get("categories", []))

existing_by_key = {}
# Дедуп ищет только на активном виде, вместе с самими сегментами
# трассы (generic) — кнопка расставляет узлы только по активному виду,
# поэтому и сверяться с существующими нужно в тех же границах.
for el in generic:
    try:
        if el.GetTypeId().IntegerValue in placed_type_ids:
            pt = get_point(el)
            if pt is not None:
                existing_by_key[point_key(pt, merge_tolerance)] = el
    except:
        pass

created = []
updated = []
counts_by_category = {"panel": 0, "route": 0, "riser": 0}

document_levels = get_document_levels(doc)
if not document_levels:
    forms.alert(u"В проекте нет ни одного уровня.", exitscript=True)

with revit.Transaction("Place Route Nodes"):

    for node in insert_nodes:
        point = node["point"]
        category = node["category"]
        target_symbol = symbols_by_category[category]

        if not target_symbol.IsActive:
            target_symbol.Activate()

        counts_by_category[category] += 1

        route_value = ROUTE_PARAM_VALUE_RISER if category == "riser" else ROUTE_PARAM_VALUE

        line_offset_value = None
        cable_type_value = None
        level = None

        device = node.get("device")
        is_marked = device is not None and category in ("panel", "riser")

        if is_marked:
            cable_type_value = ENDPOINT_CABLE_TYPE_VALUE
            dev_el = device.get("element")
            if dev_el is not None:
                line_offset_value = get_double_param(dev_el, OFFSET_PARAM_NAMES)
                # Панель/стояк — уровень берём с самого элемента
                # (его параметр «Уровень»), а не по высоте точки.
                level = get_element_level(doc, dev_el)

        for sid in node.get("segment_ids", []):
            if sid not in segments_by_id:
                continue

            seg_el = segments_by_id[sid]["element"]

            if line_offset_value is None:
                line_offset_value = get_double_param(seg_el, OFFSET_PARAM_NAMES)

            if not is_marked and cable_type_value is None:
                cable_type_value = detect_cable_type(seg_el)

            if line_offset_value is not None and cable_type_value is not None:
                break

        if level is None:
            # Уровень рабочей плоскости самой линии ненадёжен (line-based
            # семейство не всегда привязано к реальному этажу через
            # LevelId) — берём уровень ближайшей панели/стояка.
            nearest_marked = None
            nearest_marked_dist = None

            for m in marked_points:
                try:
                    d = point.DistanceTo(m["point"])
                except:
                    continue
                if nearest_marked_dist is None or d < nearest_marked_dist:
                    nearest_marked_dist = d
                    nearest_marked = m

            if nearest_marked is not None:
                level = get_element_level(doc, nearest_marked["element"])

        if level is None:
            # Нет ни одной панели/стояка с уровнем — резервный
            # вариант по высоте точки.
            level = find_level_for_elevation(point.Z, document_levels)

        key = point_key(point, merge_tolerance)
        existing = existing_by_key.get(key)

        if existing is None:
            el = doc.Create.NewFamilyInstance(point, target_symbol, level, StructuralType.NonStructural)

            if el:
                if line_offset_value is not None:
                    set_double_param(el, OFFSET_PARAM_NAMES, line_offset_value)

                if cable_type_value is not None:
                    set_string_param(el, CABLE_PARAM_NAME, cable_type_value)

                set_string_param(el, ROUTE_PARAM_NAME, route_value)
                created.append(el)

        else:
            el = existing

            if el.Symbol.Id != target_symbol.Id:
                el.Symbol = target_symbol

            if line_offset_value is not None:
                set_double_param(el, OFFSET_PARAM_NAMES, line_offset_value)

            if cable_type_value is not None:
                set_string_param(el, CABLE_PARAM_NAME, cable_type_value)

            set_string_param(el, ROUTE_PARAM_NAME, route_value)
            updated.append(el)


forms.alert(
    "Готово.\n\n"
    "Создано элементов: {}\n"
    "Обновлено элементов: {}\n\n"
    "Панелей: {}\n"
    "Стояков: {}\n"
    "Узлов маршрута: {}".format(
        len(created),
        len(updated),
        counts_by_category["panel"],
        counts_by_category["riser"],
        counts_by_category["route"]
    )
)
