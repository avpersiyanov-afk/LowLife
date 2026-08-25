# -*- coding: utf-8 -*-
__title__ = "Адреса\nузлов"
__doc__ = "Нумерует адреса узлов маршрута по этажу, начиная от панелей/стояков"
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms

from lowlife.geometry import get_point, get_document_levels
from lowlife.params import get_string_param, set_string_param, set_param_any
from lowlife.scs import (
    classify_element, clear_stray_address_params,
    is_excluded_device, panel_matches, detect_cable_type, keyword_match_rank
)
from lowlife import scs_settings
from lowlife.scs_settings import get_settings_silent
from lowlife.scs_addressing import (
    pt2, dist2, add_neighbor, get_floor_code_for_level, classify_point,
    find_nearest_real_node, find_best_real_node_for_offset,
    point_to_segment_distance_xy, line_parameter_xy,
    build_shortest_path_tree, depth_first_order, select_root_sources
)
from lowlife.scs_circuits import norm, find_nearest_segment_id

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

MM_IN_FOOT = 304.8
STRICT = 30.0 / MM_IN_FOOT
OFFSET = 210.0 / MM_IN_FOOT
MARKED_TOL = 150.0 / MM_IN_FOOT
END_TOL = 50.0 / MM_IN_FOOT

# Запас вокруг фактической области узлов маршрута для выбора корней
# обхода — см. select_root_sources в scs_addressing.py.
ROOT_SEARCH_MARGIN_MM = 20000.0
ROOT_SEARCH_MARGIN = ROOT_SEARCH_MARGIN_MM / MM_IN_FOOT


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

scs_settings.require(settings, [
    "route_type_id", "riser_type_id", "panel_type_id",
    "workset_filter_key", "circuit_panel_param", "nearest_segment_param"
])
# Имена параметров (addr_param_name, addr_prev_param_name) здесь не
# проверяются — их наличие/привязку в проекте проверяет и чинит кнопка
# «Параметры СКС» (SetupParameters).

ADDR_PARAM = settings["addr_param_name"]
ADDR_PREV_PARAM = settings["addr_prev_param_name"]
CABLE_PARAM_NAME = settings["cable_param_name"]
PANEL_KEYWORDS = settings["panel_keywords"]
PANEL_EXCLUDE_KEYWORDS = settings["panel_exclude_keywords"]

ROUTE_TYPE_ID = ElementId(int(settings["route_type_id"]))
RISER_TYPE_ID = ElementId(int(settings["riser_type_id"]))
PANEL_TYPE_ID = ElementId(int(settings["panel_type_id"]))

WORKSET_PARAM_NAME = settings["workset_param_name"]
WORKSET_FILTER_KEY = settings["workset_filter_key"]
EXCLUDED_DEVICE_KEYWORDS = settings["excluded_device_keywords"]
CIRCUIT_PANEL_PARAM = settings["circuit_panel_param"]
NEAREST_SEGMENT_PARAM = settings["nearest_segment_param"]


# ------------------------------------------------------------
# ОЧИСТКА "ЧУЖИХ" АДРЕСОВ
# ------------------------------------------------------------
# У элементов, которые больше не являются маркерами маршрута/стояка
# (например, устройств, оставшихся с прежних запусков или после
# разделения на отдельные семейства панель/устройство/маршрут), могли
# остаться значения ADDR_PARAM/ADDR_PREV_PARAM. Если реальный узел
# маршрута сошлётся на такой "чужой" адрес, путь до него не найдётся —
# поэтому чистим их перед сбором элементов.
#
# Ограничено рабочим набором: имена параметров адреса общие с другими
# дисциплинами (СКУД тоже пишет в SMNX_Сегмент), поэтому без ограничения
# запуск СКС стирал бы их адреса.

