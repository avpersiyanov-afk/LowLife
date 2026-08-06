# -*- coding: utf-8 -*-
"""
Сборка электрических цепей по шлейфам СПС/СОУЭ и расчёт их длин.

Общее тело кнопок для обеих систем — различаются они только файлом
настроек (см. fire_alarm_settings.set_system), поэтому логика здесь одна.
"""

from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, ElementId
)
from Autodesk.Revit.DB.Electrical import ElectricalSystem, ElectricalSystemType

from lowlife.geometry import get_point
from lowlife.params import get_string_param, get_type_string_param, set_param_any
from lowlife.scs import is_excluded_device, get_workset_name
from lowlife.scs_circuits import clean_text_value, balance_round_parts
from lowlife.fire_alarm import (
    parse_device_address, parse_panel_address, is_isolator
)
from lowlife.fire_alarm_loops import calc_loop_length_ft, FT_TO_M

# Категории, среди которых ищутся устройства СПС/СОУЭ. Берём через
# getattr: набор BuiltInCategory отличается между версиями Revit, и
# отсутствующее имя иначе уронило бы модуль на импорте.
#
# Те же имена используются для подбора типа проводника по категории
# устройства (см. get_category_wire_type_elem_ids в fire_alarm_settings.py) —
# категории здесь фиксированы кодом, а не настраиваются текстом, как в
# SKUD (там категории устройств произвольные и задаются пользователем).
_CATEGORY_NAMES = [
    "OST_FireAlarmDevices",
    "OST_CommunicationDevices",
    "OST_ElectricalFixtures",
    "OST_DataDevices",
    "OST_SecurityDevices",
    "OST_NurseCallDevices",
]

_CATEGORY_TITLES = {
    "OST_FireAlarmDevices": u"Пожарная сигнализация",
    "OST_CommunicationDevices": u"Устройства связи",
    "OST_ElectricalFixtures": u"Электроустановочные устройства",
    "OST_DataDevices": u"Устройства передачи данных",
    "OST_SecurityDevices": u"Охранная сигнализация",
    "OST_NurseCallDevices": u"Устройства вызова и оповещения",
}

DEVICE_CATEGORIES = []
CATEGORY_TITLE_BY_ID = {}
for _name in _CATEGORY_NAMES:
    _cat = getattr(BuiltInCategory, _name, None)
    if _cat is not None:
        DEVICE_CATEGORIES.append(_cat)
        CATEGORY_TITLE_BY_ID[int(_cat)] = _CATEGORY_TITLES[_name]


def category_title(builtin_category):
    """Читаемое название фиксированной категории устройств СПС/СОУЭ."""
    return CATEGORY_TITLE_BY_ID.get(int(builtin_category), unicode(builtin_category))


def device_category_id(el):
    """int(BuiltInCategory) устройства, если это одна из DEVICE_CATEGORIES, иначе None."""
    try:
        cat_id = el.Category.Id.IntegerValue
    except:
        return None
    return cat_id if cat_id in CATEGORY_TITLE_BY_ID else None


def in_workset(el, workset_param_name, workset_filter_key):
    if not workset_filter_key:
        return True
    ws = get_workset_name(el, workset_param_name)
    return bool(ws) and workset_filter_key.lower() in ws.lower()


def find_panels(doc, config):
    """
    Панели системы: электрооборудование нужного рабочего набора, у
    которого «Обозначение» совпадает с заданным (например ARK), а
    «Адрес устройства» — одно число (номер панели).

    Возвращает {номер панели: элемент}.
    """
    designation_param = config["designation_param"]
    address_param = config["device_address_param"]
    panel_key = (config["panel_designation_key"] or u"").lower()

    panels = {}

    equipment = FilteredElementCollector(doc) \
        .OfCategory(BuiltInCategory.OST_ElectricalEquipment) \
        .WhereElementIsNotElementType() \
        .ToElements()

    for el in equipment:
        if not in_workset(el, config["workset_param_name"], config["workset_filter_key"]):
            continue

        designation = clean_text_value(get_type_string_param(doc, el, designation_param))
        if not designation or designation.lower() != panel_key:
            continue

        panel_num = parse_panel_address(clean_text_value(get_string_param(el, address_param)))
        if panel_num is None:
            continue

        panels.setdefault(panel_num, el)

    return panels


