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
from lowlife.fire_alarm import make_full_mark, group_devices_by_loop, is_isolator
from lowlife.fire_alarm_loops import build_loop_tree, build_route_text, previous_address_by_id, FT_TO_M
from lowlife.fire_alarm_circuits import (
    find_panels, find_devices, existing_circuits_by_number, create_circuit,
    build_loop_nodes, write_loop_length, device_category_id, circuit_membership_map
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
    своей панели. Устройства, уже подключённые к изолятору отдельной
    цепью (кнопка «Цепи изолятор-устройства»), в магистральную цепь не
    включаются — они электрически "за" изолятором. Уже созданные цепи
    (по «Номеру цепи») не трогает.

    Раньше состав "магистраль vs ветка" определялся геометрической
    догадкой (ближайший сосед по расстоянию, fire_alarm_loops.
    build_loop_tree/split_branch_devices) — она ошибалась в обе стороны:
    то оставляла в магистрали устройства, которые на самом деле уже
    подключены к изолятору отдельной цепью (ловили electComponents), то
    наоборот исключала из магистрали обычные устройства без адреса на
    изоляторе, которые ошибочно оказывались "ближе" к изолятору чисто по
    координатам. Единственный надёжный источник истины — это то, что
    Revit уже знает сам: реальное членство устройства в существующей
    электрической цепи. Поэтому исключение теперь только одно —
    устройство, уже состоящее в какой-либо цепи документа (см.
    fire_alarm_circuits.circuit_membership_map); всё остальное из шлейфа
    (включая изоляторы) идёт в магистраль.
    """
    config = _config_from(settings)

    panels, devices, address_by_id, address_text_by_id, skipped, loops = _collect(doc, config)

    number_format = config["circuit_number_format"]
    existing = existing_circuits_by_number(doc, config)
    membership = circuit_membership_map(doc, config["circuit_number_param"])

    category_wire_type_ids = (
        fire_alarm_settings.get_category_wire_type_elem_ids(doc)
        if config.get("cable_type_param") else {}
    )

    isolator_keyword = config.get("isolator_keyword")

    created = 0
    already = 0
    errors = []
    no_panel = []
    already_circuited_total = 0

    output = pyrevit_script.get_output()
    output.print_md(u"## Отладка «Цепи шлейфов»")
    output.print_md(
        u"Ключевое слово изолятора: «{}»{}".format(
            isolator_keyword or u"",
            u" — **ПУСТО, is_isolator() всегда вернёт False!**"
            if not isolator_keyword else u""
        )
    )

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

            isolator_count = sum(1 for el in loop_devices if is_isolator(el, isolator_keyword))

            # Единственное исключение из магистрали: устройство уже
            # состоит в какой-либо электрической цепи документа (обычно —
            # подключено к своему изолятору через «Цепи
            # изолятор-устройства»). Revit не даёт добавить такой элемент
            # ещё в одну цепь — без этой проверки та же ошибка
            # electComponents, без внятного текста о причине.
            already_in_circuit = [
                (el, membership[el.Id.IntegerValue])
                for el in loop_devices
                if el.Id.IntegerValue in membership
            ]
            already_ids = set(el.Id.IntegerValue for el, _ in already_in_circuit)
            trunk_devices = [el for el in loop_devices if el.Id.IntegerValue not in already_ids]

            output.print_md(
                u"Шлейф {}: всего {}, изоляторов {}, в магистрали {}, уже в другой цепи {}".format(
                    circuit_number, len(loop_devices), isolator_count,
                    len(trunk_devices), len(already_in_circuit)
                )
            )
            if already_in_circuit:
                already_circuited_total += len(already_in_circuit)
                for el, (existing_number, circ_id) in already_in_circuit:
                    output.print_md(
                        u"- ID {} уже в цепи ID {} (Номер цепи «{}»)".format(
                            el.Id.IntegerValue, circ_id, existing_number or u"—"
                        )
                    )

            if not trunk_devices:
                no_panel.append(
                    u"Шлейф {}: все устройства уже состоят в других цепях — "
                    u"магистральная цепь не создана.".format(circuit_number)
                )
                continue

            circuit, error = create_circuit(
                doc, panel_el, trunk_devices, config["circuit_system_type"]
            )

            if circuit is None:
                errors.append(
                    u"Шлейф {}: {} [панель ID {}, устройств {}: {}]".format(
                        circuit_number, error, panel_el.Id.IntegerValue, len(trunk_devices),
                        u", ".join(str(d.Id.IntegerValue) for d in trunk_devices)
                    )
                )
                output.print_md(u"#### Шлейф {} — не удалось создать цепь, состав магистрали:".format(circuit_number))
                for i, el in enumerate(trunk_devices):
                    try:
                        cat_name = el.Category.Name if el.Category else u"?"
                    except:
                        cat_name = u"?"
                    try:
                        type_el = doc.GetElement(el.GetTypeId())
                        fam_name = type_el.Family.Name if type_el and type_el.Family else u"?"
                    except:
                        fam_name = u"?"
                    output.print_md(
                        u"{}. ID {}: категория «{}», семейство «{}»".format(
                            i + 1, el.Id.IntegerValue, cat_name, fam_name
                        )
                    )
                continue

            set_param_any(circuit, config["circuit_number_param"], circuit_number)
            set_param_any(circuit, config["circuit_panel_param"], norm(panel_el.Name))

            first = trunk_devices[0]
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

            # Режим траектории Revit «Все устройства» + «Длина проводника»/
            # «Способ прокладки» по получившейся Length — тем же способом,
            # что и build_isolator_device_circuits
            # (fire_alarm_isolator_circuits.py). Всё в одном try/except:
            # сбой здесь не должен откатывать всю транзакцию (в ней —
            # цепи ВСЕХ шлейфов набора, не только текущего).
            try:
                # CircuitPathMode — свойство самого экземпляра
                # ElectricalSystem (подтверждено через dir(circuit) в
                # Revit 2024), но не резолвится как отдельный импортируемый
                # тип по стандартному пути
                # Autodesk.Revit.DB.Electrical.CircuitPathMode. Берём
                # enum-тип прямо из текущего значения свойства — так не
                # нужно знать точный путь импорта/вложенность типа в этой
                # сборке Revit API.
                path_mode_type = type(circuit.CircuitPathMode)
                all_devices_mode = getattr(path_mode_type, "AllDevices", None)
                if all_devices_mode is not None:
                    circuit.CircuitPathMode = all_devices_mode
                # Length ниже читается сразу в этой же транзакции — без
                # регенерации он ещё отражал бы путь по старому режиму.
                doc.Regenerate()

                if config.get("wire_length_param"):
                    total = int(round(circuit.Length * FT_TO_M * float(config["length_coef"])))
                    set_param_any(circuit, config["wire_length_param"], total)

                    if config.get("route_method_param") and config.get("route_label_pipe_format") and total > 0:
                        set_param_any(
                            circuit, config["route_method_param"],
                            config["route_label_pipe_format"].format(total)
                        )
            except Exception as ex:
                try:
                    output.print_md(
                        u"Шлейф {}: не удалось проставить режим траектории/длину — {}: {}".format(
                            circuit_number, type(ex).__name__, ex
                        )
                    )
                except:
                    pass

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
        u"Устройств с нечитаемым адресом: {}\n"
        u"Устройств, уже состоявших в другой цепи (исключены из магистральной цепи): {}\n\n"
        u"{}".format(
            len(panels), len(devices), len(loops),
            created, already, len(errors), len(no_panel), len(skipped),
            already_circuited_total,
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
