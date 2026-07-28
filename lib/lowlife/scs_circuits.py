# -*- coding: utf-8 -*-
"""
Логика расчёта цепей и длин кабеля (кнопка SyncCircuitsAndLengths):
поиск кратчайшего пути (A*) по графу адресованных узлов маршрута
(построенному RenumberAddresses), расчёт длины по типам прокладки,
классификация и нумерация цепей, формирование текста по узлам.

Работает с обычными dict/graph-структурами, не зависит от Revit API.
"""

from collections import defaultdict, deque
import heapq

FT_TO_M = 0.3048

_BAD_TEXT_VALUES = set(["0", "0.0", "0,0", "-", "None", "none", "NULL", "null"])


def norm(x):
    if x is None:
        return None
    x = unicode(x).strip()
    return x if x else None


def clean_text_value(x):
    """norm() плюс отсев "пустышек" вроде "0"/"-"/"None", которые Revit иногда возвращает вместо реального текста."""
    x = norm(x)
    if not x:
        return None
    return None if x in _BAD_TEXT_VALUES else x


def split_multi_value(x):
    """"F1.2, F1.3" -> ["F1.2", "F1.3"] — для параметров с несколькими родительскими адресами."""
    x = norm(x)
    if not x:
        return []
    parts = [norm(p) for p in x.split(",")]
    return [p for p in parts if p]


def build_graph(segments, parents_by_id):
    """
    segments: {id: {...}}, parents_by_id: {id: [parent_id, ...]}.
    Возвращает (graph, broken_links) — граф смежности и список ссылок
    на несуществующие родительские адреса.
    """
    graph = defaultdict(list)
    broken_links = []

    for sid, parents in parents_by_id.items():
        for parent in parents:
            if parent in segments:
                graph[sid].append(parent)
                graph[parent].append(sid)
            else:
                broken_links.append(u"{} -> {}".format(sid, parent))

    return graph, broken_links


def bfs_component(graph, start):
    """Множество id, достижимых из start по графу (для диагностики обрывов)."""
    visited = set()
    q = deque([start])

    while q:
        cur = q.popleft()
        if cur in visited:
            continue
        visited.add(cur)
        for nb in graph.get(cur, []):
            if nb not in visited:
                q.append(nb)

    return visited


def find_closest_pair_between_sets(segments, start_set, end_set):
    """Ближайшая пара узлов между двумя множествами (где именно порвана связность)."""
    best_a = None
    best_b = None
    best_d = float('inf')

    if not start_set or not end_set:
        return None, None, None

    for a in start_set:
        a_pt = segments[a]["pt"]
        for b in end_set:
            b_pt = segments[b]["pt"]
            d = a_pt.DistanceTo(b_pt)
            if d < best_d:
                best_d = d
                best_a = a
                best_b = b

    return best_a, best_b, best_d


def find_nearest_segment_id(point, segments):
    """
    Ближайший узел маршрута к произвольной точке — только по XY, без
    учёта Z. Линию/устройство подводят друг к другу в плане, а высота
    подключения (например, розетка на 300мм, узел маршрута на потолке)
    не должна мешать найти правильный ближайший узел: по 3D-расстоянию
    другой, чисто случайно более близкий по высоте узел мог выиграть у
    правильного, находящегося прямо под/над точкой в плане.

    Вертикальная составляющая длины кабеля по-прежнему считается отдельно
    (см. calc_lengths / raw_vertical_ft в SyncCircuitsAndLengths) — здесь
    она сознательно игнорируется, только для выбора узла.
    """
    if point is None or not segments:
        return None, None

    nearest_sid = None
    nearest_dist = float('inf')

    for sid, seg in segments.items():
        pt = seg["pt"]
        dx = point.X - pt.X
        dy = point.Y - pt.Y
        d = (dx * dx + dy * dy) ** 0.5
        if d < nearest_dist:
            nearest_dist = d
            nearest_sid = sid

    return nearest_sid, nearest_dist


def _edge_cost(segments, a, b):
    a_pt = segments[a]["pt"]
    b_pt = segments[b]["pt"]
    return abs(a_pt.X - b_pt.X) + abs(a_pt.Y - b_pt.Y) + abs(a_pt.Z - b_pt.Z)


