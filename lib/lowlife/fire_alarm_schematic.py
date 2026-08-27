# -*- coding: utf-8 -*-
"""
Кольцевой шлейф СПС на структурной схеме.

В отличие от sot_schematic.sync_cable_connections (общий шкаф СОТ/СПС —
топология "шина", коллектор ниже узлов + один стояк): здесь линия идёт
ЧЕРЕЗ фактические точки узлов кольца на этаже (на их высоте, без отхода
вниз) — один горизонтальный отрезок на этаж, от стояка (если кольцо
затрагивает больше одного этажа) до крайнего узла кольца на этом этаже.
Переход между этажами — через один общий стояк на кольцо (слева от рамок
этажей, как и в sync_cable_connections). Панель — такой же узел на
коллекторе своего этажа: линия до стояка от неё идёт горизонтально по
этому этажу, а не отдельным наклонным отрезком.

Поскольку кольцевой интерфейс идёт "туда" и "обратно" по одному и тому же
физическому маршруту, вся структура (коллекторы всех этажей + стояк)
рисуется дважды — второй проход сдвинут на LOOP_LINE_GAP_MM (3 мм: по Y у
горизонтальных коллекторов, по X у стояка), чтобы "туда"/"обратно"
читались как два отдельных провода, а не одна линия.

Координаты панели/устройств берутся из уже размещённых на схеме
экземпляров схемных семейств — эта функция вызывается ПОСЛЕ
sot_schematic.sync_levels, когда все узлы уже стоят на месте (см.
node_points_from_state).

Изоляторы (ответвители) и их ответвления
-----------------------------------------
Изолятор стоит инлайн на основном кольце (магистраль идёт ЧЕРЕЗ него, как
через обычное устройство), но устройства, подключённые К НЕМУ (его
собственная ветвь, которая назад к магистрали не возвращается — см.
lowlife.fire_alarm_loops), исключаются из основной последовательности и
рисуются отдельной ломаной от изолятора. Состав ветви берётся не из
адреса/геометрии, а из фактической электрической цепи "изолятор ->
устройства" в модели (см. lowlife.fire_alarm_circuits.isolator_branch_device_map)
— это единственный надёжный источник, см. докстринг fire_alarm_loops о
том, почему по одному адресу магистраль от ветви не отличить.

Чтобы ответвление визуально читалось как ответвление, а не продолжение
магистрали, от изолятора линия сначала идёт коротким изломом по Y
(BRANCH_Y_OFFSET_MM) и только потом — к первому устройству ветви и далее
по её устройствам (прямыми отрезками, без возврата).
"""

from lowlife.sot_schematic import draw_segment, delete_elements, MM_TO_FT

# Зазор между линиями кольца "туда"/"обратно" (см. докстринг модуля).
LOOP_LINE_GAP_MM = 3.0

# X первого стояка кольца — левее рамок этажей (третья/крайняя левая
# линия рамки уровня в sot_schematic сидит на -35мм от group_left=0, см.
# LEVEL_LINE_1/2/3_OFFSET_MM) — с запасом, чтобы не накладываться на неё.
LOOP_RISER_BASE_OFFSET_MM = 50.0

# Шаг между стояками разных колец, чтобы не накладывались друг на друга.
LOOP_RISER_SPACING_MM = 30.0

# Излом по Y от изолятора перед ответвлением — визуально отличает ветвь
# от прямого продолжения магистрали (см. _draw_branch).
BRANCH_Y_OFFSET_MM = 8.0


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


def sync_loop_connections(doc, view, old_loop_line_ids, loops, node_point_by_uid):
    """
    Перерисовывает кольцевые шлейфы заново (как и sync_cable_connections —
    эти линии не редактируются вручную, поэтому диффинг не нужен: старые
    (old_loop_line_ids — state["loop_line_ids"] из прошлого запуска)
    удаляются, новые рисуются по актуальным позициям узлов).

    loops — список колец: [{"panel_uid": uid_или_None, "device_uids":
    [uid, ...], "branches": {isolator_uid: [uid, ...]}}, ...].
    device_uids — основная магистраль (порядок не важен для отрисовки —
    коллектор проходит через все точки этажа разом), БЕЗ устройств,
    ушедших на ветви (те перечислены в "branches"). "branches" —
    необязательный ключ; каждая запись — {UniqueId изолятора: [UniqueId
    устройств его ветви, в порядке обхода]} (см.
    fire_alarm_circuits.isolator_branch_device_map) — изолятор при этом
    сам остаётся в device_uids (магистраль идёт через него).

    node_point_by_uid — {UniqueId: (x, y)} фактических координат узлов на
    схеме (см. node_points_from_state).

    Возвращает новый список id линий (для state).
    """
    delete_elements(doc, old_loop_line_ids)

    gap_ft = LOOP_LINE_GAP_MM * MM_TO_FT
    branch_offset_ft = BRANCH_Y_OFFSET_MM * MM_TO_FT
    new_ids = []

    def draw_both_passes(x1, y1, x2, y2, dx_gap, dy_gap):
        """Отрезок "туда" как есть, "обратно" — сдвинутый на (dx_gap, dy_gap)."""
        for offset in (0.0, 1.0):
            elem = draw_segment(
                doc, view,
                x1 + dx_gap * offset, y1 + dy_gap * offset,
                x2 + dx_gap * offset, y2 + dy_gap * offset
            )
            if elem is not None:
                new_ids.append(elem.Id.IntegerValue)

    def draw_branch(isolator_pt, device_pts):
        """Излом по Y от изолятора, затем по устройствам ветви по прямой (без возврата)."""
        if isolator_pt is None or not device_pts:
            return

        ix, iy = isolator_pt
        stub_y = iy + branch_offset_ft

        path = [(ix, iy), (ix, stub_y)] + device_pts
        for (x1, y1), (x2, y2) in zip(path, path[1:]):
            elem = draw_segment(doc, view, x1, y1, x2, y2)
            if elem is not None:
                new_ids.append(elem.Id.IntegerValue)

    riser_index = 0

    for loop in loops:
        panel_uid = loop.get("panel_uid")
        device_uids = loop.get("device_uids") or []

        all_uids = ([panel_uid] if panel_uid else []) + list(device_uids)

        by_level_y = {}
        for uid in all_uids:
            pt = node_point_by_uid.get(uid)
            if pt is None:
                continue
            by_level_y.setdefault(pt[1], []).append(pt[0])

        if by_level_y:
            multi_floor = len(by_level_y) > 1
            riser_x = None

            if multi_floor:
                riser_x = -(LOOP_RISER_BASE_OFFSET_MM + riser_index * LOOP_RISER_SPACING_MM) * MM_TO_FT
                riser_index += 1

            for y, xs in by_level_y.items():
                x_min = min(xs)
                x_max = max(xs)
                if riser_x is not None:
                    x_min = min(x_min, riser_x)
                    x_max = max(x_max, riser_x)
                # Коллектор этажа — на высоте узлов (через них), без отхода вниз.
                draw_both_passes(x_min, y, x_max, y, 0.0, gap_ft)

            if riser_x is not None:
                ys = list(by_level_y.keys())
                draw_both_passes(riser_x, min(ys), riser_x, max(ys), gap_ft, 0.0)

        for isolator_uid, branch_device_uids in (loop.get("branches") or {}).items():
            isolator_pt = node_point_by_uid.get(isolator_uid)
            branch_pts = [node_point_by_uid[uid] for uid in branch_device_uids if uid in node_point_by_uid]
            draw_branch(isolator_pt, branch_pts)

    return new_ids
