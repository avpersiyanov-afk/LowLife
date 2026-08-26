# -*- coding: utf-8 -*-
"""
Нумерация адресов узлов трассы — общее тело кнопки «Адреса узлов» для
любой дисциплины (СКС / СКУД / далее СПС, СОУЭ).

Сам алгоритм (классификация точек относительно линий, Дейкстра до корня,
обход в глубину) живёт в scs_addressing.py и от дисциплины не зависит.
Здесь — сборка элементов из документа, применение алгоритма и запись
результата, с дисциплиной, заданной конфигом.
"""

from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, LocationCurve
)

from lowlife.geometry import get_point, get_document_levels
from lowlife.params import get_string_param, set_string_param, set_param_any
from lowlife.scs import classify_element, get_workset_name, detect_cable_type
from lowlife.scs_addressing import (
    pt2, dist2, add_neighbor, get_floor_code_for_level, classify_point,
    find_nearest_real_node, find_best_real_node_for_offset,
    point_to_segment_distance_xy, line_parameter_xy,
    build_shortest_path_tree, depth_first_order, select_root_sources,
    attach_roots, compute_prev_address_values
)
from lowlife.scs_circuits import find_nearest_segment_id

MM_IN_FOOT = 304.8
STRICT = 30.0 / MM_IN_FOOT
OFFSET = 210.0 / MM_IN_FOOT
MARKED_TOL = 150.0 / MM_IN_FOOT
END_TOL = 50.0 / MM_IN_FOOT

# Запас вокруг области узлов маршрута при выборе корней обхода —
# см. select_root_sources.
ROOT_SEARCH_MARGIN_MM = 20000.0
ROOT_SEARCH_MARGIN = ROOT_SEARCH_MARGIN_MM / MM_IN_FOOT


def is_empty(s):
    return s is None or unicode(s).strip() == u""


def collect_lines_and_points(doc, view, config):
    """
    Линии и точки на активном виде.

    Панель распознаётся по ключевым словам, и если задан
    workset_filter_key — дополнительно по рабочему набору: на одном плане
    могут лежать панели разных дисциплин, подходящие под похожие слова.
    """
    collector = FilteredElementCollector(doc, view.Id) \
        .OfCategory(BuiltInCategory.OST_GenericModel) \
        .WhereElementIsNotElementType()

    route_type_id = config["route_type_id"]
    riser_type_id = config["riser_type_id"]
    addr_param = config["addr_param_name"]
    workset_param_name = config.get("workset_param_name")
    workset_filter_key = config.get("workset_filter_key")

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
        is_route = (type_id == route_type_id)
        is_riser = (type_id == riser_type_id)
        is_panel = classify_element(
            el, [("panel", config["panel_keywords"], config["panel_exclude_keywords"])]
        ) == "panel"

        if is_panel and workset_filter_key:
            ws = get_workset_name(el, workset_param_name)
            if not ws or workset_filter_key.lower() not in ws.lower():
                is_panel = False

        if not (is_route or is_riser or is_panel):
            continue

        points.append({
            "id": el.Id.IntegerValue,
            "element": el,
            "point": pt2(pt),
            "is_route": is_route,
            "is_riser": is_riser,
            "is_panel": is_panel,
            "addr_original": get_string_param(el, addr_param),
            "addr": get_string_param(el, addr_param),
            "classification": None,
            "nearest_line_id": None,
            "neighbor_ids": [],
            "parent_id": None,
            "parent_addr": None,
            "write_value": None
        })

    return lines, points


def link_nodes_along_lines(lines, real_nodes):
    """Соседство узлов вдоль каждой линии — соседними считаются подряд идущие по линии."""
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


def assign_addresses(ordered_routes, floor_code, renumber_existing):
    """Проставляет node["addr"] — либо всем заново, либо только пустым."""
    if renumber_existing:
        num = 1
        for n in ordered_routes:
            n["addr"] = u"{}.{}".format(floor_code, num)
            num += 1
        return

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


def assign_root_addresses(panels, risers, floor_code):
    """
    Панели/стояки — корни обхода, сами не входят в route_points, но тоже
    получают адрес: отдельный счётчик на этаж для каждой категории
    (P для панелей/контроллеров, R для стояков), не связанный со счётчиком
    обычных узлов маршрута. Порядок — по координатам, чтобы результат был
    стабильным между запусками (порядок коллектора Revit не гарантирован).
    Всегда пересчитывается заново (не наследует старое ручное значение).
    """
    panel_num = 1
    for n in sorted(panels, key=lambda n: (n["point"][0], n["point"][1], n["id"])):
        n["addr"] = u"{}.P{}".format(floor_code, panel_num)
        panel_num += 1

    riser_num = 1
    for n in sorted(risers, key=lambda n: (n["point"][0], n["point"][1], n["id"])):
        n["addr"] = u"{}.R{}".format(floor_code, riser_num)
        riser_num += 1


def assign_cable_types(real_nodes, lines_by_id):
    """
    Тип прокладки кабеля узла маршрута — по параметру сегмента К
    РОДИТЕЛЮ (в сторону панели), не от него. Нужно направление —
    parent_id уже должен быть построен (build_shortest_path_tree),
    поэтому вызывать после него.

    Способ прокладки на стыке (например, труба переходит в лоток) должен
    смениться ровно в точке стыка, а не позже: если узел B стоит на
    стыке "труба(A-B) -> лоток(B-...)", отрезок A-B ещё в трубе, а
    отрезок от B дальше — уже в лотке. Сохраняя на B тип сегмента к
    родителю (A-B, труба), scs_circuits.calc_lengths — отрезок
    "предыдущий узел -> B" по install узла, ИЗ КОТОРОГО тот выходит —
    получает правильный тип. У корневого узла (ближайшего к панели,
    своего родителя в дереве нет) — берётся любой примыкающий сегмент,
    отдельного сегмента к родителю там просто не существует.

    Записывает node["cable_type_value"], если сегмент нашёлся и тип
    определился — write_addresses потом пишет его в параметр.
    """
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


