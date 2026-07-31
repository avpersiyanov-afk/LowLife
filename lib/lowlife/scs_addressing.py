# -*- coding: utf-8 -*-
"""
Логика нумерации адресов узлов трассы (кнопка RenumberAddresses):
построение графа по узлам маршрута/стоякам, привязка панелей/стояков
как корней, кратчайший путь до корня (Дейкстра) и присвоение адресов
вида "F1.3" в порядке обхода в глубину (DFS) по получившемуся дереву.

Работает с обычными dict-записями (не с Revit-элементами напрямую),
поэтому не зависит от Revit API и легко проверяется отдельно.
"""

import heapq
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


def _base_floor_code(level_name, basement_keyword=u"цоколь", floor_keyword=u"этаж"):
    """Код этажа вида "F3" / "F-1" из имени уровня/вида, без учёта отметки."""
    name_lower = level_name.lower()

    if basement_keyword and basement_keyword.lower() in name_lower:
        return u"F-1"

    if floor_keyword:
        m = re.search(re.escape(floor_keyword.lower()) + r'\s*(-?\d+)', name_lower, re.IGNORECASE)
        if m:
            return u"F{}".format(m.group(1))

    matches = re.findall(r'-?\d+', level_name)
    if matches:
        return u"F{}".format(matches[0])

    return u"F?"


def get_floor_code_for_level(view, all_levels, basement_keyword=u"цоколь", floor_keyword=u"этаж"):
    """
    Код этажа вида "F3" / "F-1" из имени уровня вида (или имени вида, если
    уровня нет) — с суффиксом, различающим несколько уровней с ОДИНАКОВЫМ
    именем на разной отметке (например, два уровня "Этаж -1" на разных
    отметках в разных секциях/корпусах). Без такого различения оба уровня
    получили бы один и тот же код F-1, и адреса узлов на них совпадали бы
    (что ломает поиск ближайшего узла маршрута — SyncCircuitsAndLengths не
    может отличить одинаковый адрес на разных этажах).

    Среди всех уровней документа с тем же именем, что и уровень текущего
    вида, сортирует их по отметке (Elevation) — самый нижний по высоте
    получает базовый код (F-1), второй по высоте — F-1.1, третий —
    F-1.2 и т.д. Порядок не зависит от того, с какого из одноимённых
    уровней запущена кнопка — все они отсортированы одинаково.

    Если у вида нет привязанного уровня (GenLevel) — просто использует
    имя вида, без суффикса (различать нечего, all_levels не при чём).

    all_levels — результат geometry.get_document_levels(doc) (уже
    отсортирован по Elevation).
    """
    current_level = None

    try:
        if hasattr(view, "GenLevel") and view.GenLevel:
            current_level = view.GenLevel
    except:
        pass

    if current_level is None:
        level_name = u""
        try:
            level_name = view.Name
        except:
            pass
        return _base_floor_code(level_name, basement_keyword, floor_keyword), level_name

    level_name = current_level.Name
    base_code = _base_floor_code(level_name, basement_keyword, floor_keyword)

    same_name_levels = sorted(
        [lv for lv in all_levels if lv.Name == level_name],
        key=lambda lv: lv.Elevation
    )

    index = 0
    for i, lv in enumerate(same_name_levels):
        if lv.Id == current_level.Id:
            index = i
            break

    floor_code = base_code if index == 0 else u"{}.{}".format(base_code, index)

    return floor_code, level_name


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


