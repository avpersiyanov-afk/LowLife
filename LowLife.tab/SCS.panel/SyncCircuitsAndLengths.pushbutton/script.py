# -*- coding: utf-8 -*-
__title__ = "Синхронизация цепей"
__doc__ = "Считает длины кабеля по трассе и номера/маршруты цепей для целевых панелей"
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms

from lowlife.geometry import get_point
from lowlife.params import get_string_param, get_param_any, set_param_any
from lowlife.scs import clear_stray_address_params
from lowlife import scs_settings
from lowlife.scs_settings import get_settings_silent
from lowlife.scs_circuits import (
    norm, clean_text_value, split_multi_value,
    build_graph, bfs_component, find_closest_pair_between_sets,
    astar_path, calc_lengths, balance_round_parts,
    classify_circuit_type, make_load_name, build_segment_list_text
)

doc = revit.doc


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

scs_settings.require(settings, [
    "route_type_id", "riser_type_id",
    "workset_filter_key",
    "install_tray_key", "install_pipe_key", "install_pipe_open_key",
    "route_label_pipe_format", "route_label_tray_format", "route_label_pipe_open_format",
    "circuit_key_fo", "circuit_key_utp", "circuit_key_power",
    "horiz_tray_coef", "horiz_pipe_coef", "vertical_coef"
])
# Имена параметров (addr_param_name, cable_param_name, workset_param_name,
# circuit_panel_param, nearest_segment_param, device_address_param,
# type_code_param, circuit_name_type_param, circuit_number_param,
# circuit_route_param, *_length_param, route_method_param,
# load_name_param, segment_loads_param) здесь не проверяются — их
# наличие/привязку в проекте проверяет и чинит кнопка «Параметры СКС»
# (SetupParameters).

ROUTE_TYPE_ID = ElementId(int(settings["route_type_id"]))
RISER_TYPE_ID = ElementId(int(settings["riser_type_id"]))

ADDR_PARAM = settings["addr_param_name"]
ADDR_PREV_PARAM = settings["addr_prev_param_name"]
CABLE_PARAM_NAME = settings["cable_param_name"]

WORKSET_PARAM_NAME = settings["workset_param_name"]
WORKSET_FILTER_KEY = settings["workset_filter_key"]
EXCLUDED_DEVICE_KEYWORDS = settings["excluded_device_keywords"]

CIRCUIT_PANEL_PARAM = settings["circuit_panel_param"]
NEAREST_SEGMENT_PARAM = settings["nearest_segment_param"]
DEVICE_ADDRESS_PARAM = settings["device_address_param"]
TYPE_CODE_PARAM = settings["type_code_param"]
CIRCUIT_NAME_TYPE_PARAM = settings["circuit_name_type_param"]
CIRCUIT_NUMBER_PARAM = settings["circuit_number_param"]
CIRCUIT_ROUTE_PARAM = settings["circuit_route_param"]
WIRE_LENGTH_PARAM = settings["wire_length_param"]
TRAY_LENGTH_PARAM = settings["tray_length_param"]
PIPE_LENGTH_PARAM = settings["pipe_length_param"]
ROUTE_METHOD_PARAM = settings["route_method_param"]
LOAD_NAME_PARAM = settings["load_name_param"]
SEGMENT_LOADS_PARAM = settings["segment_loads_param"]

INSTALL_TRAY_KEY = settings["install_tray_key"]
INSTALL_PIPE_KEY = settings["install_pipe_key"]
INSTALL_PIPE_OPEN_KEY = settings["install_pipe_open_key"]

ROUTE_LABEL_PIPE = settings["route_label_pipe_format"]
ROUTE_LABEL_TRAY = settings["route_label_tray_format"]
ROUTE_LABEL_PIPE_OPEN = settings["route_label_pipe_open_format"]

CIRCUIT_KEY_FO = settings["circuit_key_fo"]
CIRCUIT_KEY_UTP = settings["circuit_key_utp"]
CIRCUIT_KEY_POWER = settings["circuit_key_power"]

HORIZ_TRAY_COEF = float(settings["horiz_tray_coef"])
HORIZ_PIPE_COEF = float(settings["horiz_pipe_coef"])
VERTICAL_COEF = float(settings["vertical_coef"])


