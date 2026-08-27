# -*- coding: utf-8 -*-
"""
Логика кнопки BuildScsSchematic ("Структурная схема СКС").

Раскладка устройств по этажам/помещениям, сами схемные семейства и марки,
инкрементальное обновление вида между запусками — всё это уже есть в
lib/lowlife/sot_schematic.py (написано для СОТ, но ничем не привязано к
дисциплине: category_symbols/category_for_device — просто параметры) и
переиспользуется здесь напрямую, без копирования: sync_levels,
sync_rooms_in_level, draw_segment, delete_elements, _iter_state_devices,
_node_bottom_y и т.д. Уровни (sot_levels.py) и хранение раскладки
(sot_layout_state.py) — тоже полностью общие модули, тоже импортируются
как есть.

Единственное, чего нет у СОТ и что нужно СКС — несколько НЕЗАВИСИМЫХ шин
вместо одной общей: на этаже может быть несколько панелей (шкафов/патч-
панелей), и каждая собирает линиями только СВОИ устройства, со своим
стояком. sync_cable_connections (СОТ) рисует ровно одну такую шину на всю
схему — sync_panel_buses ниже делает то же самое в цикле, по одной шине
на панель, с разным X стояка, чтобы они не накладывались друг на друга.
"""

# lowlife.sot_schematic импортирует Autodesk.Revit.DB на уровне модуля —
# импортируем его функции ЛЕНИВО, внутри sync_panel_buses, а не здесь
# наверху (тот же приём, что и в scs.py:get_workset_name), чтобы
# panel_riser_x (чистая функция, без Revit API) можно было тестировать
# вне Revit — см. tests/test_scs_schematic.py.
MM_TO_FT = 1.0 / 304.8

# Расстояние между стояками разных панелей (в плане, по X) — чтобы стояки
# нескольких панелей на одной схеме не накладывались друг на друга и не
# сливались визуально. Первая панель (index=0) получает стояк на этом же
# расстоянии левее рамок помещений — так же, как единственный стояк у СОТ.
RISER_SPACING_MM = 300.0

# Насколько ниже узлов проходит горизонтальный коллектор панели —
# то же значение и тот же смысл, что CABLE_DROP_OFFSET_MM у СОТ.
BUS_DROP_OFFSET_MM = 15.0


def panel_riser_x(panel_index):
    """
    X стояка панели с данным порядковым номером (0, 1, 2...) — левее рамок
    помещений, панели расставлены по возрастанию номера слева направо от
    рамок (первая — ближе всего). Чистая функция, без Revit API — можно
    проверить тестами отдельно от геометрии сборки шины.
    """
    return -(panel_index + 1) * RISER_SPACING_MM * MM_TO_FT


def sync_panel_buses(doc, view, new_state, old_bus_line_ids_by_panel, panels_order,
                      panel_device_uids, drop_offset_mm=BUS_DROP_OFFSET_MM):
    """
    Рисует по одной независимой шине (коллектор на каждый этаж + свой
    отвод от каждого устройства + один стояк через все этажи) на каждую
    панель — обобщение sot_schematic.sync_cable_connections на N панелей
    вместо одного шкафа на всю схему.

    panels_order — [panel_uid, ...], уже в нужном порядке отрисовки
    (например по имени панели) — определяет X стояка каждой панели
    (panel_riser_x(index)), стабильный между запусками, пока порядок
    панелей не меняется.
    panel_device_uids — {panel_uid: set([device_uid, ...])} — устройства
    этой панели (её собственный uid тоже должен быть в своём множестве,
    чтобы шина дотянулась до самого узла панели на схеме).
    old_bus_line_ids_by_panel — {panel_uid: [line_id, ...]} из состояния
    предыдущего запуска (для панелей, которых в этот раз нет — всё равно
    будут удалены).

    Как и у СОТ, эти линии не диффятся — полностью удаляются и рисуются
    заново на каждом запуске (они целиком выводятся из уже посчитанных
    sync_levels позиций узлов, диффить их незачем — см. docstring
    sot_schematic.sync_cable_connections).

    Возвращает {panel_uid: [line_id, ...]} для сохранения в state.
    """
    from lowlife.sot_schematic import draw_segment, delete_elements, _iter_state_devices, _node_bottom_y

    all_old_ids = []
    for ids in old_bus_line_ids_by_panel.values():
        all_old_ids.extend(ids)
    delete_elements(doc, all_old_ids)

    all_devices = list(_iter_state_devices(new_state))
    device_by_uid = dict((uid, (x, y, instance_id)) for uid, x, y, instance_id in all_devices)

    drop_offset = drop_offset_mm * MM_TO_FT
    result = {}

    for index, panel_uid in enumerate(panels_order):
        member_uids = panel_device_uids.get(panel_uid) or set()
        members = [
            (uid, x, y, instance_id)
            for uid, (x, y, instance_id) in device_by_uid.items()
            if uid in member_uids
        ]

        if not members:
            result[panel_uid] = []
            continue

        riser_x = panel_riser_x(index)

        by_level_y = {}
        for uid, x, y, instance_id in members:
            by_level_y.setdefault(y, []).append((x, instance_id))

        new_ids = []
        collector_ys = []

        for level_y, x_instance_list in by_level_y.items():
            collector_y = level_y - drop_offset
            collector_ys.append(collector_y)

            xs = [x for x, _iid in x_instance_list]
            x_min = min(xs + [riser_x])
            x_max = max(xs + [riser_x])

            elem = draw_segment(doc, view, x_min, collector_y, x_max, collector_y)
            if elem is not None:
                new_ids.append(elem.Id.IntegerValue)

            for x, instance_id in x_instance_list:
                drop_top_y = _node_bottom_y(doc, view, instance_id, level_y)
                elem = draw_segment(doc, view, x, drop_top_y, x, collector_y)
                if elem is not None:
                    new_ids.append(elem.Id.IntegerValue)

        if collector_ys:
            elem = draw_segment(doc, view, riser_x, min(collector_ys), riser_x, max(collector_ys))
            if elem is not None:
                new_ids.append(elem.Id.IntegerValue)

        result[panel_uid] = new_ids

    return result