def find_devices(doc, config):
    """
    Устройства системы: нужный рабочий набор + разбираемый адрес вида
    «панель.шлейф.номер».

    Возвращает (devices, address_by_id, address_text_by_id, skipped_no_address).
    """
    address_param = config["device_address_param"]
    excluded = config.get("excluded_device_keywords") or []

    devices = []
    address_by_id = {}
    address_text_by_id = {}
    skipped = []

    for cat in DEVICE_CATEGORIES:
        try:
            found = FilteredElementCollector(doc) \
                .OfCategory(cat) \
                .WhereElementIsNotElementType() \
                .ToElements()
        except:
            continue

        for el in found:
            if not in_workset(el, config["workset_param_name"], config["workset_filter_key"]):
                continue

            if is_excluded_device(el, excluded):
                continue

            raw = clean_text_value(get_string_param(el, address_param))
            parsed = parse_device_address(raw)

            if parsed is None:
                if raw:
                    skipped.append((el, raw))
                continue

            eid = el.Id.IntegerValue
            devices.append(el)
            address_by_id[eid] = parsed
            address_text_by_id[eid] = raw

    return devices, address_by_id, address_text_by_id, skipped


def existing_circuits_by_number(doc, config):
    """Уже созданные цепи системы по значению «Номер цепи»."""
    number_param = config["circuit_number_param"]
    result = {}

    circuits = FilteredElementCollector(doc) \
        .OfCategory(BuiltInCategory.OST_ElectricalCircuit) \
        .WhereElementIsNotElementType() \
        .ToElements()

    for c in circuits:
        number = clean_text_value(get_string_param(c, number_param))
        if number:
            result.setdefault(number, c)

    return result


def resolve_system_type(name):
    """
    ElectricalSystemType по имени из настроек ("FireAlarm", "Data",
    "Communication", "Security", "NurseCall", "Power"...).

    Возвращает (тип, текст ошибки): набор значений отличается между
    версиями Revit, поэтому имя проверяется через getattr, а не
    фиксируется в коде.
    """
    value = (name or u"").strip()

    if not value:
        return None, u"тип цепи не задан в настройках"

    system_type = getattr(ElectricalSystemType, value, None)

    if system_type is None:
        available = [a for a in dir(ElectricalSystemType) if not a.startswith("_")]
        return None, u"неизвестный тип цепи «{}». Доступные: {}".format(
            value, u", ".join(sorted(available))
        )

    return system_type, None


def create_circuit(doc, panel_el, device_els, system_type_name):
    """
    Создаёт электрическую цепь из устройств и подключает её к панели.

    Тип цепи задаётся настройкой системы: у СПС это пожарная сигнализация
    (FireAlarm), у СОУЭ может быть свой — поэтому он не зашит в код.

    Возвращает (цепь, текст ошибки).
    """
    from System.Collections.Generic import List

    system_type, error = resolve_system_type(system_type_name)
    if system_type is None:
        return None, error

    # Revit требует, чтобы среди переданных элементов был хотя бы один,
    # способный "создать" цепь заданного типа — это панель, а не нагрузки:
    # без неё ElectricalSystem.Create падает с electComponents, даже если
    # панель потом отдельно назначается через SelectPanel.
    ids = List[ElementId]()
    ids.Add(panel_el.Id)
    for el in device_els:
        ids.Add(el.Id)

    try:
        system = ElectricalSystem.Create(doc, ids, system_type)
    except Exception as ex:
        return None, u"не удалось создать цепь типа «{}»: {}".format(system_type_name, ex)

    if system is None:
        return None, u"Revit не создал цепь"

    try:
        system.SelectPanel(panel_el)
    except Exception as ex:
        return system, u"цепь создана, но не подключена к панели: {}".format(ex)

    return system, None


def build_loop_nodes(device_els, address_by_id, isolator_keyword):
    """Узлы шлейфа для build_loop_tree — из элементов Revit."""
    nodes = []

    for el in device_els:
        pt = get_point(el)
        if pt is None:
            continue

        eid = el.Id.IntegerValue
        nodes.append({
            "id": eid,
            "index": address_by_id[eid][2],
            "pt": pt,
            "is_isolator": is_isolator(el, isolator_keyword),
            "element": el,
        })

    return nodes


def write_loop_length(circuit, ordered_nodes, panel_point, config):
    """Считает и записывает длину шлейфа и сопутствующие параметры цепи."""
    length_ft = calc_loop_length_ft(ordered_nodes, panel_point)
    length_m = length_ft * FT_TO_M * float(config["length_coef"])

    total = balance_round_parts(length_m, [length_m])[0]

    set_param_any(circuit, config["wire_length_param"], total)

    # Шлейфы СПС/СОУЭ прокладывают в трубе — лоток остаётся нулевым, но
    # параметры заполняются, чтобы спецификация считалась одинаково со
    # всеми остальными системами.
    if config.get("pipe_length_param"):
        set_param_any(circuit, config["pipe_length_param"], total)
    if config.get("tray_length_param"):
        set_param_any(circuit, config["tray_length_param"], 0)

    if config.get("route_method_param") and config.get("route_label_pipe_format") and total > 0:
        set_param_any(circuit, config["route_method_param"],
                      config["route_label_pipe_format"].format(total))

    return total