def is_excluded_device(el):
    """Резервный (исключаемый из расчёта) порт — по ключевым словам в имени семейства."""
    try:
        fam_name = el.Symbol.Family.Name
    except:
        return False
    return any(w.lower() in (fam_name or u"").lower() for w in EXCLUDED_DEVICE_KEYWORDS if w)


def get_workset_name(el):
    val = get_param_any(el, WORKSET_PARAM_NAME)
    if val:
        return val
    try:
        p = el.get_Parameter(BuiltInParameter.ELEM_PARTITION_PARAM)
        if p and p.HasValue:
            v = p.AsValueString()
            if v:
                return v
    except:
        pass
    return None


def panel_matches(panel):
    ws = norm(get_workset_name(panel))
    if not ws:
        return False
    return WORKSET_FILTER_KEY.lower() in ws.lower()


# ------------------------------------------------------------
# ОЧИСТКА "ЧУЖИХ" АДРЕСОВ
# ------------------------------------------------------------
# См. комментарий в RenumberAddresses — устройства/панели могли унаследовать
# значения ADDR_PARAM/ADDR_PREV_PARAM с прежних запусков или ручного ввода.

with revit.Transaction("Clear stray route addresses"):
    stray_cleared = clear_stray_address_params(
        doc, [ADDR_PARAM, ADDR_PREV_PARAM], set([ROUTE_TYPE_ID, RISER_TYPE_ID])
    )


# ------------------------------------------------------------
# СБОР УЗЛОВ МАРШРУТА (СЕГМЕНТОВ)
# ------------------------------------------------------------

segments = {}
parents_by_id = {}
duplicate_addr_report = []

all_generic = FilteredElementCollector(doc) \
    .OfCategory(BuiltInCategory.OST_GenericModel) \
    .WhereElementIsNotElementType() \
    .ToElements()

