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

Раскладка ответвлений изоляторов (sync_isolator_satellites)
-------------------------------------------------------------
Отдельно от линий — САМИ устройства ответвления рисуются не в своём
обычном помещении (где им и следовало бы быть по параметру помещения), а
отдельным рядом-"спутником" прямо под изолятором, как у обычного
помещения (тот же шаг между узлами, та же рамка, подпись — реальные
помещения устройств ветви — переиспользуется sot_schematic._place_room_group),
с зазором SATELLITE_GAP_MM от рамки этажа. Так итоговая раскладка
читается как дерево, растущее от кольца: кольцо — обычный ряд по
этажам/помещениям, а каждое ответвление — собственная "ветка" под своим
изолятором. Вызывающий код (кнопка) сам исключает устройства ответвления
из обычной группировки по помещению, иначе они оказались бы на схеме
дважды.

Ветки изоляторов ОДНОГО этажа (у них общий фиксированный отступ от него,
см. SATELLITE_ROW_OFFSET_MM) могли бы наложиться друг на друга, если их
изоляторы физически близко по X — раскладываются слева направо в
порядке X изолятора, с тем же зазором SATELLITE_GAP_MM между соседними
ветками, что и по вертикали (тот же x_cursor-приём, что у обычных
помещений в sync_rooms_in_level).

Если ВСЕ устройства ветви — в том же помещении, что и сам изолятор
(сравнивается с уже размещённым узлом изолятора по параметру помещения,
а не по ключу раскладки), отдельная рамка/подпись не рисуется вовсе —
ветка просто ложится в тот же ряд, ниже на same_room_branch_offset_mm
(параметр sync_isolator_satellites — по умолчанию
SAME_ROOM_BRANCH_OFFSET_MM_DEFAULT, настраивается в параметрах СПС), с
зазором SAME_ROOM_BRANCH_GAP_MM между изолятором и первым устройством
ветки (см. _place_inline_branch_devices). Если хотя бы одно устройство
ветви из ДРУГОГО помещения (или у изолятора/устройств помещение не
определено) — рамка рисуется как раньше.

Место под ряд-спутник должно быть зарезервировано ЗАРАНЕЕ, при вызове
sot_schematic.sync_levels — параметром extra_bottom_mm, значением
SATELLITE_EXTRA_BOTTOM_MM (см. подробности отступов в комментариях к
константам ниже; учитывает оба случая — и рамку, и ветку в том же
помещении, у неё отступ больше); без этого рамка этажа наложится на
ряд-спутник/ветку.

