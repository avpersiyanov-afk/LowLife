# -*- coding: utf-8 -*-
"""
Расстановка узлов трассы (панель / узел маршрута / стояк) по линиям
сегментов трассы — общее тело кнопки «Узлы трассы» для любой дисциплины.

Дисциплина задаётся конфигом (какие ключевые слова, какие типы семейств,
какой рабочий набор), а не отдельной копией скрипта: у СКС узлы ведут до
шкафа СКС, у СКУД — от устройств до контроллера, дальше появятся СПС/СОУЭ.
Логика при этом одна и та же, поэтому живёт здесь, а не в script.py.

Скрипт кнопки остаётся тонким: собрать конфиг из своих настроек и вызвать
place_route_nodes().
"""

from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, ElementId
)
from Autodesk.Revit.DB.Structure import StructuralType

from lowlife.geometry import (
    get_point, get_curve_data, point_key, points_close,
    is_point_on_curve, sort_points, get_document_levels,
    find_level_for_elevation, get_element_level
)
from lowlife.params import get_double_param, set_double_param, set_string_param
from lowlife.scs import (
    classify_element, merge_nodes, resolve_category,
    get_workset_name
)

TOLERANCE = 0.01
POINT_ON_CURVE_TOLERANCE = 0.05
MERGE_TOLERANCE = 0.1

# Категории, среди которых ищутся панели/стояки (реальные элементы, а не
# маркеры) — те же, что у СКС.
CANDIDATE_CATEGORIES = [
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_ElectricalEquipment
]


def collect_segments(doc, view, family_filter):
    """Линейные элементы-сегменты трассы на виде: [{element, id, curve, p1, p2}]."""
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

        if family_filter not in fam_name:
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

    return segments, segments_by_id, generic


def build_line_graph(segments):
    """
    Граф точек по линиям: каждая линия режется на участки в точках, где на
    неё попадают концы других линий. Возвращает (node_points, graph,
    segment_ids_by_node) с ключами по point_key.
    """
    all_endpoints = []
    for s in segments:
        all_endpoints.append(s["p1"])
        all_endpoints.append(s["p2"])

    split_points_by_segment = {}

    for s in segments:
        pts = [s["p1"], s["p2"]]
        for pt in all_endpoints:
            ok, projected = is_point_on_curve(s["curve"], pt, POINT_ON_CURVE_TOLERANCE)
            if ok and projected is not None:
                exists = False
                for ex in pts:
                    if ex.DistanceTo(projected) <= TOLERANCE:
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

            if a.DistanceTo(b) <= TOLERANCE:
                continue

            k1 = point_key(a, TOLERANCE)
            k2 = point_key(b, TOLERANCE)

            node_points[k1] = a
            node_points[k2] = b

            graph.setdefault(k1, [])
            graph.setdefault(k2, [])

            if k2 not in graph[k1]:
                graph[k1].append(k2)
            if k1 not in graph[k2]:
                graph[k2].append(k1)

            segment_ids_by_node.setdefault(k1, set()).add(s["id"])
            segment_ids_by_node.setdefault(k2, set()).add(s["id"])

    return node_points, graph, segment_ids_by_node


def collect_marked_points(doc, view, node_points, classify_rules,
                          workset_param_name=None, workset_filter_key=None):
    """
    Панели/стояки на виде — распознаются по ключевым словам, а если задан
    workset_filter_key, дополнительно фильтруются по рабочему набору.

    Фильтр по рабочему набору — то, чем дисциплины отличаются друг от
    друга на одном и том же плане: панель СКС и контроллер СКУД могут
    подходить под похожие ключевые слова, но лежат в разных рабочих
    наборах.
    """
    all_candidates = []

    for cat in CANDIDATE_CATEGORIES:
        all_candidates.extend(
            FilteredElementCollector(doc, view.Id)
            .OfCategory(cat)
            .WhereElementIsNotElementType()
            .ToElements()
        )

    marked_points = []

    for el in all_candidates:
        category = classify_element(el, classify_rules)
        if category is None:
            continue

        if workset_filter_key:
            ws = get_workset_name(el, workset_param_name)
            if not ws or workset_filter_key.lower() not in ws.lower():
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

    return marked_points


def build_insert_nodes(node_points, segment_ids_by_node, marked_points, existing_points=None):
    """
    Узлы для вставки: точки графа линий + помеченные точки, слитые по
    допуску. existing_points — координаты уже вставленных на виде
    маркеров; если заданы, итоговая точка кластера предпочитает точку
    уже существующего маркера (см. merge_nodes/_pick_cluster_point в
    scs.py) — иначе появление нового узла графа рядом с уже вставленным
    маркером могло "утянуть" итоговую точку кластера на новую координату,
    и повторный запуск не находил старый маркер, создавая дубль рядом.
    """
    raw_nodes = []

    for nk in node_points:
        # Включая узлы с одним соседом — иначе свободные концы линий
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
            "segment_ids": list(segment_ids_by_node.get(m["node_key"], []))
                if m["node_key"] in segment_ids_by_node else [],
            "device": m
        })

    insert_nodes = merge_nodes(raw_nodes, MERGE_TOLERANCE, points_close, existing_points=existing_points)

    for node in insert_nodes:
        node["category"] = resolve_category(node.get("categories", []))

    return insert_nodes