for e in all_generic:
    if e.GetTypeId() not in (ROUTE_TYPE_ID, RISER_TYPE_ID):
        continue

    pt = get_point(e)
    if pt is None:
        continue

    sid = clean_text_value(get_string_param(e, ADDR_PARAM))
    if not sid:
        continue

    if sid in segments:
        duplicate_addr_report.append(
            u"Адрес «{}»: элементы {} и {} — оставлен первый, второй проигнорирован. "
            u"Запустите «Адреса узлов» заново.".format(
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

if not segments:
    forms.alert(u"Не найдено ни одного адресованного узла маршрута (сначала запустите «Адреса узлов»).", exitscript=True)

graph, broken_parent_links = build_graph(segments, parents_by_id)


# ------------------------------------------------------------
# ЦЕЛЕВЫЕ ПАНЕЛИ И ЦЕПИ
# ------------------------------------------------------------

all_panels = FilteredElementCollector(doc) \
    .OfCategory(BuiltInCategory.OST_ElectricalEquipment) \
    .WhereElementIsNotElementType() \
    .ToElements()

target_panels = [p for p in all_panels if panel_matches(p)]
target_panel_names = set(norm(p.Name) for p in target_panels if norm(p.Name))

if not target_panels:
    forms.alert(
        u"Не найдено ни одной панели с рабочим набором, содержащим «{}».".format(WORKSET_FILTER_KEY),
        exitscript=True
    )

all_circuits = FilteredElementCollector(doc) \
    .OfCategory(BuiltInCategory.OST_ElectricalCircuit) \
    .WhereElementIsNotElementType() \
    .ToElements()

circuits_by_panel_name = {}
for c in all_circuits:
    panel_name = norm(get_string_param(c, CIRCUIT_PANEL_PARAM))
    if panel_name:
        circuits_by_panel_name.setdefault(panel_name, []).append(c)


# ------------------------------------------------------------
# НУМЕРАЦИЯ ОПТИЧЕСКИХ И СИЛОВЫХ ЦЕПЕЙ
# ------------------------------------------------------------

fo_circuits = []
power_circuits = []

for c in all_circuits:
    panel_name = norm(get_string_param(c, CIRCUIT_PANEL_PARAM))
    if panel_name not in target_panel_names:
        continue

    name_type_value = get_string_param(c, CIRCUIT_NAME_TYPE_PARAM)
    circuit_class = classify_circuit_type(name_type_value, CIRCUIT_KEY_FO, CIRCUIT_KEY_UTP, CIRCUIT_KEY_POWER)

    if circuit_class == "FO":
        fo_circuits.append(c)
    elif circuit_class == "POWER":
        power_circuits.append(c)

fo_circuits.sort(key=lambda x: (norm(get_string_param(x, CIRCUIT_PANEL_PARAM)) or u"", norm(x.Name) or u"", x.Id.IntegerValue))
power_circuits.sort(key=lambda x: (norm(get_string_param(x, CIRCUIT_PANEL_PARAM)) or u"", norm(x.Name) or u"", x.Id.IntegerValue))

fo_number_written = 0
power_number_written = 0

with revit.Transaction("Number FO/Power circuits"):
    idx = 1
    for c in fo_circuits:
        if set_param_any(c, CIRCUIT_NUMBER_PARAM, u"FO-{}".format(idx)):
            fo_number_written += 1
        idx += 1

    idx = 1
    for c in power_circuits:
        if set_param_any(c, CIRCUIT_NUMBER_PARAM, u"PWR-{}".format(idx)):
            power_number_written += 1
        idx += 1


# ------------------------------------------------------------
# ОСНОВНОЙ ПРОХОД: ДЛИНЫ И МАРШРУТЫ ЦЕПЕЙ
# ------------------------------------------------------------

segment_info_map = {}
processed_devices = {}
no_path_report = []

processed_panels = 0
processed_circuits = 0
ok_paths = 0
no_path = 0
no_panel_start = 0
no_device = 0
no_end = 0
missing_segment = 0

with revit.Transaction("Sync Circuits And Lengths"):

    for panel in target_panels:
        panel_name = norm(panel.Name)
        panel_pt = get_point(panel)

        panel_start = clean_text_value(get_string_param(panel, NEAREST_SEGMENT_PARAM))

        if not panel_start:
            no_panel_start += 1
            continue

        processed_panels += 1
        panel_circuits = circuits_by_panel_name.get(panel_name, [])

        for c in panel_circuits:
            try:
                raw_devs = [x for x in c.Elements if x.Id != panel.Id]
            except:
                continue

            normal_devs = [d for d in raw_devs if not is_excluded_device(d)]

            if not normal_devs:
                no_device += 1
                continue

            dev = normal_devs[0]
            dev_id = dev.Id.IntegerValue

            if dev_id not in processed_devices:
                dev_pt = get_point(dev)
                nearest_sid = clean_text_value(get_string_param(dev, NEAREST_SEGMENT_PARAM))
                processed_devices[dev_id] = (nearest_sid, dev_pt)

            end_sid, dev_pt = processed_devices.get(dev_id, (None, None))

            if not end_sid:
                no_end += 1
                continue

            if panel_start not in segments or end_sid not in segments:
                missing_segment += 1
                continue

            path = astar_path(segments, graph, panel_start, end_sid)
            processed_circuits += 1

            if not path:
                no_path += 1

                start_component = bfs_component(graph, panel_start)
                end_component = bfs_component(graph, end_sid)
                near_a, near_b, gap = find_closest_pair_between_sets(segments, start_component, end_component)

                no_path_report.append(
                    u"Цепь «{}» (панель {}): {} -> {} — путь не найден. "
                    u"Ближайший разрыв: {} <-> {} (зазор {:.2f} м)".format(
                        norm(c.Name) or c.Id.IntegerValue, panel_name,
                        panel_start, end_sid,
                        near_a, near_b,
                        (gap * 0.3048) if gap is not None else 0.0
                    )
                )
                continue

            route_path_text = u" -> ".join(path)

            horiz_total_m, horiz_tray_m, horiz_pipe_m, horiz_pipe_open_m = calc_lengths(
                segments, path, INSTALL_TRAY_KEY, INSTALL_PIPE_KEY, INSTALL_PIPE_OPEN_KEY
            )

            start_seg_pt = segments[panel_start]["pt"]
            end_seg_pt = segments[end_sid]["pt"]

            raw_vertical_ft = 0.0
            if panel_pt:
                raw_vertical_ft += abs(panel_pt.Z - start_seg_pt.Z)
            if dev_pt:
                raw_vertical_ft += abs(dev_pt.Z - end_seg_pt.Z)

            vertical_m = raw_vertical_ft * 0.3048

            final_tray_m = horiz_tray_m * HORIZ_TRAY_COEF
            final_pipe_m = (horiz_pipe_m * HORIZ_PIPE_COEF) + (vertical_m * VERTICAL_COEF)
            final_pipe_open_m = horiz_pipe_open_m * HORIZ_PIPE_COEF
            final_total_m = final_tray_m + final_pipe_m + final_pipe_open_m

            T, tr, pi, po = balance_round_parts(final_total_m, [final_tray_m, final_pipe_m, final_pipe_open_m])
            pipe_total_for_param = pi + po

            set_param_any(c, WIRE_LENGTH_PARAM, T)
            set_param_any(c, TRAY_LENGTH_PARAM, tr)
            set_param_any(c, PIPE_LENGTH_PARAM, pipe_total_for_param)

            route_parts = []
            if pi > 0 and ROUTE_LABEL_PIPE:
                route_parts.append(ROUTE_LABEL_PIPE.format(pi))
            if po > 0 and ROUTE_LABEL_PIPE_OPEN:
                route_parts.append(ROUTE_LABEL_PIPE_OPEN.format(po))
            if tr > 0 and ROUTE_LABEL_TRAY:
                route_parts.append(ROUTE_LABEL_TRAY.format(tr))

            set_param_any(c, ROUTE_METHOD_PARAM, u"; ".join(route_parts))
            set_param_any(c, CIRCUIT_ROUTE_PARAM, route_path_text)

            name_type_value = get_string_param(c, CIRCUIT_NAME_TYPE_PARAM)
            circuit_class = classify_circuit_type(name_type_value, CIRCUIT_KEY_FO, CIRCUIT_KEY_UTP, CIRCUIT_KEY_POWER)

            load_name = None
            if circuit_class != "FO":
                type_el = None
                try:
                    type_el = doc.GetElement(dev.GetTypeId())
                except:
                    pass

                type_code = clean_text_value(get_string_param(type_el, TYPE_CODE_PARAM)) if type_el else None
                device_address = clean_text_value(get_string_param(dev, DEVICE_ADDRESS_PARAM))
                load_name = make_load_name(type_code, device_address)

                if load_name:
                    set_param_any(c, LOAD_NAME_PARAM, load_name)

            segment_list_name = clean_text_value(get_string_param(c, CIRCUIT_NUMBER_PARAM))
            if not segment_list_name:
                segment_list_name = clean_text_value(load_name)
            if not segment_list_name:
                segment_list_name = clean_text_value(norm(c.Name)) or u"Circuit {}".format(c.Id.IntegerValue)

            for sid in path:
                info = segment_info_map.setdefault(sid, {"loads": set(), "fo": 0, "utp": 0})
                if segment_list_name:
                    info["loads"].add(segment_list_name)
                if circuit_class == "FO":
                    info["fo"] += 1
                elif circuit_class == "UTP":
                    info["utp"] += 1

            ok_paths += 1

    segments_written = 0
    for sid, info in segment_info_map.items():
        seg = segments.get(sid)
        if not seg:
            continue
        value = build_segment_list_text(info["loads"], info["fo"], info["utp"])
        if set_param_any(seg["el"], SEGMENT_LOADS_PARAM, value):
            segments_written += 1


if broken_parent_links or no_path_report or duplicate_addr_report:
    from pyrevit import script as pyrevit_script
    output = pyrevit_script.get_output()

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
    u"Целевых панелей: {}\n"
    u"Обработано цепей: {}\n"
    u"Путь найден: {}\n"
    u"Путь не найден: {}\n\n"
    u"Нет стартового узла у панели: {}\n"
    u"Нет устройства в цепи: {}\n"
    u"Нет узла у устройства: {}\n"
    u"Отсутствует узел в графе: {}\n"
    u"Разорванных ссылок «предыдущий адрес»: {}\n"
    u"Дублирующихся адресов: {}\n"
    u"Очищено чужих адресов: {}\n\n"
    u"Пронумеровано FO: {}\n"
    u"Пронумеровано силовых: {}\n"
    u"Записано узлов со списком цепей: {}\n\n"
    u"{}".format(
        processed_panels,
        processed_circuits,
        ok_paths,
        no_path,
        no_panel_start,
        no_device,
        no_end,
        missing_segment,
        len(broken_parent_links),
        len(duplicate_addr_report),
        len(stray_cleared),
        fo_number_written,
        power_number_written,
        segments_written,
        u"Подробности — в окне вывода pyRevit." if (broken_parent_links or no_path_report or duplicate_addr_report) else u""
    )
)