def build_shortest_path_tree(nodes_by_id, roots, all_nodes, dist_fn=dist2):
    """
    Многоисточниковый Дейкстра по графу узлов (сосед — node["neighbor_ids"]),
    вес ребра — dist_fn(a["point"], b["point"]) (реальное расстояние, а не
    число шагов графа, как в BFS). Устанавливает node["parent_id"] для
    каждого достижимого узла на "ближайший по расстоянию" предыдущий узел
    — родителям (корням) их parent_id не трогает.

    Узлы, не связанные ни с одним из roots (отдельная связная компонента),
    всё равно получают дерево: по очереди берутся как локальные корни
    (без родителя) после того, как основной обход исчерпан.

    Возвращает (visited, effective_roots) — множество id посещённых узлов
    и полный список корней, включая добавленные локальные (нужен для
    depth_first_order, чтобы не потерять эти узлы при обходе).
    """
    dist = {}
    visited = set()
    heap = []
    effective_roots = list(roots)

    def relax_from(node_id, base_dist):
        current = nodes_by_id[node_id]
        for nb_id in current.get("neighbor_ids", []):
            if nb_id not in nodes_by_id or nb_id in visited:
                continue
            nb = nodes_by_id[nb_id]
            candidate = base_dist + dist_fn(current["point"], nb["point"])
            if candidate < dist.get(nb_id, float("inf")):
                dist[nb_id] = candidate
                nb["parent_id"] = node_id
                heapq.heappush(heap, (candidate, nb_id))

    def drain():
        while heap:
            d, node_id = heapq.heappop(heap)
            if node_id in visited:
                continue
            visited.add(node_id)
            relax_from(node_id, d)

    for r in roots:
        dist[r["id"]] = 0.0
        heapq.heappush(heap, (0.0, r["id"]))

    drain()

    remaining = sorted(
        [n for n in all_nodes if n["id"] not in visited],
        key=lambda n: (n["point"][0], n["point"][1], n["id"])
    )

    for seed in remaining:
        if seed["id"] in visited:
            continue
        effective_roots.append(seed)
        dist[seed["id"]] = 0.0
        heapq.heappush(heap, (0.0, seed["id"]))
        drain()

    return visited, effective_roots


def depth_first_order(nodes_by_id, roots):
    """
    Обход в глубину дерева, заданного node["parent_id"] (например, после
    build_shortest_path_tree): вдоль каждой ветки — подряд, до конца,
    только потом переход к следующей ветке. В отличие от обхода в ширину,
    даёт узлам одной физической ветки последовательные номера, а не
    вперемешку с соседними ветками.

    roots — узлы, с которых начинать (обычно effective_roots из
    build_shortest_path_tree). Итеративно (без рекурсии) — безопасно для
    длинных цепочек узлов.
    """
    children_by_id = {}

    for node in nodes_by_id.values():
        pid = node.get("parent_id")
        if pid is not None and pid in nodes_by_id:
            children_by_id.setdefault(pid, []).append(node)

    for kids in children_by_id.values():
        kids.sort(key=lambda n: (n["point"][0], n["point"][1], n["id"]), reverse=True)

    order = []
    visited = set()

    for root in roots:
        if root["id"] in visited:
            continue

        stack = [root]

        while stack:
            node = stack.pop()
            if node["id"] in visited:
                continue
            visited.add(node["id"])
            order.append(node)

            for child in children_by_id.get(node["id"], []):
                if child["id"] not in visited:
                    stack.append(child)

    return order


def select_root_sources(panels, risers, real_nodes, margin):
    """
    Выбирает источники корней обхода (панели или стояки) из точек,
    физически находящихся в пределах области реальных узлов маршрута
    (плюс margin) — без этой проверки панель, случайно подошедшая по
    ключевым словам, но находящаяся в другом конце здания/проекта, всё
    равно "прилипала" бы к ближайшему узлу через резервный поиск без
    ограничения расстояния (find_nearest_real_node).

    Приоритет — панели: если хотя бы одна панель попадает в область,
    корнями становятся только близкие панели (далёкие панели просто
    отбрасываются, даже если они реальные — иначе они бы увели ветку от
    настоящего корня этажа). Если ни одна панель не попала в область,
    пробуются стояки по тому же правилу.

    Возвращает (root_sources, far_sources) — источники-корни и
    отброшенные как слишком далёкие (для отчёта).
    """
    if real_nodes:
        xs = [n["point"][0] for n in real_nodes]
        ys = [n["point"][1] for n in real_nodes]
        root_area = (
            min(xs) - margin, max(xs) + margin,
            min(ys) - margin, max(ys) + margin
        )
    else:
        root_area = None

    def in_root_area(pt):
        if root_area is None:
            return True
        x_min, x_max, y_min, y_max = root_area
        return x_min <= pt[0] <= x_max and y_min <= pt[1] <= y_max

    near_panels = [p for p in panels if in_root_area(p["point"])]
    near_panel_ids = set(p["id"] for p in near_panels)
    far_panels = [p for p in panels if p["id"] not in near_panel_ids]

    if near_panels:
        return near_panels, far_panels

    near_risers = [r for r in risers if in_root_area(r["point"])]
    near_riser_ids = set(r["id"] for r in near_risers)
    far_risers = [r for r in risers if r["id"] not in near_riser_ids]

    return near_risers, far_panels + far_risers