def _heuristic(segments, a, b):
    return segments[a]["pt"].DistanceTo(segments[b]["pt"])


def astar_path(segments, graph, start, end):
    """Кратчайший (по Манхэттену) путь между двумя адресами узлов, или []."""
    if start == end:
        return [start]

    open_heap = []
    heapq.heappush(open_heap, (_heuristic(segments, start, end), start))

    came = {}
    g = {start: 0.0}
    closed = set()

    while open_heap:
        _, current = heapq.heappop(open_heap)

        if current in closed:
            continue

        if current == end:
            path = []
            while current in came:
                path.append(current)
                current = came[current]
            path.append(start)
            path.reverse()
            return path

        closed.add(current)

        for nb in graph.get(current, []):
            if nb in closed:
                continue

            tentative_g = g[current] + _edge_cost(segments, current, nb)

            if tentative_g < g.get(nb, float('inf')):
                came[nb] = current
                g[nb] = tentative_g
                f_score = tentative_g + _heuristic(segments, nb, end)
                heapq.heappush(open_heap, (f_score, nb))

    return []


def calc_lengths(segments, path, install_tray_key, install_pipe_key, install_pipe_open_key):
    """
    Суммарная длина пути (в метрах) и её разбивка по способу прокладки,
    определяемому по параметру "install" узла, В КОТОРЫЙ ПРИХОДИТ отрезок
    (т.е. install следующего по пути узла).
    """
    total_ft = 0.0
    tray_ft = 0.0
    pipe_ft = 0.0
    pipe_open_ft = 0.0

    for i in range(len(path) - 1):
        a = segments[path[i]]["pt"]
        b = segments[path[i + 1]]["pt"]

        d = abs(a.X - b.X) + abs(a.Y - b.Y) + abs(a.Z - b.Z)
        total_ft += d

        install = (segments[path[i + 1]]["install"] or "").strip()

        if install_pipe_open_key and install_pipe_open_key in install:
            pipe_open_ft += d
        elif install_tray_key and install_tray_key in install:
            tray_ft += d
        elif install_pipe_key and install_pipe_key in install:
            pipe_ft += d

    return (
        total_ft * FT_TO_M,
        tray_ft * FT_TO_M,
        pipe_ft * FT_TO_M,
        pipe_open_ft * FT_TO_M
    )


def balance_round_parts(total, parts):
    """
    Округляет total и parts до целых так, чтобы сумма округлённых parts
    точно равнялась округлённому total (разницу добавляет к наибольшей части).
    Возвращает [round(total), *rounded_parts].
    """
    total_round = int(round(total))
    rounded_parts = [int(round(x)) for x in parts]
    diff = total_round - sum(rounded_parts)

    if diff != 0 and rounded_parts:
        max_index = max(range(len(parts)), key=lambda i: parts[i])
        rounded_parts[max_index] += diff

    return [total_round] + rounded_parts


def classify_circuit_type(name_type_value, key_fo, key_utp, key_power):
    """Тип цепи (FO/UTP/POWER/None) по значению параметра-наименования цепи."""
    if not name_type_value:
        return None

    val_l = name_type_value.lower()

    if key_fo and key_fo.lower() in val_l:
        return "FO"
    if key_utp and key_utp.lower() in val_l:
        return "UTP"
    if key_power and key_power.lower() in val_l:
        return "POWER"

    return None


def make_load_name(type_code, device_address):
    """Имя нагрузки из обозначения типа устройства + адреса экземпляра."""
    if type_code and device_address:
        return u"{}.{}".format(type_code, device_address)
    if type_code:
        return unicode(type_code)
    if device_address:
        return unicode(device_address)
    return None


def build_segment_list_text(load_names, fo_count, utp_count):
    """Текст для параметра узла маршрута со списком цепей, проходящих через него."""
    lines = sorted(set(n for n in load_names if n))

    summary = [u"Всего кабелей:"]
    if fo_count > 0:
        summary.append(u"FO-{} шт.".format(fo_count))
    if utp_count > 0:
        summary.append(u"UTP-{} шт.".format(utp_count))

    if lines:
        return u"\n".join(lines + summary)
    return u"\n".join(summary)
