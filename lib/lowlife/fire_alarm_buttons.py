# -*- coding: utf-8 -*-
"""
Тела кнопок СПС/СОУЭ — общие для обеих систем.

Скрипт кнопки только выбирает систему (fire_alarm_settings.set_system) и
вызывает нужную функцию отсюда: логика у СПС и СОУЭ одна, различаются
только настройки.
"""

from pyrevit import revit, forms, script as pyrevit_script

from lowlife.geometry import get_point
from lowlife.params import get_string_param, get_type_string_param, set_param_any, set_element_id_param
from lowlife.scs_circuits import norm, clean_text_value, make_load_name
from lowlife.fire_alarm import make_full_mark, group_devices_by_loop
from lowlife.fire_alarm_loops import (
    build_loop_tree, build_route_text, previous_address_by_id
)
from lowlife.fire_alarm_circuits import (
    find_panels, find_devices, existing_circuits_by_number, create_circuit,
    build_loop_nodes, write_loop_length, device_category_id
)
from lowlife import fire_alarm_settings


def _config_from(settings):
    return dict(settings)


def _collect(doc, config):
    """Панели, устройства и шлейфы — общий первый этап обеих кнопок."""
    panels = find_panels(doc, config)

    if not panels:
        forms.alert(
            u"Не найдено ни одной панели: рабочий набор содержит «{}», "
            u"«Обозначение» = «{}», «Адрес устройства» — одно число.".format(
                config["workset_filter_key"], config["panel_designation_key"]
            ),
            exitscript=True
        )

    devices, address_by_id, address_text_by_id, skipped = find_devices(doc, config)

    if not devices:
        forms.alert(
            u"Не найдено ни одного устройства с разбираемым адресом вида "
            u"«панель.шлейф.номер» в рабочем наборе «{}».".format(config["workset_filter_key"]),
            exitscript=True
        )

    loops = group_devices_by_loop(devices, address_by_id)

    return panels, devices, address_by_id, address_text_by_id, skipped, loops


def build_loop_circuits(doc, settings):
    """
    Создаёт по одной электрической цепи на каждый шлейф и подключает её к
    своей панели. Уже созданные цепи (по «Номеру цепи») не трогает.
    """
    config = _config_from(settings)

    panels, devices, address_by_id, address_text_by_id, skipped, loops = _collect(doc, config)

    number_format = config["circuit_number_format"]
    existing = existing_circuits_by_number(doc, config)

    category_wire_type_ids = (
        fire_alarm_settings.get_category_wire_type_elem_ids(doc)
        if config.get("cable_type_param") else {}
    )

    created = 0
    already = 0
    errors = []
    no_panel = []

    with revit.Transaction("Build {} Loop Circuits".format(fire_alarm_settings.current_title())):

        for (panel_num, loop_num) in sorted(loops.keys()):
            loop_devices = loops[(panel_num, loop_num)]

            panel_el = panels.get(panel_num)
            if panel_el is None:
                no_panel.append(
                    u"Шлейф {}.{}: панель с номером {} не найдена — {} устройств пропущено.".format(
                        panel_num, loop_num, panel_num, len(loop_devices)
                    )
                )
                continue

            circuit_number = number_format.format(u"{}.{}".format(panel_num, loop_num))

            if circuit_number in existing:
                already += 1
                continue

            circuit, error = create_circuit(
                doc, panel_el, loop_devices, config["circuit_system_type"]
            )

            if circuit is None:
                errors.append(u"Шлейф {}: {}".format(circuit_number, error))
                continue

            set_param_any(circuit, config["circuit_number_param"], circuit_number)
            set_param_any(circuit, config["circuit_panel_param"], norm(panel_el.Name))

            first = loop_devices[0]
            designation = clean_text_value(get_type_string_param(doc, first, config["designation_param"]))
            load_name = make_load_name(
                designation, address_text_by_id.get(first.Id.IntegerValue)
            )
            if load_name:
                set_param_any(circuit, config["load_name_param"], load_name)

            if category_wire_type_ids:
                cat_id = device_category_id(first)
                wire_type_id = category_wire_type_ids.get(cat_id) if cat_id is not None else None
                if wire_type_id is not None:
                    set_element_id_param(circuit, config["cable_type_param"], wire_type_id)

            created += 1

            if error:
                errors.append(u"Шлейф {}: {}".format(circuit_number, error))

    _report_collect_problems(skipped, no_panel, errors)

    forms.alert(
        u"Готово.\n\n"
        u"Панелей: {}\n"
        u"Устройств с адресом: {}\n"
        u"Шлейфов найдено: {}\n\n"
        u"Цепей создано: {}\n"
        u"Уже существовали: {}\n"
        u"Ошибок создания: {}\n"
        u"Шлейфов без панели: {}\n"
        u"Устройств с нечитаемым адресом: {}\n\n"
        u"{}".format(
            len(panels), len(devices), len(loops),
            created, already, len(errors), len(no_panel), len(skipped),
            u"Подробности — в окне вывода pyRevit." if (skipped or no_panel or errors) else u""
        )
    )