with revit.Transaction("Clear stray route addresses"):
    stray_cleared = clear_stray_address_params(
        doc, [ADDR_PARAM, ADDR_PREV_PARAM], set([ROUTE_TYPE_ID, RISER_TYPE_ID, PANEL_TYPE_ID]),
        workset_param_name=WORKSET_PARAM_NAME,
        workset_filter_key=WORKSET_FILTER_KEY
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
    # Совпадение с PANEL_TYPE_ID — основной, надёжный признак: именно этим
    # типом PlaceRouteNodes реально расставляет маркеры панелей, и route/
    # riser определяются точно так же, по ElementId типа. Ключевые слова
    # (classify_element) — запасной вариант, оставлен для проектов, где
    # тип панели ещё не выбран/отличается: раньше это был ЕДИНСТВЕННЫЙ
    # признак панели, из-за чего маркер, чьё имя семейства/типа не
    # содержит ни одного слова из PANEL_KEYWORDS, вообще не попадал в
    # список панелей — и, соответственно, никогда не мог стать корнем
    # адресации, даже если он расставлен верно.
    is_panel = (type_id == PANEL_TYPE_ID) or (
        classify_element(el, [("panel", PANEL_KEYWORDS, PANEL_EXCLUDE_KEYWORDS)]) == "panel"
    )

    if not (is_route or is_riser or is_panel):
        continue

    # Индекс подошедшего слова в PANEL_KEYWORDS (0 = самое приоритетное) —
    # используется ниже, чтобы на этаже с несколькими видами "панелей"
    # (например разные шкафы, оба подходящие под общий список ключевых
    # слов) корнями адресации становился только один вид — тот, чьё слово
    # стоит в списке раньше (см. блок «КОРНИ» ниже).
    panel_keyword_rank = keyword_match_rank(el, PANEL_KEYWORDS, PANEL_EXCLUDE_KEYWORDS) if is_panel else None

    points.append({
        "id": el.Id.IntegerValue,
        "element": el,
        "point": pt2(pt),
        "is_route": is_route,
        "is_riser": is_riser,
        "is_panel": is_panel,
        "panel_keyword_rank": panel_keyword_rank,
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

document_levels = get_document_levels(doc)
floor_code, level_name = get_floor_code_for_level(view, document_levels)

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
            add_neighbor(n1, n2, line["id"])


# ------------------------------------------------------------
# КОРНИ (ПАНЕЛИ/СТОЯКИ)
# ------------------------------------------------------------
# Если на этаже панели разных видов (подошли под разные слова из
# PANEL_KEYWORDS — например помимо целевого шкафа СКС рядом стоит и
# силовой щит, у которого в имени тоже случайно есть общее слово),
# кандидатами в корень идёт только вид с самым приоритетным словом
# (наименьший panel_keyword_rank) — остальные виды панелей на этом этаже
# из кандидатов в корень исключаются (но остаются панелями: адрес вида
# "F1.P2" получают как обычно, см. блок «АДРЕСА» ниже — просто не
# участвуют в выборе корня и не являются веткой дерева).
# panel_keyword_rank is None — панель распознана по PANEL_TYPE_ID, а не
# по слову из PANEL_KEYWORDS (см. сбор точек выше): у приоритета "нет
# мнения" про такую панель, поэтому она никогда не демоутится этим
# фильтром — демоутятся только панели, у которых само слово нашлось, но
# оно НЕ самое приоритетное среди найденных на этаже.
panel_ranks_present = [p["panel_keyword_rank"] for p in panels if p["panel_keyword_rank"] is not None]
best_panel_rank = min(panel_ranks_present) if panel_ranks_present else None

root_candidate_panels = [
    p for p in panels
    if p["panel_keyword_rank"] is None or best_panel_rank is None or p["panel_keyword_rank"] == best_panel_rank
]
root_candidate_ids = set(p["id"] for p in root_candidate_panels)
demoted_panels = [p for p in panels if p["id"] not in root_candidate_ids]

root_sources, far_sources = select_root_sources(root_candidate_panels, risers, real_nodes, ROOT_SEARCH_MARGIN)

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
# ТИП ПРОКЛАДКИ КАБЕЛЯ
# ------------------------------------------------------------
# Раньше это определялось в PlaceRouteNodes по первому попавшемуся в
# set() соседнему сегменту — недетерминированно: узел на стыке трубы и
# лотка мог получить любой из двух типов в зависимости от порядка
# обхода, из-за чего длина в трубе/лотке считалась неверно.
#
# Направление известно только здесь (parent_id уже построен Дейкстрой):
# берём тип прокладки сегмента К РОДИТЕЛЮ (в сторону панели), а не от
# него. Способ прокладки на стыке (например, труба переходит в лоток)
# должен смениться ровно в точке стыка, а не позже — если узел B стоит
# на стыке "труба(A-B) -> лоток(B-...)", отрезок A-B ещё в трубе, а
# отрезок от B дальше — уже в лотке; сохраняя на B тип сегмента к
# родителю (A-B, труба), get calc_lengths (SyncCircuitsAndLengths)
# отрезок "предыдущий узел -> B" по install узла, ИЗ КОТОРОГО тот
# выходит, получает правильный тип. У корневого узла (ближайшего к
# панели, своего родителя в дереве нет) — берём любой примыкающий
# сегмент, отдельного сегмента к родителю там просто не существует.

for n in real_nodes:
    neighbor_line_by_id = n.get("neighbor_line_by_id", {})
    parent_id = n.get("parent_id")

    line_id = neighbor_line_by_id.get(parent_id) if parent_id is not None else None

    if line_id is None:
        for neighbor_id in n.get("neighbor_ids", []):
            line_id = neighbor_line_by_id.get(neighbor_id)
            if line_id is not None:
                break

    line = lines_by_id.get(line_id) if line_id is not None else None

    if line is not None:
        cable_type_value = detect_cable_type(line["element"])
        if cable_type_value is not None:
            n["cable_type_value"] = cable_type_value


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


num = 1
for n in ordered_routes:
    n["addr"] = u"{}.{}".format(floor_code, num)
    num += 1

# Панели и стояки — корни обхода, сами не входят в route_points/
# ordered_routes, но тоже получают адрес: отдельный счётчик на этаж для
# каждой категории (P для панелей, R для стояков), не связанный со
# счётчиком обычных узлов маршрута. Порядок — по координатам (как и для
# offset/unconnected узлов), чтобы результат был стабильным между
# запусками (порядок коллектора Revit не гарантирован).
panel_num = 1
for n in sorted(panels, key=lambda n: (n["point"][0], n["point"][1], n["id"])):
    n["addr"] = u"{}.P{}".format(floor_code, panel_num)
    panel_num += 1

riser_num = 1
for n in sorted(risers, key=lambda n: (n["point"][0], n["point"][1], n["id"])):
    n["addr"] = u"{}.R{}".format(floor_code, riser_num)
    riser_num += 1

for n in real_nodes:
    if n["parent_id"] is not None and n["parent_id"] in all_points_by_id:
        parent_obj = all_points_by_id[n["parent_id"]]
        n["parent_addr"] = parent_obj["addr"]
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

with revit.Transaction("Renumber Route Addresses"):

    for p in route_points:
        set_string_param(p["element"], ADDR_PARAM, p["addr"] if p["addr"] else u"")
        set_string_param(p["element"], ADDR_PREV_PARAM, p["write_value"])
        cable_type_value = p.get("cable_type_value")
        if cable_type_value is not None:
            set_string_param(p["element"], CABLE_PARAM_NAME, cable_type_value)
        changed.append(p)

    # Панели и стояки тоже получают свой адрес (F1.P1/F1.R1) — «Предыдущий
    # адрес» у них не пишется, они сами корни, родителя у них нет.
    for p in panels + risers:
        set_string_param(p["element"], ADDR_PARAM, p["addr"] if p["addr"] else u"")
        changed.append(p)


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

# Ближайший узел ищется только среди узлов маршрута АКТИВНОГО ВИДА
# (segments_by_addr выше построен из route_points — тоже view.Id-
# коллектор). Раньше панели/устройства для этого шага собирались по ВСЕМУ
# документу — устройство с другого этажа могло получить "ближайший узел"
# с текущего этажа просто по XY-расстоянию (find_nearest_segment_id
# сознательно игнорирует Z, см. её docstring), хотя физически относится к
# другой, отдельно адресованной трассе. Теперь панели и устройства для
# этого шага тоже ограничены активным видом — только к нему относится
# посчитанный здесь граф узлов.
visible_on_view_ids = set(
    eid.IntegerValue for eid in
    FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType().ToElementIds()
)

all_panels = FilteredElementCollector(doc, view.Id) \
    .OfCategory(BuiltInCategory.OST_ElectricalEquipment) \
    .WhereElementIsNotElementType() \
    .ToElements()

target_panels = [p for p in all_panels if panel_matches(p, WORKSET_PARAM_NAME, WORKSET_FILTER_KEY, norm)]

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
        if is_excluded_device(d, EXCLUDED_DEVICE_KEYWORDS):
            continue
        if d.Id.IntegerValue not in visible_on_view_ids:
            continue
        devices_by_id[d.Id.IntegerValue] = d

nearest_written = 0

with revit.Transaction("Write Nearest Segment"):

    for panel in target_panels:
        panel_pt = get_point(panel)
        if panel_pt is None:
            continue
        nearest_sid, _ = find_nearest_segment_id(panel_pt, segments_by_addr)
        if nearest_sid and set_param_any(panel, NEAREST_SEGMENT_PARAM, nearest_sid):
            nearest_written += 1

    for dev in devices_by_id.values():
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


def find_root_source(n):
    """
    Идёт вверх по цепочке parent_id до панели/стояка (корня обхода) — в
    отличие от parent_label (только непосредственный родитель), показывает
    ИТОГОВЫЙ шкаф/стояк, к которому в итоге отнесена вся ветка узла. Нужно
    для проверки, когда на этаже несколько шкафов: build_shortest_path_tree
    относит каждый узел к БЛИЖАЙШЕМУ по РЕАЛЬНОЙ длине трассы шкафу/стояку
    (не по прямой) — эта функция показывает, к какому именно, чтобы можно
    было сверить с ожиданием и найти обрыв связности, если авто-выбор
    выглядит неверным.
    """
    seen = set()
    current = n
    while True:
        pid = current.get("parent_id")
        if pid is None or pid in seen:
            return None
        seen.add(pid)
        if pid in real_nodes_by_id:
            current = real_nodes_by_id[pid]
            continue
        return all_points_by_id.get(pid)


def root_source_label(n):
    src = find_root_source(n)
    if src is None:
        return u"-"
    return u"{} ({})".format(src.get("addr") or u"без адреса", category_label(src))


branch_size_by_root_id = {}
for n in real_nodes:
    src = find_root_source(n)
    if src is not None:
        branch_size_by_root_id[src["id"]] = branch_size_by_root_id.get(src["id"], 0) + 1


from pyrevit import script as pyrevit_script
output = pyrevit_script.get_output()

output.print_md(u"## Адреса узлов — подробный отчёт")

far_ids = set(s["id"] for s in far_sources)
demoted_ids = set(p["id"] for p in demoted_panels)


def root_status_label(n):
    if n["id"] in demoted_ids:
        return u"Ниже приоритета слова панели — не корень"
    if n["id"] in far_ids:
        return u"Слишком далеко — не корень"
    return u"Корень"


if panels or risers:
    output.print_md(u"### Панели и стояки ({})".format(len(panels) + len(risers)))
    roots_table = []
    for n in panels + risers:
        roots_table.append([
            n["id"], category_label(n), mm(n["point"][0]), mm(n["point"][1]),
            n.get("addr") or u"-",
            n.get("panel_keyword_rank") if n.get("panel_keyword_rank") is not None else u"-",
            root_status_label(n),
            branch_size_by_root_id.get(n["id"], 0)
        ])
    output.print_table(
        table_data=roots_table,
        columns=[u"ID", u"Категория", u"X, мм", u"Y, мм", u"Адрес", u"Приоритет слова", u"Статус", u"Узлов в ветке"]
    )

output.print_md(u"### Узлы маршрута — в порядке нумерации ({})".format(len(ordered_routes)))
nodes_table = []
for i, n in enumerate(ordered_routes, start=1):
    nodes_table.append([
        i, n["id"], mm(n["point"][0]), mm(n["point"][1]),
        n.get("classification") or u"-",
        n.get("addr") or u"-",
        n.get("write_value") or u"-",
        parent_label(n),
        root_source_label(n)
    ])
output.print_table(
    table_data=nodes_table,
    columns=[
        u"#", u"ID", u"X, мм", u"Y, мм", u"Классификация", u"Адрес", u"Предыдущий адрес",
        u"Родитель", u"Итоговый шкаф/стояк"
    ]
)


forms.alert(
    u"Готово.\n\n"
    u"Уровень: {}\n"
    u"Код этажа: {}\n"
    u"Корень: {}\n\n"
    u"Узлов маршрута всего: {}\n"
    u"Перенумеровано: {}\n"
    u"Очищено чужих адресов: {}\n"
    u"Отброшено как слишком далёкие (не корень): {}\n"
    u"Панелей ниже приоритета слова (не корень): {}\n\n"
    u"Записано «Ближайший узел маршрута» (панели/устройства): {}\n\n"
    u"Подробности — в окне вывода pyRevit.".format(
        level_name,
        floor_code,
        (u"Панель" if root_sources[0]["is_panel"] else u"Стояк") if root_sources else u"Нет (все далеко)",
        len(route_points),
        len(changed),
        len(stray_cleared),
        len(far_sources),
        len(demoted_panels),
        nearest_written
    )
)
