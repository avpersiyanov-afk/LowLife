# -*- coding: utf-8 -*-
"""
Чистая логика кнопки «СОУЭ — расстановка типовой этаж»
(SOUE.panel/PlaceTypicalFloor) без Revit API — покрыта тестами
(tests/test_soue_floor_core.py). Revit-часть — soue_floor.py.

Координаты — в одной системе (футы, план XY), какие именно — решает
вызывающий код (soue_floor.py работает в координатах связи).
"""

import math

from lowlife.ss1_easy_core import normalize, split_names  # noqa: F401 — реэкспорт

# Роли помещений.
ROLE_APARTMENT = "apartment"
ROLE_CORRIDOR = "corridor"
ROLE_LIFT_HALL = "lift_hall"
ROLES = (ROLE_APARTMENT, ROLE_CORRIDOR, ROLE_LIFT_HALL)

# Способ установки.
MOUNT_WALL = "wall"
MOUNT_CEILING = "ceiling"


def name_rank(name, names):
    """Место имени помещения в списке names (без учёта регистра) или None."""
    wanted = normalize(name)
    for index, candidate in enumerate(names):
        if normalize(candidate) == wanted:
            return index
    return None


def classify_rooms(rooms, apartment_names, corridor_names, lift_hall_names):
    """
    Какие помещения оснащаются и чем.

    rooms — [(ключ, имя помещения, имя лота, отметка или None)].

    Квартиры: в каждом лоте — одно помещение из apartment_names (список по
    приоритету: «Прихожая, Холл» — сначала прихожая, нет её — холл), из
    равных по приоритету — с минимальной отметкой (у двухуровневой
    квартиры — нижнее). Помещение квартиры без имени лота ставится само по
    себе — с предупреждением (ключ в no_lot).

    МОП: помещения из corridor_names / lift_hall_names, кроме лежащих в
    лоте квартиры (коридор внутри квартиры с её именем лота — не МОП).
    Если имя есть и в списке квартир, и в списке МОП, помещение без имени
    лота считается МОП.

    Возвращает (назначения {ключ: роль}, no_lot [ключи]).
    """
    groups = {}
    no_lot = []
    mop_names = list(corridor_names) + list(lift_hall_names)
    for key, name, lot, elevation in rooms:
        rank = name_rank(name, apartment_names)
        if rank is None:
            continue
        lot_norm = normalize(lot)
        if not lot_norm:
            if name_rank(name, mop_names) is None:
                no_lot.append(key)
            continue
        groups.setdefault(lot_norm, []).append((rank, elevation, key))

    result = {}
    for entries in groups.values():
        def sort_key(entry):
            rank, elevation, _ = entry
            return (rank, elevation is None, elevation if elevation is not None else 0.0)
        result[min(entries, key=sort_key)[2]] = ROLE_APARTMENT
    for key in no_lot:
        result[key] = ROLE_APARTMENT

    apartment_lots = set(groups)
    for key, name, lot, elevation in rooms:
        if key in result:
            continue
        if normalize(lot) in apartment_lots:
            continue
        if name_rank(name, corridor_names) is not None:
            result[key] = ROLE_CORRIDOR
        elif name_rank(name, lift_hall_names) is not None:
            result[key] = ROLE_LIFT_HALL
    return result, no_lot


def grid_cells(min_x, min_y, max_x, max_y, step):
    """
    Деление габарита помещения на клетки со стороной не больше step (по
    каждой оси — поровну). step <= 0 — одна клетка на весь габарит (один
    оповещатель на помещение). Возвращает [(x0, y0, x1, y1)].
    """
    width = max(0.0, max_x - min_x)
    height = max(0.0, max_y - min_y)
    if step and step > 0:
        nx = max(1, int(math.ceil(width / step - 1e-9)))
        ny = max(1, int(math.ceil(height / step - 1e-9)))
    else:
        nx = ny = 1
    dx = width / nx
    dy = height / ny
    cells = []
    for j in range(ny):
        for i in range(nx):
            cells.append((min_x + dx * i, min_y + dy * j,
                          min_x + dx * (i + 1), min_y + dy * (j + 1)))
    return cells


def cell_samples(cell, count=7):
    """
    Точки клетки для поиска точки внутри помещения: сначала центр, дальше —
    узлы сетки count×count по удалению от центра (для Г-образных коридоров,
    где центр клетки вне помещения).
    """
    x0, y0, x1, y1 = cell
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    points = []
    for j in range(count):
        for i in range(count):
            px = x0 + (x1 - x0) * (i + 0.5) / count
            py = y0 + (y1 - y0) * (j + 0.5) / count
            points.append((px, py))
    points.sort(key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
    return [(cx, cy)] + points


def _free_intervals(length, margin, blocked):
    """Отрезок [margin, length - margin] за вычетом интервалов blocked."""
    start, end = margin, length - margin
    if end < start:
        if length <= 0:
            return []
        start = end = length / 2.0
    free = [(start, end)]
    for b0, b1 in sorted(blocked):
        next_free = []
        for f0, f1 in free:
            if b1 <= f0 or b0 >= f1:
                next_free.append((f0, f1))
                continue
            if b0 > f0:
                next_free.append((f0, b0))
            if b1 < f1:
                next_free.append((b1, f1))
        free = next_free
    return free


def wall_point(segments, target, obstacles, margin):
    """
    Точка на стене помещения для настенного оповещателя: ближайшая к
    target (центр помещения или клетки) точка его границы, не ближе margin
    к углам сегмента и вне зон obstacles (двери, окна).

    segments  — [(x1, y1, x2, y2)] сегменты границы помещения;
    target    — (x, y);
    obstacles — [(x, y, радиус)]: точка стены ближе радиуса к ним не годится.

    Возвращает (x, y, nx, ny, свободна) — точку, единичную нормаль к стене
    в сторону target и признак, что точка вне зон obstacles (False — все
    стены заняты, взята ближайшая точка без учёта препятствий) — или None,
    если сегментов нет.
    """
    tx, ty = target
    best = None
    fallback = None
    for x1, y1, x2, y2 in segments:
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 1e-9:
            continue
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        t_target = (tx - x1) * ux + (ty - y1) * uy

        def at(t):
            return x1 + ux * t, y1 + uy * t

        # нормаль в сторону target
        nx, ny = -uy, ux
        if (tx - x1) * nx + (ty - y1) * ny < 0:
            nx, ny = -nx, -ny

        t_plain = min(max(t_target, 0.0), length)
        px, py = at(t_plain)
        distance = math.hypot(px - tx, py - ty)
        if fallback is None or distance < fallback[0]:
            fallback = (distance, (px, py, nx, ny, False))

        blocked = []
        for ox, oy, radius in obstacles:
            along = (ox - x1) * ux + (oy - y1) * uy
            across = abs((ox - x1) * -uy + (oy - y1) * ux)
            if across >= radius:
                continue
            half = math.sqrt(radius * radius - across * across)
            blocked.append((along - half, along + half))

        for f0, f1 in _free_intervals(length, margin, blocked):
            t = min(max(t_target, f0), f1)
            px, py = at(t)
            distance = math.hypot(px - tx, py - ty)
            if best is None or distance < best[0]:
                best = (distance, (px, py, nx, ny, True))

    if best is not None:
        return best[1]
    if fallback is not None:
        return fallback[1]
    return None

