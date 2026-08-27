# -*- coding: utf-8 -*-
"""
Кольцевой шлейф СПС на структурной схеме.

Внутри одного помещения — прямая линия через фактические точки узлов
этого кольца в этом помещении (на их высоте, без отхода вниз). Переход
в ЛЮБОЕ другое помещение — хоть соседнее, хоть на другом этаже — только
через один общий стояк на кольцо (слева от рамок этажей), никогда
напрямую между помещениями: иначе между ними на схеме почти всегда
оказываются чужие рамки/помещения (раскладка идёт по номеру помещения,
не по шлейфу), и прямая линия резала бы их насквозь (см. sync_cable_connections
— тот же приём для одного общего шкафа СОТ/СПС, но там достаточно одного
коллектора без деления по помещениям).

Раз связи "помещение -> стояк" всё равно неизбежно нужно как-то миновать
чужие рамки, которые могут стоять между этим помещением и стояком (тот
всегда слева от group_left=0, то есть левее ЛЮБОГО помещения в ряду
этажа) — этот короткий участок уходит в свободный зазор под рамкой
(LOOP_ROOM_DROP_OFFSET_MM ниже узлов, между нижней линией рамки
помещения и разделителем этажей — то же место, что использует
sync_cable_connections), а не идёт по прямой на высоте узлов.

Поскольку кольцевой интерфейс идёт "туда" и "обратно" по одному и тому
же физическому маршруту, вся структура (линии внутри помещений, спуски к
стояку и сам стояк) рисуется дважды — второй проход сдвинут на
LOOP_LINE_GAP_MM (3 мм), чтобы "туда"/"обратно" читались как два
отдельных провода, а не одна линия.

Координаты и помещение/этаж каждого узла берутся из уже размещённых на
схеме экземпляров схемных семейств — эта функция вызывается ПОСЛЕ
sot_schematic.sync_levels, когда все узлы уже стоят на месте (см.
node_placement_from_state).

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
по её устройствам (прямыми отрезками, без возврата). Ответвления обычно
локальные (в пределах того же помещения, что и изолятор), поэтому для
них правило "только через стояк" не применяется.
"""

from lowlife.sot_schematic import draw_segment, delete_elements, MM_TO_FT

# Зазор между линиями кольца "туда"/"обратно" (см. докстринг модуля).
LOOP_LINE_GAP_MM = 3.0

# Насколько ниже узлов проходит участок "помещение -> стояк" — тот же
# свободный зазор (между нижней линией рамки помещения и разделителем
# этажей), что использует sync_cable_connections, но отдельная константа
# — обе линии на одной схеме не пересекаются одновременно с одним и тем
# же view, но должны остаться независимо настраиваемыми.
LOOP_ROOM_DROP_OFFSET_MM = 15.0

# X первого стояка кольца — левее рамок этажей (третья/крайняя левая
# линия рамки уровня в sot_schematic сидит на -35мм от group_left=0, см.
# LEVEL_LINE_1/2/3_OFFSET_MM) — с запасом, чтобы не накладываться на неё.
LOOP_RISER_BASE_OFFSET_MM = 50.0

# Шаг между стояками разных колец, чтобы не накладывались друг на друга.
LOOP_RISER_SPACING_MM = 30.0

# Излом по Y от изолятора перед ответвлением — визуально отличает ветвь
# от прямого продолжения магистрали (см. _draw_branch).
BRANCH_Y_OFFSET_MM = 8.0


def node_placement_from_state(state):
    """
    {UniqueId реального устройства: (x, y, level_key, room_key)} —
    фактические координаты И помещение/этаж уже размещённых на схеме
    узлов (и устройств, и панелей — панель это тоже узел категории
    "Электрооборудование", если для неё выбран схемный тип в настройках),
    по итоговому state sot_schematic.sync_levels.
    """
    result = {}
    for level_key, level_record in state.get("levels", {}).items():
        y = level_record.get("y", 0.0)
        for room_key, room_record in level_record.get("rooms", {}).items():
            for uid, dev in room_record.get("devices", {}).items():
                result[uid] = (dev.get("x", 0.0), y, level_key, room_key)
    return result


