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
from lowlife.params import get_string_param, set_string_param, get_param_any, set_param_any
from lowlife.scs import classify_element, clear_stray_address_params
from lowlife import scs_settings
from lowlife.scs_settings import get_settings_silent
from lowlife.scs_addressing import (
    pt2, dist2, add_neighbor, get_floor_code_from_view, classify_point,
    find_nearest_real_node, find_best_real_node_for_offset,
    point_to_segment_distance_xy, line_parameter_xy,
    build_shortest_path_tree, depth_first_order
)
from lowlife.scs_circuits import norm, clean_text_value, find_nearest_segment_id

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

MM_IN_FOOT = 304.8
STRICT = 30.0 / MM_IN_FOOT
OFFSET = 210.0 / MM_IN_FOOT
MARKED_TOL = 150.0 / MM_IN_FOOT
END_TOL = 50.0 / MM_IN_FOOT

# Насколько далеко за пределы фактической области узлов маршрута на этом
# виде может быть панель/стояк, чтобы всё ещё считаться корнем обхода.
# Без этой проверки панель, случайно подошедшая по ключевым словам, но
# находящаяся физически в другом конце здания, всё равно "прилипала" бы
# к ближайшему узлу — там срабатывал резервный поиск без ограничения
# расстояния (find_nearest_real_node).
ROOT_SEARCH_MARGIN_MM = 20000.0
ROOT_SEARCH_MARGIN = ROOT_SEARCH_MARGIN_MM / MM_IN_FOOT


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

scs_settings.require(settings, [
    "route_type_id", "riser_type_id",
    "workset_filter_key", "circuit_panel_param", "nearest_segment_param"
])
# Имена параметров (addr_param_name, addr_prev_param_name) здесь не
# проверяются — их наличие/привязку в проекте проверяет и чинит кнопка
# «Параметры СКС» (SetupParameters).

ADDR_PARAM = settings["addr_param_name"]
ADDR_PREV_PARAM = settings["addr_prev_param_name"]
PANEL_KEYWORDS = settings["panel_keywords"]
PANEL_EXCLUDE_KEYWORDS = settings["panel_exclude_keywords"]

ROUTE_TYPE_ID = ElementId(int(settings["route_type_id"]))
RISER_TYPE_ID = ElementId(int(settings["riser_type_id"]))

WORKSET_PARAM_NAME = settings["workset_param_name"]
WORKSET_FILTER_KEY = settings["workset_filter_key"]
EXCLUDED_DEVICE_KEYWORDS = settings["excluded_device_keywords"]
CIRCUIT_PANEL_PARAM = settings["circuit_panel_param"]
NEAREST_SEGMENT_PARAM = settings["nearest_segment_param"]


def is_excluded_device(el):
    """Резервный (исключаемый из расчёта) порт — по ключевым словам в имени семейства."""
    try:
        fam_name = el.Symbol.Family.Name
    except:
        return False
    return any(w.lower() in (fam_name or u"").lower() for w in EXCLUDED_DEVICE_KEYWORDS if w)


def get_workset_name(el):
    val = get_param_any(el, WORKSET_PARAM_NAME)
    if val:
        return val
    try:
        p = el.get_Parameter(BuiltInParameter.ELEM_PARTITION_PARAM)
        if p and p.HasValue:
            v = p.AsValueString()
            if v:
                return v
    except:
        pass
    return None


def panel_matches(panel):
    ws = norm(get_workset_name(panel))
    if not ws:
        return False
    return WORKSET_FILTER_KEY.lower() in ws.lower()

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

# Область, где реально есть узлы маршрута на этом виде, расширенная на
# запас — панель/стояк далеко за её пределами в корни не годится, даже
# если формально у неё "нашёлся" ближайший узел (резервный поиск по
# find_nearest_real_node ищет вообще без ограничения расстояния).
if real_nodes:
    xs = [n["point"][0] for n in real_nodes]
    ys = [n["point"][1] for n in real_nodes]
    root_area = (
        min(xs) - ROOT_SEARCH_MARGIN, max(xs) + ROOT_SEARCH_MARGIN,
        min(ys) - ROOT_SEARCH_MARGIN, max(ys) + ROOT_SEARCH_MARGIN
    )
else:
    root_area = None


def in_root_area(pt):
    if root_area is None:
        return True
    x_min, x_max, y_min, y_max = root_area
    return x_min <= pt[0] <= x_max and y_min <= pt[1] <= y_max


# Панель в приоритете, но если ВСЕ панели оказались далеко за пределами
# области трассы — это фактически "на этаже нет панели", пробуем стояки.
near_panels = [p for p in panels if in_root_area(p["point"])]
near_panel_ids = set(p["id"] for p in near_panels)
far_panels = [p for p in panels if p["id"] not in near_panel_ids]

if near_panels:
    root_sources = near_panels
    far_sources = far_panels