def calc_loop_lengths(doc, settings):
    """
    Считает длину каждого шлейфа по координатам устройств и записывает её
    в цепь, а также маршрут шлейфа и «Предыдущий адрес» на устройствах.
    """
    config = _config_from(settings)

    panels, devices, address_by_id, address_text_by_id, skipped, loops = _collect(doc, config)

    number_format = config["circuit_number_format"]
    existing = existing_circuits_by_number(doc, config)

    isolator_keyword = config.get("isolator_keyword")

    processed = 0
    no_circuit = []
    marked = 0
    prev_written = 0

    with revit.Transaction("Calc {} Loop Lengths".format(fire_alarm_settings.current_title())):

        for (panel_num, loop_num) in sorted(loops.keys()):
            loop_devices = loops[(panel_num, loop_num)]

            circuit_number = number_format.format(u"{}.{}".format(panel_num, loop_num))
            circuit = existing.get(circuit_number)

            nodes = build_loop_nodes(loop_devices, address_by_id, isolator_keyword)

            if not nodes:
                continue

            panel_el = panels.get(panel_num)
            panel_point = get_point(panel_el) if panel_el is not None else None

            ordered = build_loop_tree(nodes, panel_point)

            # «Предыдущий адрес» на устройствах — чтобы на плане была видна
            # фактическая топология, включая ветви от изоляторов.
            if config.get("addr_prev_param_name"):
                prev_by_id = previous_address_by_id(ordered, address_text_by_id)
                for node in ordered:
                    value = prev_by_id.get(node["id"], u"")
                    if set_param_any(node["element"], config["addr_prev_param_name"], value):
                        prev_written += 1

            if config.get("device_marking_param"):
                for node in ordered:
                    el = node["element"]
                    designation = clean_text_value(
                        get_type_string_param(doc, el, config["designation_param"])
                    )
                    mark = make_full_mark(designation, address_text_by_id.get(node["id"]))
                    if mark and set_param_any(el, config["device_marking_param"], mark):
                        marked += 1

            if circuit is None:
                no_circuit.append(
                    u"Шлейф {}: цепь не найдена — сначала запустите «Цепи шлейфов».".format(
                        circuit_number
                    )
                )
                continue

            write_loop_length(circuit, ordered, panel_point, config)

            if config.get("circuit_route_param"):
                set_param_any(circuit, config["circuit_route_param"],
                              build_route_text(ordered, address_text_by_id))

            processed += 1

    _report_collect_problems(skipped, no_circuit, [])

    forms.alert(
        u"Готово.\n\n"
        u"Панелей: {}\n"
        u"Устройств с адресом: {}\n"
        u"Шлейфов: {}\n\n"
        u"Длин записано: {}\n"
        u"Шлейфов без цепи: {}\n"
        u"Устройств маркировано: {}\n"
        u"«Предыдущий адрес» записан: {}\n"
        u"Устройств с нечитаемым адресом: {}\n\n"
        u"{}".format(
            len(panels), len(devices), len(loops),
            processed, len(no_circuit), marked, prev_written, len(skipped),
            u"Подробности — в окне вывода pyRevit." if (skipped or no_circuit) else u""
        )
    )


def _report_collect_problems(skipped, no_panel, errors):
    if not (skipped or no_panel or errors):
        return

    output = pyrevit_script.get_output()

    if skipped:
        output.print_md(u"### Устройства с нечитаемым адресом ({})".format(len(skipped)))
        output.print_md(
            u"Ожидается «панель.шлейф.номер», например `3.1.2`. "
            u"Эти устройства в шлейфы не попали:"
        )
        for el, raw in skipped[:100]:
            output.print_md(u"- ID {} — «{}»".format(el.Id.IntegerValue, raw))

    if no_panel:
        output.print_md(u"### Шлейфы без панели / без цепи ({})".format(len(no_panel)))
        for line in no_panel[:100]:
            output.print_md(u"- {}".format(line))

    if errors:
        output.print_md(u"### Ошибки ({})".format(len(errors)))
        for line in errors[:100]:
            output.print_md(u"- {}".format(line))