ИЗВЕСТНОЕ ОГРАНИЧЕНИЕ: при переносе помещений по строкам
(max_row_width_mm у sync_levels) нечётные строки отзеркалены — подпись
помещения и марка узла у НИХ уже сами уходят ВНИЗ (см. докстринг
sot_schematic.sync_rooms_in_level/_place_room_group, flipped). Ряд-
спутник/ветка изолятора здесь всегда уходит вниз тоже, независимо от
flipped его строки — если изолятор попадёт на нечётную (отзеркаленную)
строку, его ветка теоретически может визуально столкнуться с уже
отзеркаленной подписью/маркой этой же строки. Не обработано (нет
доступа к flipped там, где это нужно, без более широкой правки) —
проверить на реальной схеме с переносом строк и изоляторами на
нечётных строках, если увидите наложение — сообщите.
"""

from Autodesk.Revit.DB import XYZ

from lowlife.params import get_string_param, set_param_any
from lowlife.sot_schematic import (
    draw_segment, delete_elements, MM_TO_FT, STEP_MM, BOTTOM_LINE_MM, HEADER_TOP_LINE_MM,
    LEVEL_SEPARATOR_OFFSET_MM, place_node_annotation, _place_room_group
)

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

# Зазор между нижней линией рамки помещения изолятора (BOTTOM_LINE_MM) и
# верхней линией рамки ряда-спутника — прямо между двумя рамками, как
# GROUP_GAP_MM между соседними помещениями в одном ряду, только по
# вертикали.
SATELLITE_GAP_MM = 5.0

# На сколько ниже базовой линии этажа рисуется ряд-спутник ответвления:
# нижняя граница рамки помещения (BOTTOM_LINE_MM), минус зазор
# (SATELLITE_GAP_MM), минус верхняя граница собственной рамки спутника
# (HEADER_TOP_LINE_MM — та же, что у обычного помещения).
SATELLITE_ROW_OFFSET_MM = BOTTOM_LINE_MM - SATELLITE_GAP_MM - HEADER_TOP_LINE_MM

# Нижняя граница рамки ряда-спутника (та же BOTTOM_LINE_MM, что и у
# обычного помещения, но уже от его собственной базовой линии).
_SATELLITE_ROW_BOTTOM_MM = SATELLITE_ROW_OFFSET_MM + BOTTOM_LINE_MM

# Обычная (extra_bottom_mm=0) нижняя граница рамки этажа — см.
# sot_schematic._draw_level_frame: base_bottom_y = current_level_y +
# BOTTOM_LINE_MM - LEVEL_SEPARATOR_OFFSET_MM.
_LEVEL_BASE_BOTTOM_MM = BOTTOM_LINE_MM - LEVEL_SEPARATOR_OFFSET_MM

# Ветка изолятора, все устройства которой в том же помещении, что и сам
# изолятор — без отдельной рамки, просто ниже на эту величину (мм) от
# ряда изолятора, в пределах того же помещения на схеме. Значение по
# умолчанию, если вызывающий код (кнопка) не передал своё, настраиваемое
# в параметрах СПС ("same_room_branch_offset_mm") — было 120мм
# изначально, оказалось на практике слишком далеко от изолятора для
# "той же комнаты", уменьшено.
SAME_ROOM_BRANCH_OFFSET_MM_DEFAULT = 40.0

# Зазор между изолятором и первым устройством такой ветки по X — тот же
# шаг, что и между обычными узлами (STEP_MM), чтобы связывающая линия от
# изолятора не начиналась вплотную под ним.
SAME_ROOM_BRANCH_GAP_MM = STEP_MM

# Запас под сам схемный символ узла ниже точки вставки (высота УГО),
# чтобы нижняя граница рамки этажа не резала узлы такой ветки.
_INLINE_BOTTOM_MARGIN_MM = 15.0


def satellite_extra_bottom_mm(same_room_branch_offset_mm=None):
    """
    extra_bottom_mm для sot_schematic.sync_levels — растягивает рамку
    КАЖДОГО этажа вниз ровно настолько, чтобы под ней помещался самый
    глубокий из двух случаев (обычная рамка ряда-спутника ИЛИ ветка в
    том же помещении, с отступом same_room_branch_offset_mm — по
    умолчанию SAME_ROOM_BRANCH_OFFSET_MM_DEFAULT, если не задан/некорректен,
    как и у sync_isolator_satellites), плюс небольшой запас 4мм — иначе
    разделительная линия этажа наложится на них. Общий на все этажи (см.
    докстринг sync_levels) — при построении СПС передаётся всегда, даже
    для этажей без ответвлений, чтобы при появлении нового изолятора (или
    смене этого отступа в настройках) не пришлось всё перестраивать
    заново из-за смены этого параметра.
    """
    offset = (
        same_room_branch_offset_mm
        if same_room_branch_offset_mm and same_room_branch_offset_mm > 0
        else SAME_ROOM_BRANCH_OFFSET_MM_DEFAULT
    )
    inline_bottom_mm = -(offset + _INLINE_BOTTOM_MARGIN_MM)

    return max(
        (_LEVEL_BASE_BOTTOM_MM - _SATELLITE_ROW_BOTTOM_MM) + 4.0,
        (_LEVEL_BASE_BOTTOM_MM - inline_bottom_mm) + 4.0
    )


# extra_bottom_mm по умолчанию (SAME_ROOM_BRANCH_OFFSET_MM_DEFAULT) — для
# вызывающего кода, которому не нужно настраивать отступ отдельно.
SATELLITE_EXTRA_BOTTOM_MM = satellite_extra_bottom_mm()


def node_placement_from_state(state):
    """
    {UniqueId реального устройства: (x, y, level_key, room_key)} —
    фактические координаты И помещение/этаж уже размещённых на схеме
    узлов (и устройств, и панелей — панель это тоже узел категории
    "Электрооборудование", если для неё выбран схемный тип в настройках),
    по итоговому state sot_schematic.sync_levels.

    y — Y СОБСТВЕННОЙ строки помещения (room_record["y"]), НЕ этажа
    целиком (level_record["y"]): при переносе помещений по строкам
    (max_row_width_mm у sync_levels) у разных помещений одного этажа
    разный Y — см. докстринг sot_schematic._iter_state_devices, тот же
    приём. У помещений без собственного "y" в записи (сохранены до
    появления переноса по строкам) — Y этажа, как раньше.
    """
    result = {}
    for level_key, level_record in state.get("levels", {}).items():
        level_y = level_record.get("y", 0.0)
        for room_key, room_record in level_record.get("rooms", {}).items():
            row_y = room_record.get("y", level_y)
            for uid, dev in room_record.get("devices", {}).items():
                result[uid] = (dev.get("x", 0.0), row_y, level_key, room_key)
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


def _place_inline_branch_devices(doc, view, start_x, y, valid_devices, room_param_name,
                                  address_param_name, device_uid_param_name, annotation_symbol,
                                  label_offset_mm):
    """
    Устройства ветви БЕЗ рамки/подписи — просто узлы + марки в ряд, тем
    же шагом STEP_MM, что и обычные помещения, начиная с start_x на
    высоте y (см. докстринг модуля, SAME_ROOM_BRANCH_OFFSET_MM). Для
    веток изолятора, чьи устройства в том же помещении, что и сам
    изолятор — своя рамка не нужна, ветка просто читается как
    продолжение того же помещения на схеме, только ниже.

    Возвращает список id новых элементов (узлы + марки) — сюда же
    относится: параметры на схемный экземпляр (адрес/помещение/UID)
    пишутся точно так же, как в sot_schematic._place_room_group.
    """
    step = STEP_MM * MM_TO_FT
    x = start_x
    new_ids = []

    for device, symbol in valid_devices:
        if not symbol.IsActive:
            symbol.Activate()
            doc.Regenerate()

        node_instance = doc.Create.NewFamilyInstance(XYZ(x, y, 0.0), symbol, view)

        if node_instance is not None:
            address_value = get_string_param(device, address_param_name)
            if address_value:
                set_param_any(node_instance, address_param_name, address_value)

            room_value = get_string_param(device, room_param_name)
            if room_value:
                set_param_any(node_instance, room_param_name, room_value)

            if device_uid_param_name:
                set_param_any(node_instance, device_uid_param_name, device.UniqueId)

            tag = place_node_annotation(doc, view, node_instance, annotation_symbol, x, y, label_offset_mm)

            new_ids.append(node_instance.Id.IntegerValue)
            if tag is not None:
                new_ids.append(tag.Id.IntegerValue)

        x += step

    return new_ids


def sync_isolator_satellites(doc, view, old_satellite_ids, isolator_branches, node_placement_by_uid,
                              category_symbols, category_for_device, room_param_name,
                              address_param_name, device_uid_param_name, annotation_symbol,
                              label_offset_mm, timing=None, same_room_branch_offset_mm=None):
    """
    Рисует ответвления изоляторов отдельным рядом-спутником прямо под
    изолятором (см. докстринг модуля) — полностью перерисовывается каждый
    запуск (без инкрементальной синхронизации, как у основной раскладки
    помещений): состав ответвлений обычно небольшая часть от общего числа
    устройств, полный перебор здесь дешёвый, а отдельный инкрементальный
    код рисковал бы разъехаться с основной раскладкой при её собственных
    сдвигах (сдвиг/пересчёт помещений сейчас не знает о спутниках).

    isolator_branches — {UniqueId изолятора: [device_el, ...]} — реальные
    элементы Revit его ветви (не UniqueId — нужны, чтобы создавать по ним
    новые схемные экземпляры), уже в нужном порядке слева направо.

    node_placement_by_uid — {UniqueId: (x, y, level_key, room_key)}
    положения уже размещённых на схеме узлов (см. node_placement_from_state)
    — используется только для координат самого изолятора; сами устройства
    ветви в этом словаре отсутствуют (вызывающий код исключает их из
    обычной группировки по помещению перед sync_levels).

    same_room_branch_offset_mm — на сколько мм ниже ряда изолятора
    ставится ветка "в том же помещении" (см. докстринг модуля); если не
    задан/не больше нуля — SAME_ROOM_BRANCH_OFFSET_MM_DEFAULT. Должно
    совпадать со значением, переданным в satellite_extra_bottom_mm() при
    вызове sync_levels — иначе резерва под рамкой этажа может не
    хватить/останется зря пустым.

    Остальные параметры — как у sot_schematic.sync_rooms_in_level/
    _place_room_group (категории, схемные символы, параметры записи).
    timing — см. sot_schematic._place_room_group/sync_levels.

    Возвращает новый список id элементов ответвлений (для state).
    """
    delete_elements(doc, old_satellite_ids)

    new_ids = []
    row_offset_ft = SATELLITE_ROW_OFFSET_MM * MM_TO_FT
    gap_ft = SATELLITE_GAP_MM * MM_TO_FT
    inline_offset_mm = (
        same_room_branch_offset_mm
        if same_room_branch_offset_mm and same_room_branch_offset_mm > 0
        else SAME_ROOM_BRANCH_OFFSET_MM_DEFAULT
    )
    inline_offset_ft = inline_offset_mm * MM_TO_FT
    inline_gap_ft = SAME_ROOM_BRANCH_GAP_MM * MM_TO_FT

    # Группируем изоляторы по этажу — и рамка ряда-спутника, и ветка "в
    # том же помещении" сидят на одном и том же фиксированном отступе от
    # своего этажа (у каждой — свой отступ, но общий для ВСЕХ изоляторов
    # этажа), поэтому столкнуться (наложиться) по X могут только ветки
    # ОДНОГО этажа И одного типа (обе рамочные либо обе инлайн), если их
    # изоляторы физически близко. Внутри этажа раскладываем оба вида
    # слева направо в порядке X изолятора, каждый вид — со своим
    # курсором (тот же x_cursor-приём, что у обычных помещений в
    # sync_rooms_in_level), сдвигая начало следующей ветки за правый
    # край предыдущей ТОГО ЖЕ вида (+ зазор), если иначе она бы на неё
    # наехала.
    by_level = {}
    for isolator_uid, devices in isolator_branches.items():
        if not devices:
            continue
        placement = node_placement_by_uid.get(isolator_uid)
        if placement is None:
            continue
        isolator_x, isolator_y, level_key, isolator_room_key = placement
        by_level.setdefault(level_key, []).append((isolator_x, isolator_y, isolator_room_key, devices))

    for level_key, items in by_level.items():
        items.sort(key=lambda item: item[0])
        framed_right_edge = None
        inline_right_edge = None

        for isolator_x, isolator_y, isolator_room_key, devices in items:
            valid_devices = []
            for device in devices:
                category = category_for_device(device)
                symbol = category_symbols.get(category) if category else None
                if symbol is not None:
                    valid_devices.append((device, symbol))

            if not valid_devices:
                continue

            # "В том же помещении" — у изолятора есть реальное (не
            # "(пусто)") помещение, и у ВСЕХ устройств ветви оно
            # совпадает с ним (сравниваем со значением параметра
            # напрямую, а не с ключом раскладки — надёжнее, если
            # где-то попадётся "(пусто)" как реальный текст).
            same_room = bool(isolator_room_key) and isolator_room_key != u"(пусто)" and all(
                (get_string_param(device, room_param_name) or u"").strip() == isolator_room_key
                for device, _symbol in valid_devices
            )

            if same_room:
                start_x = isolator_x + inline_gap_ft
                if inline_right_edge is not None and start_x < inline_right_edge + gap_ft:
                    start_x = inline_right_edge + gap_ft

                inline_y = isolator_y - inline_offset_ft

                ids = _place_inline_branch_devices(
                    doc, view, start_x, inline_y, valid_devices, room_param_name,
                    address_param_name, device_uid_param_name, annotation_symbol, label_offset_mm
                )
                new_ids.extend(ids)

                last_x = start_x + max(0, len(valid_devices) - 1) * STEP_MM * MM_TO_FT
                inline_right_edge = last_x
                continue

            start_x = isolator_x
            if framed_right_edge is not None and start_x < framed_right_edge + gap_ft:
                start_x = framed_right_edge + gap_ft

            satellite_y = isolator_y + row_offset_ft

            # Подпись ветки — реальные помещения её устройств (как у
            # обычных помещений), а не заглушка: если все устройства из
            # одного помещения — просто его имя, если из разных — через
            # "; ". Пусто (нет ни у одного) — тогда уже "↳", просто как
            # пометка "это ветка".
            room_names = []
            for device, _symbol in valid_devices:
                room_value = get_string_param(device, room_param_name)
                if room_value and room_value.strip() and room_value.strip() not in room_names:
                    room_names.append(room_value.strip())
            room_label = u"; ".join(room_names) if room_names else u"↳"

            # Переиспользуем ту же функцию, что рисует обычные помещения —
            # тот же шаг между узлами, та же рамка, та же логика марок,
            # только на своей строке (satellite_y вместо этажной
            # current_level_y).
            room_record, _report_rows = _place_room_group(
                doc, view, start_x, room_label, valid_devices, room_param_name,
                address_param_name, device_uid_param_name, annotation_symbol,
                label_offset_mm, satellite_y, timing=timing
            )

            framed_right_edge = room_record.get("x_right", start_x)

            new_ids.extend(room_record.get("line_ids", []))
            if room_record.get("text_id") is not None:
                new_ids.append(room_record["text_id"])
            for dev in room_record.get("devices", {}).values():
                if dev.get("instance_id") is not None:
                    new_ids.append(dev["instance_id"])
                if dev.get("tag_id") is not None:
                    new_ids.append(dev["tag_id"])

    return new_ids