else:
    near_risers = [r for r in risers if in_root_area(r["point"])]
    near_riser_ids = set(r["id"] for r in near_risers)
    far_risers = [r for r in risers if r["id"] not in near_riser_ids]

    root_sources = near_risers
    far_sources = far_panels + far_risers

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
# КРАТЧАЙШИЙ ПУТЬ ДО КОРНЯ (ДЕЙКСТРА) + ПОРЯДОК ОБХОДА (DFS)
# ------------------------------------------------------------
# Раньше здесь был обход в ширину (BFS): "предыдущий узел" — тот, кто
# первым открыл узел в обходе, что при наличии нескольких физических
# путей к одному узлу могло выбрать более длинный путь как "предыдущий".
# Дейкстра всегда выбирает родителя по кратчайшему РЕАЛЬНОМУ расстоянию.
#
# Нумерация — обходом в глубину (DFS) по уже построенному дереву: одна
# ветка получает подряд идущие номера от начала до конца, только потом
# нумеруется следующая ветка (а не вперемешку, как при нумерации в
# порядке открытия BFS).

real_nodes_by_id = dict((n["id"], n) for n in real_nodes)

_, effective_roots = build_shortest_path_tree(real_nodes_by_id, unique_roots, real_nodes, dist2)

ordered_real_nodes = depth_first_order(real_nodes_by_id, effective_roots)


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


# ------------------------------------------------------------
# БЛИЖАЙШИЙ УЗЕЛ МАРШРУТА ДЛЯ ПАНЕЛЕЙ И УСТРОЙСТВ
# ------------------------------------------------------------
# Раньше это считалось и писалось в SyncCircuitsAndLengths, но логичнее
# делать это здесь: сначала расставляются узлы (PlaceRouteNodes), потом
# им всем присваиваются адреса и заодно у панелей/устройств проставляется
# ближайший адресованный узел (эта кнопка), и только потом
# SyncCircuitsAndLengths считает по готовым адресам длины/маршруты цепей.

segments_by_addr = {}
for p in route_points:
    pt = get_point(p["element"])
    if pt is None or is_empty(p["addr"]):
        continue
    segments_by_addr[p["addr"]] = {"pt": pt}

all_panels = FilteredElementCollector(doc) \
    .OfCategory(BuiltInCategory.OST_ElectricalEquipment) \
    .WhereElementIsNotElementType() \
    .ToElements()

target_panels = [p for p in all_panels if panel_matches(p)]

all_circuits = FilteredElementCollector(doc) \
    .OfCategory(BuiltInCategory.OST_ElectricalCircuit) \
    .WhereElementIsNotElementType() \
    .ToElements()

target_panels_by_name = {}
for p in target_panels:
    pname = norm(p.Name)
    if pname:
        target_panels_by_name.setdefault(pname, p)

devices_by_id = {}
for c in all_circuits:
    panel_name = norm(get_string_param(c, CIRCUIT_PANEL_PARAM))
    panel_el = target_panels_by_name.get(panel_name)
    if panel_el is None:
        continue

    try:
        raw_devs = [x for x in c.Elements if x.Id != panel_el.Id]
    except:
        continue

    for d in raw_devs:
        if is_excluded_device(d):
            continue
        devices_by_id[d.Id.IntegerValue] = d

nearest_written = 0

with revit.Transaction("Write Nearest Segment"):

    for panel in target_panels:
        if clean_text_value(get_string_param(panel, NEAREST_SEGMENT_PARAM)):
            continue
        panel_pt = get_point(panel)
        if panel_pt is None:
            continue
        nearest_sid, _ = find_nearest_segment_id(panel_pt, segments_by_addr)
        if nearest_sid and set_param_any(panel, NEAREST_SEGMENT_PARAM, nearest_sid):
            nearest_written += 1

    for dev in devices_by_id.values():
        if clean_text_value(get_string_param(dev, NEAREST_SEGMENT_PARAM)):
            continue
        dev_pt = get_point(dev)
        if dev_pt is None:
            continue
        nearest_sid, _ = find_nearest_segment_id(dev_pt, segments_by_addr)
        if nearest_sid and set_param_any(dev, NEAREST_SEGMENT_PARAM, nearest_sid):
            nearest_written += 1


# ------------------------------------------------------------
# ПОДРОБНЫЙ ОТЧЁТ (для диагностики порядка нумерации)
# ------------------------------------------------------------

def mm(v):
    return u"{:.0f}".format(v * MM_IN_FOOT)


def category_label(n):
    if n["is_panel"]:
        return u"Панель"
    if n["is_riser"]:
        return u"Стояк"
    return u"Маршрут"


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

output.print_md(u"## Адреса узлов — подробный отчёт")

far_ids = set(s["id"] for s in far_sources)

if panels or risers:
    output.print_md(u"### Панели и стояки ({})".format(len(panels) + len(risers)))
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


forms.alert(
    u"Готово.\n\n"
    u"Уровень: {}\n"
    u"Код этажа: {}\n"
    u"Корень: {}\n"
    u"Режим: {}\n\n"
    u"Узлов маршрута всего: {}\n"
    u"Изменено: {}\n"
    u"Пропущено (уже был адрес): {}\n"
    u"Очищено чужих адресов: {}\n"
    u"Отброшено как слишком далёкие (не корень): {}\n\n"
    u"Записано «Ближайший узел маршрута» (панели/устройства): {}\n\n"
    u"Подробности — в окне вывода pyRevit.".format(
        level_name,
        floor_code,
        (u"Панель" if root_sources[0]["is_panel"] else u"Стояк") if root_sources else u"Нет (все далеко)",
        choice,
        len(route_points),
        len(changed),
        len(skipped),
        len(stray_cleared),
        len(far_sources),
        nearest_written
    )
)
