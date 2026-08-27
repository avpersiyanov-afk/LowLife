# -*- coding: utf-8 -*-
"""
Кольцевой шлейф СПС на структурной схеме — ломаная линия панель ->
устройство №1 -> №2 -> ... -> №N -> обратно на панель, в порядке адреса
(панель.шлейф.номер, см. lowlife.fire_alarm.parse_device_address /
group_devices_by_loop) — реальный физический порядок кольцевого
интерфейса, а не топология "шина" (см. sot_schematic.sync_cable_connections
— тот же приём для одного общего шкафа СОТ/СПС, но там порядок устройств
не важен и достаточно одной сборной линии до него).

Координаты панели/устройств берутся из уже размещённых на схеме экземпляров
схемных семейств — эта функция вызывается ПОСЛЕ sot_schematic.sync_levels,
когда все узлы уже стоят на месте (см. node_points_from_state).

Это ТОПОЛОГИЧЕСКАЯ схема, не трассировка: отрезки идут по прямой между
фактическими точками узлов на виде, как и просил пользователь ("ломаная
через устройства по адресу"), а не огибают чужие рамки — полноценная
трассировка с обходом препятствий (в духе A* из scs_circuits/
SyncCircuitsAndLengths) в объём этой кнопки не входит. Единственная
защита от наложений — совпадающие/накладывающиеся отрезки одного и того
же кольца (типичный случай — кольцо из одного устройства, где "туда" и
"обратно" идут по одному и тому же отрезку): между ними выдерживается
зазор LOOP_LINE_GAP_MM.
"""

from lowlife.sot_schematic import draw_segment, delete_elements, MM_TO_FT

# Зазор между линиями кольца, когда они совпадают/идут параллельно
# (см. докстринг модуля и sync_loop_connections._draw_hop).
LOOP_LINE_GAP_MM = 3.0

_TOL_FT = 1e-6


def node_points_from_state(state):
    """
    {UniqueId реального устройства: (x, y)} — фактические координаты уже
    размещённых на схеме узлов (и устройств, и панелей — панель это тоже
    узел категории "Электрооборудование", если для неё выбран схемный тип
    в настройках), по итоговому state sot_schematic.sync_levels.
    """
    points = {}
    for level_record in state.get("levels", {}).values():
        y = level_record.get("y", 0.0)
        for room_record in level_record.get("rooms", {}).values():
            for uid, dev in room_record.get("devices", {}).items():
                points[uid] = (dev.get("x", 0.0), y)
    return points


def _offset_perp(x1, y1, x2, y2, gap_ft, side):
    """Отрезок (x1,y1)-(x2,y2), сдвинутый на gap_ft перпендикулярно себе (сторона side=+-1)."""
    dx = x2 - x1
    dy = y2 - y1
    length = (dx * dx + dy * dy) ** 0.5
    if length < _TOL_FT:
        return (x1, y1), (x2, y2)
    nx = -dy / length * gap_ft * side
    ny = dx / length * gap_ft * side
    return (x1 + nx, y1 + ny), (x2 + nx, y2 + ny)


def _segment_key(x1, y1, x2, y2):
    """Ключ для обнаружения совпадающих/накладывающихся отрезков независимо от направления обхода."""
    a = (round(x1, 5), round(y1, 5))
    b = (round(x2, 5), round(y2, 5))
    return (a, b) if a <= b else (b, a)


def sync_loop_connections(doc, view, old_loop_line_ids, loops, node_point_by_uid):
    """
    Перерисовывает кольцевые шлейфы заново (как и sync_cable_connections —
    эти линии не редактируются вручную, поэтому диффинг не нужен: старые
    (old_loop_line_ids — state["loop_line_ids"] из прошлого запуска)
    удаляются, новые рисуются по актуальным позициям узлов).

    loops — список колец: [{"panel_uid": uid_или_None, "device_uids":
    [uid, ...]}, ...], device_uids уже в нужном порядке обхода (по
    порядковому номеру адреса — см. fire_alarm.group_devices_by_loop).

    node_point_by_uid — {UniqueId: (x, y)} фактических координат узлов на
    схеме (см. node_points_from_state).

    Кольцо, для которого на схеме нет узла-панели (panel_uid не задан или
    не нашёлся среди node_point_by_uid) или не осталось ни одного
    устройства с известной точкой — пропускается (только его старые линии
    удаляются, новые не рисуются).

    Возвращает новый список id линий (для state).
    """
    delete_elements(doc, old_loop_line_ids)

    gap_ft = LOOP_LINE_GAP_MM * MM_TO_FT
    new_ids = []
    seen_segments = {}

    def draw_hop(x1, y1, x2, y2):
        key = _segment_key(x1, y1, x2, y2)
        count = seen_segments.get(key, 0)
        seen_segments[key] = count + 1

        if count == 0:
            p1, p2 = (x1, y1), (x2, y2)
        else:
            # Совпадающий/накладывающийся отрезок (типично — "обратно" по
            # тому же пути, что и "туда") — отодвигаем на LOOP_LINE_GAP_MM
            # в сторону поочерёдно, чтобы линии не сливались в одну.
            side = 1.0 if count % 2 else -1.0
            step = (count + 1) // 2
            p1, p2 = _offset_perp(x1, y1, x2, y2, gap_ft * step, side)

        elem = draw_segment(doc, view, p1[0], p1[1], p2[0], p2[1])
        if elem is not None:
            new_ids.append(elem.Id.IntegerValue)

    for loop in loops:
        panel_uid = loop.get("panel_uid")
        device_uids = loop.get("device_uids") or []

        panel_pt = node_point_by_uid.get(panel_uid) if panel_uid else None
        device_pts = [node_point_by_uid[uid] for uid in device_uids if uid in node_point_by_uid]

        if not device_pts:
            continue

        path = ([panel_pt] if panel_pt else []) + device_pts + ([panel_pt] if panel_pt else [])
        if len(path) < 2:
            continue

        for (x1, y1), (x2, y2) in zip(path, path[1:]):
            draw_hop(x1, y1, x2, y2)

    return new_ids
