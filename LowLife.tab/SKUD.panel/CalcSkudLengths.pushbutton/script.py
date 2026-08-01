# -*- coding: utf-8 -*-
__title__ = "Длины и маркировка"
__doc__ = (
    "Считает длину проводника для каждой цепи контроллер-устройство: по "
    "катетам (с коэффициентом запаса), если устройство рядом с контроллером, "
    "иначе по графу адресованных узлов трассы. Пишет длину в трубе/лотке "
    "раздельно, способ прокладки, марку устройств и список цепей на узлах "
    "маршрута."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms

from lowlife.geometry import get_point
from lowlife.params import get_string_param, set_param_any
from lowlife.scs import clear_stray_address_params, is_excluded_device, get_workset_name
from lowlife.scs_circuits import (
    norm, clean_text_value, split_multi_value, build_graph, bfs_component,
    find_closest_pair_between_sets, astar_path,
    calc_lengths, balance_round_parts, build_segment_list_text
)
from lowlife.skud import is_controller, is_near_controller, hypotenuse_length_ft
from lowlife import skud_settings
from lowlife.skud_settings import get_settings_silent

doc = revit.doc

FT_TO_M = 0.3048
M_TO_FT = 1.0 / FT_TO_M


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

skud_settings.require(settings, [
    "controller_workset_keyword", "controller_type_keyword", "workset_param_name",
    "circuit_panel_param",
    "route_type_id", "riser_type_id",
    "near_controller_threshold_m", "hypotenuse_coef",
    "horiz_tray_coef", "horiz_pipe_coef", "vertical_coef",
    "install_tray_key", "install_pipe_key", "install_pipe_open_key",
    "wire_length_param", "tray_length_param", "pipe_length_param",
    "route_method_param", "circuit_route_param",
    "route_label_pipe_format", "route_label_tray_format",
    "device_address_param", "device_marking_param", "segment_loads_param"
])

CONTROLLER_WORKSET_KEYWORD = settings["controller_workset_keyword"]
# Рабочий набор узлов трассы СКУД. Типы семейств узлов у СКС и СКУД могут
# быть одни и те же (общий SMNX_Сегмент), поэтому только по типу их не
# различить — разделение идёт по рабочему набору.
NODE_WORKSET_FILTER_KEY = settings.get("workset_filter_key")
CONTROLLER_TYPE_KEYWORD = settings["controller_type_keyword"]
WORKSET_PARAM_NAME = settings["workset_param_name"]
EXCLUDED_DEVICE_KEYWORDS = settings["excluded_device_keywords"]

CIRCUIT_PANEL_PARAM = settings["circuit_panel_param"]

ADDR_PARAM = settings["addr_param_name"]
ADDR_PREV_PARAM = settings["addr_prev_param_name"]
NEAREST_SEGMENT_PARAM = settings["nearest_segment_param"]
CABLE_PARAM_NAME = settings["cable_param_name"]

ROUTE_TYPE_ID = ElementId(int(settings["route_type_id"]))
RISER_TYPE_ID = ElementId(int(settings["riser_type_id"]))

NEAR_THRESHOLD_FT = float(settings["near_controller_threshold_m"]) * M_TO_FT
HYPOTENUSE_COEF = float(settings["hypotenuse_coef"])
HORIZ_TRAY_COEF = float(settings["horiz_tray_coef"])
HORIZ_PIPE_COEF = float(settings["horiz_pipe_coef"])
VERTICAL_COEF = float(settings["vertical_coef"])

INSTALL_TRAY_KEY = settings["install_tray_key"]
INSTALL_PIPE_KEY = settings["install_pipe_key"]
INSTALL_PIPE_OPEN_KEY = settings["install_pipe_open_key"]

WIRE_LENGTH_PARAM = settings["wire_length_param"]
TRAY_LENGTH_PARAM = settings["tray_length_param"]
PIPE_LENGTH_PARAM = settings["pipe_length_param"]
ROUTE_METHOD_PARAM = settings["route_method_param"]
CIRCUIT_ROUTE_PARAM = settings["circuit_route_param"]

ROUTE_LABEL_PIPE = settings["route_label_pipe_format"]
ROUTE_LABEL_TRAY = settings["route_label_tray_format"]

DEVICE_ADDRESS_PARAM = settings["device_address_param"]
DEVICE_MARKING_PARAM = settings["device_marking_param"]
SEGMENT_LOADS_PARAM = settings["segment_loads_param"]


# ------------------------------------------------------------
# ОЧИСТКА "ЧУЖИХ" АДРЕСОВ
# ------------------------------------------------------------
# Очистка ограничена рабочим набором СКУД: параметры адреса общие с СКС
# (SMNX_Сегмент), поэтому без такого ограничения запуск СКУД стирал бы
# адреса узлов СКС, и наоборот.

with revit.Transaction("Clear stray SKUD route addresses"):
    stray_cleared = clear_stray_address_params(
        doc, [ADDR_PARAM, ADDR_PREV_PARAM], set([ROUTE_TYPE_ID, RISER_TYPE_ID]),
        workset_param_name=WORKSET_PARAM_NAME,
        workset_filter_key=NODE_WORKSET_FILTER_KEY
    )


# ------------------------------------------------------------
# СБОР УЗЛОВ ТРАССЫ СКУД (для длинных участков)
# ------------------------------------------------------------

segments = {}
parents_by_id = {}
duplicate_addr_report = []

all_generic = FilteredElementCollector(doc) \
    .OfCategory(BuiltInCategory.OST_GenericModel) \
    .WhereElementIsNotElementType() \
    .ToElements()

foreign_workset_nodes = 0

for e in all_generic:
    if e.GetTypeId() not in (ROUTE_TYPE_ID, RISER_TYPE_ID):
        continue

    # Узлы СКС и СКУД могут быть одного типа семейства и с одинаковыми
    # именами параметров адреса — различает их только рабочий набор.
    # Без этой проверки узел СКС с тем же адресом (F1.3 и там, и там)
    # попал бы в граф СКУД, и путь пошёл бы через чужую трассу.
    if NODE_WORKSET_FILTER_KEY:
        node_workset = get_workset_name(e, WORKSET_PARAM_NAME)
        if not node_workset or NODE_WORKSET_FILTER_KEY.lower() not in node_workset.lower():
            foreign_workset_nodes += 1
            continue

    pt = get_point(e)
    if pt is None:
        continue

    sid = clean_text_value(get_string_param(e, ADDR_PARAM))
    if not sid:
        continue

    if sid in segments:
        duplicate_addr_report.append(
            u"Адрес «{}»: элементы {} и {} — оставлен первый, второй проигнорирован.".format(
                sid, segments[sid]["el"].Id.IntegerValue, e.Id.IntegerValue
            )
        )
        continue

    parents = split_multi_value(get_string_param(e, ADDR_PREV_PARAM))

    segments[sid] = {
        "el": e,
        "pt": pt,
        "install": clean_text_value(get_string_param(e, CABLE_PARAM_NAME))
    }
    parents_by_id[sid] = parents

graph, broken_parent_links = build_graph(segments, parents_by_id) if segments else ({}, [])


# ------------------------------------------------------------
# КОНТРОЛЛЕРЫ И ЦЕПИ
# ------------------------------------------------------------

all_equipment = FilteredElementCollector(doc) \
    .OfCategory(BuiltInCategory.OST_ElectricalEquipment) \
    .WhereElementIsNotElementType() \
    .ToElements()

controllers = [
    e for e in all_equipment
    if is_controller(e, WORKSET_PARAM_NAME, CONTROLLER_WORKSET_KEYWORD, CONTROLLER_TYPE_KEYWORD)
]

if not controllers:
    forms.alert(
        u"Не найдено ни одного контроллера (рабочий набор содержит «{}», "
        u"имя типа содержит «{}»).".format(CONTROLLER_WORKSET_KEYWORD, CONTROLLER_TYPE_KEYWORD),
        exitscript=True
    )

all_circuits = FilteredElementCollector(doc) \
    .OfCategory(BuiltInCategory.OST_ElectricalCircuit) \
    .WhereElementIsNotElementType() \
    .ToElements()

circuits_by_controller_name = {}
for c in all_circuits:
    panel_name = norm(get_string_param(c, CIRCUIT_PANEL_PARAM))
    if panel_name:
        circuits_by_controller_name.setdefault(panel_name, []).append(c)


# ------------------------------------------------------------
# ОСНОВНОЙ ПРОХОД: ДЛИНЫ И МАРКИРОВКА
# ------------------------------------------------------------
# Маркировка идёт здесь же, а не отдельной кнопкой: марка устройства —
# это просто перенос уже известного адреса, а список цепей на узлах
# собирается из пути цепи, который на этом шаге уже посчитан как список
# (отдельной кнопке пришлось бы разбирать его обратно из текста
# "F1.1 -> F1.2" в параметре «Маршрут цепи»).

processed_circuits = 0
near_count = 0
graph_count = 0
no_device = 0
no_path = 0
no_segment = 0
no_path_report = []
no_segment_report = []
devices_marked = 0
segment_info_map = {}

with revit.Transaction("Calc SKUD Lengths And Marking"):

    for controller in controllers:
        controller_name = norm(controller.Name)
        controller_pt = get_point(controller)
        if controller_pt is None:
            continue

        controller_circuits = circuits_by_controller_name.get(controller_name, [])

        for c in controller_circuits:
            try:
                raw_devs = [x for x in c.Elements if x.Id != controller.Id]
            except:
                continue

            normal_devs = [d for d in raw_devs if not is_excluded_device(d, EXCLUDED_DEVICE_KEYWORDS)]

            if not normal_devs:
                no_device += 1
                continue

            dev = normal_devs[0]
            dev_pt = get_point(dev)

            if dev_pt is None:
                no_device += 1
                continue

            processed_circuits += 1

            device_addr = clean_text_value(get_string_param(dev, DEVICE_ADDRESS_PARAM))
            if device_addr and set_param_any(dev, DEVICE_MARKING_PARAM, device_addr):
                devices_marked += 1

            circuit_label = clean_text_value(norm(c.Name)) or u"Circuit {}".format(c.Id.IntegerValue)

            if is_near_controller(controller_pt, dev_pt, NEAR_THRESHOLD_FT):
                near_count += 1

                length_ft = hypotenuse_length_ft(controller_pt, dev_pt) * HYPOTENUSE_COEF
                length_m = length_ft * FT_TO_M

                T, pi = balance_round_parts(length_m, [length_m])

                set_param_any(c, WIRE_LENGTH_PARAM, T)
                set_param_any(c, PIPE_LENGTH_PARAM, pi)
                set_param_any(c, TRAY_LENGTH_PARAM, 0)

                route_parts = []
                if pi > 0 and ROUTE_LABEL_PIPE:
                    route_parts.append(ROUTE_LABEL_PIPE.format(pi))
                set_param_any(c, ROUTE_METHOD_PARAM, u"; ".join(route_parts))
                set_param_any(c, CIRCUIT_ROUTE_PARAM, u"")

            else:
                controller_start = clean_text_value(get_string_param(controller, NEAREST_SEGMENT_PARAM))
                dev_end = clean_text_value(get_string_param(dev, NEAREST_SEGMENT_PARAM))

                if not controller_start or not dev_end:
                    no_segment += 1
                    no_segment_report.append(
                        u"Цепь «{}» (контроллер {}): нет привязки к узлу маршрута "
                        u"{}.".format(
                            norm(c.Name) or c.Id.IntegerValue, controller_name,
                            u"у контроллера" if not controller_start else u"у устройства"
                        )
                    )
                    continue

                if controller_start not in segments or dev_end not in segments:
                    no_segment += 1
                    no_segment_report.append(
                        u"Цепь «{}» (контроллер {}): узел «{}» не найден среди "
                        u"адресованных узлов трассы.".format(
                            norm(c.Name) or c.Id.IntegerValue, controller_name,
                            controller_start if controller_start not in segments else dev_end
                        )
                    )
                    continue

                path = astar_path(segments, graph, controller_start, dev_end)

                if not path:
                    no_path += 1
                    start_component = bfs_component(graph, controller_start)
                    end_component = bfs_component(graph, dev_end)
                    near_a, near_b, gap = find_closest_pair_between_sets(segments, start_component, end_component)

                    no_path_report.append(
                        u"Цепь «{}» (контроллер {}): {} -> {} — путь не найден. "
                        u"Ближайший разрыв: {} <-> {} (зазор {:.2f} м)".format(
                            norm(c.Name) or c.Id.IntegerValue, controller_name,
                            controller_start, dev_end,
                            near_a, near_b,
                            (gap * FT_TO_M) if gap is not None else 0.0
                        )
                    )
                    continue

                graph_count += 1

                horiz_total_m, horiz_tray_m, horiz_pipe_m, horiz_pipe_open_m = calc_lengths(
                    segments, path, INSTALL_TRAY_KEY, INSTALL_PIPE_KEY, INSTALL_PIPE_OPEN_KEY
                )

                start_seg_pt = segments[controller_start]["pt"]
                end_seg_pt = segments[dev_end]["pt"]

                raw_vertical_ft = abs(controller_pt.Z - start_seg_pt.Z) + abs(dev_pt.Z - end_seg_pt.Z)
                vertical_m = raw_vertical_ft * FT_TO_M

                final_tray_m = horiz_tray_m * HORIZ_TRAY_COEF
                final_pipe_m = (horiz_pipe_m + horiz_pipe_open_m) * HORIZ_PIPE_COEF + vertical_m * VERTICAL_COEF
                final_total_m = final_tray_m + final_pipe_m

                T, tr, pi = balance_round_parts(final_total_m, [final_tray_m, final_pipe_m])

                set_param_any(c, WIRE_LENGTH_PARAM, T)
                set_param_any(c, TRAY_LENGTH_PARAM, tr)
                set_param_any(c, PIPE_LENGTH_PARAM, pi)

                route_parts = []
                if pi > 0 and ROUTE_LABEL_PIPE:
                    route_parts.append(ROUTE_LABEL_PIPE.format(pi))
                if tr > 0 and ROUTE_LABEL_TRAY:
                    route_parts.append(ROUTE_LABEL_TRAY.format(tr))

                set_param_any(c, ROUTE_METHOD_PARAM, u"; ".join(route_parts))
                set_param_any(c, CIRCUIT_ROUTE_PARAM, u" -> ".join(path))

                # Путь уже есть списком — сразу копим, через какие узлы
                # проходит эта цепь (записываем после цикла, одним махом).
                for sid in path:
                    info = segment_info_map.setdefault(sid, {"loads": set(), "fo": 0, "utp": 0})
                    info["loads"].add(circuit_label)

    segments_written = 0
    for sid, info in segment_info_map.items():
        seg = segments.get(sid)
        if not seg:
            continue
        value = build_segment_list_text(info["loads"], info["fo"], info["utp"])
        if set_param_any(seg["el"], SEGMENT_LOADS_PARAM, value):
            segments_written += 1


# ------------------------------------------------------------
# ОТЧЁТ
# ------------------------------------------------------------

if broken_parent_links or no_path_report or duplicate_addr_report or no_segment_report:
    from pyrevit import script as pyrevit_script
    output = pyrevit_script.get_output()

    if no_segment_report:
        output.print_md(u"### Цепи без привязки к узлу маршрута ({})".format(len(no_segment_report)))
        if not segments:
            output.print_md(
                u"**В проекте не найдено ни одного адресованного узла трассы.** "
                u"Для устройств дальше порога «рядом с контроллером» нужны узлы "
                u"маршрута с адресами — расставьте их и пронумеруйте кнопками "
                u"«Узлы трассы СКУД» и «Адреса узлов СКУД»."
            )
        for line in no_segment_report[:100]:
            output.print_md(u"- {}".format(line))

    if duplicate_addr_report:
        output.print_md(u"### Дублирующиеся адреса узлов ({})".format(len(duplicate_addr_report)))
        for line in duplicate_addr_report:
            output.print_md(u"- {}".format(line))

    if broken_parent_links:
        output.print_md(u"### Разорванные ссылки «предыдущий адрес» ({})".format(len(broken_parent_links)))
        for line in broken_parent_links[:100]:
            output.print_md(u"- {}".format(line))

    if no_path_report:
        output.print_md(u"### Цепи без найденного пути ({})".format(len(no_path_report)))
        for line in no_path_report:
            output.print_md(u"- {}".format(line))

forms.alert(
    u"Готово.\n\n"
    u"Контроллеров: {}\n"
    u"Обработано цепей: {}\n"
    u"Рядом с контроллером (катеты): {}\n"
    u"По графу трассы: {}\n"
    u"Нет устройства в цепи: {}\n"
    u"Нет узла у контроллера/устройства: {}\n"
    u"Путь не найден: {}\n\n"
    u"Устройств маркировано: {}\n"
    u"Узлов со списком цепей: {}\n\n"
    u"Дублирующихся адресов: {}\n"
    u"Очищено чужих адресов: {}\n"
    u"Узлов чужого рабочего набора пропущено: {}\n\n"
    u"{}".format(
        len(controllers),
        processed_circuits,
        near_count,
        graph_count,
        no_device,
        no_segment,
        no_path,
        devices_marked,
        segments_written,
        len(duplicate_addr_report),
        len(stray_cleared),
        foreign_workset_nodes,
        u"Подробности — в окне вывода pyRevit." if (broken_parent_links or no_path_report or duplicate_addr_report or no_segment_report) else u""
    )
)