def renumber_addresses(doc, view, config, renumber_existing):
    """
    Полный проход нумерации: сбор, классификация, граф, корни, Дейкстра,
    DFS, присвоение адресов и вычисление «предыдущего адреса».

    Возвращает dict со всем нужным для записи и отчёта. Записи в документ
    НЕ делает — вызывающий пишет внутри своей транзакции (см. write_addresses).
    """
    floor_code, level_name = get_floor_code_for_level(view, get_document_levels(doc))

    lines, points = collect_lines_and_points(doc, view, config)

    if not lines:
        return {"error": u"Не найдены линейные элементы на активном виде."}

    for p in points:
        classify_point(p, lines, STRICT, OFFSET, MARKED_TOL, END_TOL)

    all_points_by_id = dict((p["id"], p) for p in points)
    lines_by_id = dict((l["id"], l) for l in lines)

    panels = [p for p in points if p["is_panel"]]
    risers = [p for p in points if p["is_riser"]]
    route_points = [p for p in points if p["is_route"]]

    if not route_points:
        return {"error": u"Не найдены узлы маршрута выбранного типа."}

    real_nodes = [p for p in route_points
                  if p["classification"] in ("NODE_STRICT", "NODE_ON_LINE", "NODE_NEAR_ENDPOINT")]
    offset_nodes = [p for p in route_points if p["classification"] == "OFFSET_MARKER"]
    unconnected_nodes = [p for p in route_points if p["classification"] == "UNCONNECTED"]

    link_nodes_along_lines(lines, real_nodes)

    root_sources, far_sources, fallback_risers = select_root_sources(panels, risers, real_nodes, ROOT_SEARCH_MARGIN)
    unique_roots = attach_roots(root_sources, lines_by_id, real_nodes, OFFSET)
    fallback_roots = attach_roots(fallback_risers, lines_by_id, real_nodes, OFFSET)

    real_nodes_by_id = dict((n["id"], n) for n in real_nodes)
    _, effective_roots = build_shortest_path_tree(
        real_nodes_by_id, unique_roots, real_nodes, dist2, fallback_roots=fallback_roots
    )
    ordered_real_nodes = depth_first_order(real_nodes_by_id, effective_roots)

    assign_cable_types(real_nodes, lines_by_id)

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

    assign_addresses(ordered_routes, floor_code, renumber_existing)
    assign_root_addresses(panels, risers, floor_code)

    compute_prev_address_values(real_nodes, real_nodes_by_id, all_points_by_id)

    for n in offset_nodes:
        best_real = find_best_real_node_for_offset(n, lines_by_id, real_nodes, OFFSET)

        if best_real is None:
            best_real, _ = find_nearest_real_node(n, real_nodes)

        n["write_value"] = best_real["addr"] if (best_real and not is_empty(best_real["addr"])) else u""

    for n in unconnected_nodes:
        n["write_value"] = u""

    return {
        "error": None,
        "floor_code": floor_code,
        "level_name": level_name,
        "points": points,
        "route_points": route_points,
        "ordered_routes": ordered_routes,
        "panels": panels,
        "risers": risers,
        "real_nodes": real_nodes,
        "all_points_by_id": all_points_by_id,
        "root_sources": root_sources,
        "far_sources": far_sources,
    }


def write_addresses(route_points, panels, risers, config, renumber_existing):
    """
    Пишет адреса, «предыдущий адрес» и тип прокладки кабеля узлам
    маршрута, и адрес — панелям/стоякам (у них «предыдущего адреса» нет,
    они сами корни). Вызывать внутри revit.Transaction.
    """
    addr_param = config["addr_param_name"]
    addr_prev_param = config["addr_prev_param_name"]
    cable_param_name = config.get("cable_param_name")

    changed = []
    skipped = []

    for p in route_points:
        if renumber_existing or is_empty(p["addr_original"]):
            set_string_param(p["element"], addr_param, p["addr"] if p["addr"] else u"")
            set_string_param(p["element"], addr_prev_param, p["write_value"])
            cable_type_value = p.get("cable_type_value")
            if cable_param_name and cable_type_value is not None:
                set_string_param(p["element"], cable_param_name, cable_type_value)
            changed.append(p)
        else:
            skipped.append(p)

    for p in panels + risers:
        set_string_param(p["element"], addr_param, p["addr"] if p["addr"] else u"")
        changed.append(p)

    return changed, skipped


def write_nearest_nodes(doc, route_points, targets, config):
    """
    Пишет «Ближайший узел маршрута» переданным элементам (панели/устройства
    дисциплины) — адрес ближайшего адресованного узла по XY.

    Всегда пересчитывается и перезаписывается, даже если значение уже
    было записано раньше (то же поведение, что у СКС). Вызывать внутри
    revit.Transaction.
    """
    nearest_segment_param = config["nearest_segment_param"]

    segments_by_addr = {}
    for p in route_points:
        pt = get_point(p["element"])
        if pt is None or is_empty(p["addr"]):
            continue
        segments_by_addr[p["addr"]] = {"pt": pt}

    if not segments_by_addr:
        return 0

    written = 0

    for el in targets:
        pt = get_point(el)
        if pt is None:
            continue
        nearest_sid, _ = find_nearest_segment_id(pt, segments_by_addr)
        if nearest_sid and set_param_any(el, nearest_segment_param, nearest_sid):
            written += 1

    return written