def sync_loop_connections(doc, view, old_loop_line_ids, loops, node_placement_by_uid):
    """
    Перерисовывает кольцевые шлейфы заново (как и sync_cable_connections —
    эти линии не редактируются вручную, поэтому диффинг не нужен: старые
    (old_loop_line_ids — state["loop_line_ids"] из прошлого запуска)
    удаляются, новые рисуются по актуальным позициям узлов).

    loops — список колец: [{"panel_uid": uid_или_None, "device_uids":
    [uid, ...], "branches": {isolator_uid: [uid, ...]}}, ...].
    device_uids — основная магистраль (порядок не важен для отрисовки —
    внутри помещения линия проходит через все точки разом), БЕЗ устройств,
    ушедших на ветви (те перечислены в "branches"). "branches" —
    необязательный ключ; каждая запись — {UniqueId изолятора: [UniqueId
    устройств его ветви, в порядке обхода]} (см.
    fire_alarm_circuits.isolator_branch_device_map) — изолятор при этом
    сам остаётся в device_uids (магистраль идёт через него).

    node_placement_by_uid — {UniqueId: (x, y, level_key, room_key)}
    фактического положения узлов на схеме (см. node_placement_from_state).

    Возвращает новый список id линий (для state).
    """
    delete_elements(doc, old_loop_line_ids)

    gap_ft = LOOP_LINE_GAP_MM * MM_TO_FT
    drop_offset_ft = LOOP_ROOM_DROP_OFFSET_MM * MM_TO_FT
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

        # Группировка по (этаж, помещение) — связь между разными группами
        # идёт ТОЛЬКО через стояк, см. докстринг модуля.
        by_room = {}
        for uid in all_uids:
            placement = node_placement_by_uid.get(uid)
            if placement is None:
                continue
            x, y, level_key, room_key = placement
            by_room.setdefault((level_key, room_key), []).append((x, y))

        if by_room:
            multi_room = len(by_room) > 1
            riser_x = None
            riser_join_ys = []

            if multi_room:
                riser_x = -(LOOP_RISER_BASE_OFFSET_MM + riser_index * LOOP_RISER_SPACING_MM) * MM_TO_FT
                riser_index += 1

            for points in by_room.values():
                y = points[0][1]
                xs = [p[0] for p in points]
                x_min, x_max = min(xs), max(xs)

                # Внутри помещения — прямая линия через все точки разом
                # (без отхода вниз), только в пределах САМОГО этого
                # помещения — наружу за его пределы линия не выходит.
                if x_max > x_min:
                    draw_both_passes(x_min, y, x_max, y, 0.0, gap_ft)

                if riser_x is not None:
                    # Спуск к стояку — от ближайшего к стояку узла этого
                    # помещения, коротким участком в свободном зазоре под
                    # рамкой (а не по прямой на высоте узлов — иначе резало
                    # бы рамки всех помещений, что физически окажутся
                    # между этим помещением и стояком).
                    room_anchor_x = x_min
                    drop_y = y - drop_offset_ft
                    riser_join_ys.append(drop_y)

                    draw_both_passes(room_anchor_x, y, room_anchor_x, drop_y, gap_ft, 0.0)
                    draw_both_passes(room_anchor_x, drop_y, riser_x, drop_y, 0.0, gap_ft)

            if riser_x is not None and riser_join_ys:
                draw_both_passes(riser_x, min(riser_join_ys), riser_x, max(riser_join_ys), gap_ft, 0.0)

        for isolator_uid, branch_device_uids in (loop.get("branches") or {}).items():
            isolator_placement = node_placement_by_uid.get(isolator_uid)
            isolator_pt = isolator_placement[:2] if isolator_placement is not None else None
            branch_pts = []
            for uid in branch_device_uids:
                placement = node_placement_by_uid.get(uid)
                if placement is not None:
                    branch_pts.append(placement[:2])
            draw_branch(isolator_pt, branch_pts)

    return new_ids
