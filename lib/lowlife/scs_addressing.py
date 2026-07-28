# -*- coding: utf-8 -*-
"""
Логика нумерации адресов узлов трассы (кнопка RenumberAddresses):
построение графа по узлам маршрута/стоякам, привязка панелей/стояков
как корней, обход в ширину (BFS) и присвоение адресов вида "F1.3".

Работает с обычными dict-записями (не с Revit-элементами напрямую),
поэтому не зависит от Revit API и легко проверяется отдельно.
"""

import math
import re


def pt2(xyz):
    return (xyz.X, xyz.Y)


def dist2(p1, p2):
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    return math.sqrt(dx * dx + dy * dy)


def matches_keywords(text, keywords, exclude_keywords=None):
    """Простая проверка вхождения одного из keywords в text (без учёта регистра)."""
    text_l = (text or u"").lower()

    if exclude_keywords and any(w.lower() in text_l for w in exclude_keywords if w):
        return False

    return any(w.lower() in text_l for w in keywords if w)


def point_to_segment_distance_xy(pt, a, b):
    ax, ay = a
    bx, by = b
    px, py = pt

    abx = bx - ax
    aby = by - ay
    apx = px - ax
    apy = py - ay

    ab_len2 = abx * abx + aby * aby
    if ab_len2 == 0:
        return math.sqrt((px - ax) ** 2 + (py - ay) ** 2), 0.0

    t = float(apx * abx + apy * aby) / float(ab_len2)
    t_clamped = max(0.0, min(1.0, t))

    cx = ax + t_clamped * abx
    cy = ay + t_clamped * aby

    dx = px - cx
    dy = py - cy

    return math.sqrt(dx * dx + dy * dy), t


def line_parameter_xy(pt, a, b):
    ax, ay = a
    bx, by = b
    px, py = pt

    abx = bx - ax
    aby = by - ay
    ab_len2 = abx * abx + aby * aby
    if ab_len2 == 0:
        return 0.0

    apx = px - ax
    apy = py - ay
    return float(apx * abx + apy * aby) / float(ab_len2)


def add_neighbor(node_a, node_b):
    if node_b["id"] not in node_a["neighbor_ids"]:
        node_a["neighbor_ids"].append(node_b["id"])
    if node_a["id"] not in node_b["neighbor_ids"]:
        node_b["neighbor_ids"].append(node_a["id"])


def get_floor_code_from_view(view, basement_keyword=u"цоколь", floor_keyword=u"этаж"):
    """
    Код этажа вида "F3" / "F-1" из имени уровня (или вида, если уровня нет).
    """
    level_name = u""

    try:
        if hasattr(view, "GenLevel") and view.GenLevel:
            level_name = view.GenLevel.Name
    except:
        pass

    if not level_name:
        try:
            level_name = view.Name
        except:
            level_name = u""

    name_lower = level_name.lower()

    if basement_keyword and basement_keyword.lower() in name_lower:
        return u"F-1", level_name

    if floor_keyword:
        m = re.search(re.escape(floor_keyword.lower()) + r'\s*(-?\d+)', name_lower, re.IGNORECASE)
        if m:
            return u"F{}".format(m.group(1)), level_name

    matches = re.findall(r'-?\d+', level_name)
    if matches:
        return u"F{}".format(matches[0]), level_name

    return u"F?", level_name


def classify_point(point, lines, strict_tol, offset_tol, marked_tol, end_tol):
    """
    Определяет ближайшую линию маршрута и классификацию точки:
    - для стояков/панелей: OFFSET_MARKER (рядом с линией) или UNCONNECTED
    - для обычных узлов маршрута: NODE_STRICT / NODE_ON_LINE /
      NODE_NEAR_ENDPOINT / OFFSET_MARKER / UNCONNECTED

    Ожидает в point булевы флаги "is_riser" и "is_panel" (их проставляет
    вызывающий код — по ElementId типа для стояков, по ключевым словам
    для панелей).
    """
    pt = point["point"]
    is_marked = point.get("is_riser") or point.get("is_panel")

    loose_tol = marked_tol if is_marked else offset_tol

    best_line = None
    best_dist = 1e9
    best_end_dist = 1e9

    for line in lines:
        d, t = point_to_segment_distance_xy(pt, line["p1"], line["p2"])
        d1 = dist2(pt, line["p1"])
        d2 = dist2(pt, line["p2"])
        end_d = min(d1, d2)

        if d < best_dist:
            best_dist = d
            best_line = line
            best_end_dist = end_d

    is_on_line_strict = best_dist <= strict_tol
    is_on_line_loose = best_dist <= loose_tol
    is_endpoint_like = best_end_dist <= end_tol

    if is_marked:
        cls = "OFFSET_MARKER" if is_on_line_loose else "UNCONNECTED"
    else:
        if is_on_line_strict and is_endpoint_like:
            cls = "NODE_STRICT"
        elif is_on_line_strict:
            cls = "NODE_ON_LINE"
        elif is_on_line_loose and is_endpoint_like:
            cls = "NODE_NEAR_ENDPOINT"
        elif is_on_line_loose:
            cls = "OFFSET_MARKER"
        else:
            cls = "UNCONNECTED"

    point["nearest_line_id"] = best_line["id"] if best_line else None
    point["classification"] = cls


def find_nearest_real_node(source_point, real_nodes):
    best = None
    best_d = 1e9
    sp = source_point["point"]

    for n in real_nodes:
        d = dist2(sp, n["point"])
        if d < best_d:
            best_d = d
            best = n

    return best, best_d


def real_nodes_on_line(line, real_nodes, tol):
    result = []
    for n in real_nodes:
        d, t_raw = point_to_segment_distance_xy(n["point"], line["p1"], line["p2"])
        if d <= tol and -0.05 <= t_raw <= 1.05:
            t = line_parameter_xy(n["point"], line["p1"], line["p2"])
            result.append((t, n))
    result.sort(key=lambda x: x[0])
    return result


def find_best_real_node_for_offset(offset_node, lines_by_id, real_nodes, tol):
    line_id = offset_node.get("nearest_line_id")
    if line_id is None or line_id not in lines_by_id:
        return None

    line = lines_by_id[line_id]
    candidates = real_nodes_on_line(line, real_nodes, tol)

    if not candidates:
        return None

    best = None
    best_d = 1e9
    p = offset_node["point"]

    for t, node in candidates:
        d = dist2(p, node["point"])
        if d < best_d:
            best_d = d
            best = node

    return best