def find_existing_markers(generic, placed_type_ids):
    """
    Уже вставленные маркеры выбранных типов — плоский список (element, point),
    чтобы повторный запуск обновлял их, а не плодил копии.

    Простой линейный перебор без разбивки по сетке — медленнее (O(n^2)
    вместо O(n) на сетке), но однозначно надёжный: разбивка по ключу
    сетки (point_key) считала "другой" точкой то, что физически лежит
    рядом, но округляется в соседнюю ячейку — из-за чего повторный
    запуск не находил уже стоящий маркер и плодил дубль в той же точке.

    Ищет только среди переданных элементов (у вызывающего — активный вид),
    поэтому запускать кнопку для одной трассы стоит всегда с одного вида.
    """
    existing_list = []

    for el in generic:
        try:
            if el.GetTypeId().IntegerValue in placed_type_ids:
                pt = get_point(el)
                if pt is not None:
                    existing_list.append((el, pt))
        except:
            pass

    return existing_list


def find_existing_element(existing_list, consumed_ids, point):
    """Ближайший ещё не использованный существующий элемент нужного типа в пределах MERGE_TOLERANCE."""
    best_el = None
    best_dist = None

    for el, pt in existing_list:
        if el.Id in consumed_ids:
            continue
        try:
            d = point.DistanceTo(pt)
        except:
            continue
        if d <= MERGE_TOLERANCE and (best_dist is None or d < best_dist):
            best_dist = d
            best_el = el

    return best_el


def resolve_node_values(doc, node, segments_by_id, marked_points, config, document_levels):
    """
    Значения параметров и уровень для одного вставляемого узла.

    Тип прокладки кабеля НЕ определяется здесь для route-узлов: на стыке
    двух сегментов с разным способом прокладки (труба/лоток) нужно знать
    направление "к устройствам", а оно известно только после построения
    дерева адресации (см. route_addressing.py, assign_cable_types) —
    иначе узел на стыке недетерминированно получал бы любой из двух
    типов в зависимости от порядка обхода segment_ids (set()).
    """
    point = node["point"]
    category = node["category"]

    line_offset_value = None
    cable_type_value = None
    level = None

    device = node.get("device")
    is_marked = device is not None and category in ("panel", "riser")

    if is_marked:
        cable_type_value = config["endpoint_cable_type_value"]
        dev_el = device.get("element")
        if dev_el is not None:
            line_offset_value = get_double_param(dev_el, config["offset_param_names"])
            # Панель/стояк — уровень с самого элемента, а не по высоте точки.
            level = get_element_level(doc, dev_el)

    for sid in node.get("segment_ids", []):
        if sid not in segments_by_id:
            continue

        seg_el = segments_by_id[sid]["element"]

        if line_offset_value is None:
            line_offset_value = get_double_param(seg_el, config["offset_param_names"])

        if line_offset_value is not None:
            break

    if level is None:
        # Уровень рабочей плоскости линии ненадёжен — берём уровень
        # ближайшей панели/стояка.
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
        level = find_level_for_elevation(point.Z, document_levels)

    route_value = config["route_param_value_riser"] if category == "riser" \
        else config["route_param_value"]

    return line_offset_value, cable_type_value, level, route_value


def place_route_nodes(doc, view, config, symbols_by_category, document_levels):
    """
    Расставляет/обновляет узлы трассы на активном виде.

    config — словарь с ключами: family_filter, route_param_name,
    route_param_value, route_param_value_riser, endpoint_cable_type_value,
    cable_param_name, offset_param_names, panel_keywords,
    panel_exclude_keywords, riser_keywords, riser_exclude_keywords,
    workset_param_name, workset_filter_key.

    Возвращает dict со сводкой; сам транзакцию НЕ открывает — вызывающий
    оборачивает вызов в revit.Transaction.
    """
    segments, segments_by_id, generic = collect_segments(doc, view, config["family_filter"])

    if not segments:
        return {"segments_found": 0, "created": [], "skipped": [],
                "counts_by_category": {"panel": 0, "route": 0, "riser": 0}}

    node_points, _graph, segment_ids_by_node = build_line_graph(segments)

    classify_rules = [
        ("riser", config["riser_keywords"], config["riser_exclude_keywords"]),
        ("panel", config["panel_keywords"], config["panel_exclude_keywords"]),
    ]

    marked_points = collect_marked_points(
        doc, view, node_points, classify_rules,
        config.get("workset_param_name"), config.get("workset_filter_key")
    )

    placed_type_ids = set(s.Id.IntegerValue for s in symbols_by_category.values())
    existing_list = find_existing_markers(generic, placed_type_ids)
    existing_points = [pt for el, pt in existing_list]

    insert_nodes = build_insert_nodes(
        node_points, segment_ids_by_node, marked_points, existing_points=existing_points
    )

    consumed_ids = set()
    created = []
    skipped = []
    counts_by_category = {"panel": 0, "route": 0, "riser": 0}

    for node in insert_nodes:
        point = node["point"]
        category = node["category"]
        target_symbol = symbols_by_category[category]

        # Если в этой точке уже стоит маркер нужного типа — точку
        # полностью пропускаем: ничего не создаём и не обновляем.
        existing = find_existing_element(existing_list, consumed_ids, point)

        if existing is not None:
            consumed_ids.add(existing.Id)
            skipped.append(existing)
            continue

        if not target_symbol.IsActive:
            target_symbol.Activate()

        counts_by_category[category] += 1

        line_offset_value, cable_type_value, level, route_value = resolve_node_values(
            doc, node, segments_by_id, marked_points, config, document_levels
        )

        el = doc.Create.NewFamilyInstance(
            point, target_symbol, level, StructuralType.NonStructural
        )
        if el:
            if line_offset_value is not None:
                set_double_param(el, config["offset_param_names"], line_offset_value)
            if cable_type_value is not None:
                set_string_param(el, config["cable_param_name"], cable_type_value)
            set_string_param(el, config["route_param_name"], route_value)
            created.append(el)

    return {
        "segments_found": len(segments),
        "created": created,
        "skipped": skipped,
        "counts_by_category": counts_by_category
    }
