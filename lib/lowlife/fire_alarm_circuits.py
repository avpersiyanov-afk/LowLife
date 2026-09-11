# -*- coding: utf-8 -*-
"""
Сборка электрических цепей по шлейфам СПС/СОУЭ и расчёт их длин.

Общее тело кнопок для обеих систем — различаются они только файлом
настроек (см. fire_alarm_settings.set_system), поэтому логика здесь одна.
"""

from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory
)

from lowlife.geometry import get_point
from lowlife.params import get_string_param, get_type_string_param, set_param_any
from lowlife.scs import is_excluded_device, get_workset_name
from lowlife.scs_circuits import clean_text_value, balance_round_parts
from lowlife.sot_levels import get_level_display_name
from lowlife.fire_alarm import (
    parse_device_address, parse_panel_address, is_isolator, is_riser
)
from lowlife.fire_alarm_loops import calc_loop_length_ft, FT_TO_M
from lowlife.electrical_circuits import resolve_system_type, create_circuit

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
    # Изоляторы шлейфа тоже смоделированы в этой категории — та же, что и
    # панель. Панель и изолятор различаются по адресу (find_panels ищет
    # одно число, обычные устройства/изоляторы — «панель.шлейф.номер»),
    # поэтому включение категории сюда не путает их местами.
    "OST_ElectricalEquipment",
]

_CATEGORY_TITLES = {
    "OST_FireAlarmDevices": u"Пожарная сигнализация",
    "OST_CommunicationDevices": u"Устройства связи",
    "OST_ElectricalFixtures": u"Электроустановочные устройства",
    "OST_DataDevices": u"Устройства передачи данных",
    "OST_SecurityDevices": u"Охранная сигнализация",
    "OST_NurseCallDevices": u"Устройства вызова и оповещения",
    "OST_ElectricalEquipment": u"Электрооборудование (изоляторы)",
}

DEVICE_CATEGORIES = []
CATEGORY_TITLE_BY_ID = {}
for _name in _CATEGORY_NAMES:
    _cat = getattr(BuiltInCategory, _name, None)
    if _cat is not None:
        DEVICE_CATEGORIES.append(_cat)
        CATEGORY_TITLE_BY_ID[int(_cat)] = _CATEGORY_TITLES[_name]

# Категории, исключаемые из сбора устройств для КОНКРЕТНЫХ систем (ключ —
# fire_alarm_settings.SYSTEMS, значение — имена BuiltInCategory).
# У СПА рядом с устройствами (в том же рабочем наборе) стоят electrical
# fixtures-устройства ("Электроприборы") — сопутствующее оборудование
# (РМ/АМ/МДУ, см. lowlife.companion_placement), физически подключённое к
# устройствам СПА, но это не адресные устройства шлейфа и не должны
# попадать в него/в шлейфовые цепи. У СПС/СОУЭ эта категория по-прежнему
# участвует как обычно — исключение только для СПА.
_SYSTEM_EXCLUDED_CATEGORY_NAMES = {
    "SPA": ("OST_ElectricalFixtures",),
}

_SYSTEM_EXCLUDED_CATEGORY_IDS = {}
for _system_key, _names in _SYSTEM_EXCLUDED_CATEGORY_NAMES.items():
    _ids = set()
    for _name in _names:
        _cat = getattr(BuiltInCategory, _name, None)
        if _cat is not None:
            _ids.add(int(_cat))
    if _ids:
        _SYSTEM_EXCLUDED_CATEGORY_IDS[_system_key] = _ids

# Категории, среди которых ищется стояк (find_risers) — те же, что и для
# устройств, плюс «Обобщённые модели» (типичная категория для маркера
# стояка/шахты, которая сама по себе не адресное устройство шлейфа и
# поэтому не входит в DEVICE_CATEGORIES). Стояк отличается от обычного
# устройства/панели только по ключевому слову в имени семейства
# (riser_keyword), не по категории.
RISER_CATEGORIES = list(DEVICE_CATEGORIES)
_riser_generic_model_cat = getattr(BuiltInCategory, "OST_GenericModel", None)
if _riser_generic_model_cat is not None and _riser_generic_model_cat not in RISER_CATEGORIES:
    RISER_CATEGORIES.append(_riser_generic_model_cat)


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
    excluded_category_ids = _SYSTEM_EXCLUDED_CATEGORY_IDS.get(config.get("_system"), ())

    devices = []
    address_by_id = {}
    address_text_by_id = {}
    skipped = []

    for cat in DEVICE_CATEGORIES:
        if int(cat) in excluded_category_ids:
            continue

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
                # Панели попадают в этот перебор тоже (та же категория,
                # что и изоляторы), но их адрес — одно число, а не
                # «панель.шлейф.номер»: это не ошибка, а ожидаемый вид
                # адреса панели, поэтому в отчёт о нечитаемых не пишем.
                if raw and parse_panel_address(raw) is None:
                    skipped.append((el, raw))
                continue

            eid = el.Id.IntegerValue
            devices.append(el)
            address_by_id[eid] = parsed
            address_text_by_id[eid] = raw

    return devices, address_by_id, address_text_by_id, skipped


def find_risers(doc, config):
    """
    Экземпляры стояка (по ключевому слову «riser_keyword» в имени
    семейства/типа) в рабочем наборе системы — для расчёта перехода
    шлейфа между этажами и обратного участка кольцевого шлейфа (см.
    fire_alarm_loops.calc_loop_length_ft). Категории поиска —
    RISER_CATEGORIES (устройства + «Обобщённые модели»).

    Пустой список, если ключевое слово не задано в настройках (стояк не
    используется — переход между этажами считается напрямую).

    Возвращает [{"id":, "pt":, "floor": имя этажа}, ...] — этаж тем же
    способом, что и у устройств (level_param_name, см. build_loop_nodes).
    """
    riser_keyword = config.get("riser_keyword")
    if not riser_keyword:
        return []

    level_param_name = config.get("level_param_name")
    risers = []
    seen_ids = set()

    for cat in RISER_CATEGORIES:
        try:
            found = FilteredElementCollector(doc) \
                .OfCategory(cat) \
                .WhereElementIsNotElementType() \
                .ToElements()
        except:
            continue

        for el in found:
            eid = el.Id.IntegerValue
            if eid in seen_ids:
                continue

            if not in_workset(el, config["workset_param_name"], config["workset_filter_key"]):
                continue

            if not is_riser(el, riser_keyword):
                continue

            pt = get_point(el)
            if pt is None:
                continue

            seen_ids.add(eid)
            risers.append({
                "id": eid,
                "pt": pt,
                "floor": get_level_display_name(doc, el, level_param_name),
            })

    return risers


def group_risers_by_floor(risers):
    """{имя этажа: [риски, ...]} из find_risers — вход для calc_loop_length_ft."""
    by_floor = {}
    for r in risers:
        by_floor.setdefault(r["floor"], []).append(r)
    return by_floor


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


def circuit_membership_map(doc, number_param):
    """
    {ID устройства: (номер цепи, ElementId цепи)} для устройств, которые
    УЖЕ состоят в какой-либо электрической цепи документа — любой, не
    только этой дисциплины (ручные тестовые цепи, цепи «изолятор-
    устройства» и т.п.).

    Revit не даёт добавить элемент, уже входящий в одну цепь, в другую —
    ошибка при этом та же самая electComponents, без внятного текста про
    причину, поэтому перед созданием новой цепи стоит явно проверить
    состав по этой карте.
    """
    result = {}

    circuits = FilteredElementCollector(doc) \
        .OfCategory(BuiltInCategory.OST_ElectricalCircuit) \
        .WhereElementIsNotElementType() \
        .ToElements()

    for c in circuits:
        number = clean_text_value(get_string_param(c, number_param))
        try:
            members = c.Elements
        except:
            continue
        for m in members:
            result[m.Id.IntegerValue] = (number, c.Id.IntegerValue)

    return result


def isolator_branch_device_map(doc, isolator_ids=None):
    """
    {ID изолятора (BaseEquipment цепи): [элементы-устройства]} — для
    цепей «изолятор -> устройства» (см.
    fire_alarm_isolator_circuits.build_isolator_device_circuits) BaseEquipment
    цепи это и есть сам изолятор, что даёт достоверный состав его
    ответвления напрямую из модели (а не по геометрии/адресу — то не
    отличает "продолжение магистрали" от "устройства на ветви", см.
    докстринг fire_alarm_loops).

    isolator_ids — необязательный набор int ElementId, к которым сузить
    результат: BaseEquipment каждой цепи документа (СКС/СКУД/ручных и
    т.п., не только "изолятор-устройства") всё равно приходится прочитать
    (дешёвое свойство), но .Elements (может быть дорогим на цепи с
    большим числом устройств) читается ТОЛЬКО для цепей, чей BaseEquipment
    входит в isolator_ids — на модели с тысячами цепей это на порядки
    быстрее, чем читать .Elements у каждой. Если isolator_ids не задан —
    прежнее поведение (без фильтра, читает всё).
    """
    result = {}
    wanted = set(isolator_ids) if isolator_ids is not None else None

    if wanted is not None and not wanted:
        return result

    circuits = FilteredElementCollector(doc) \
        .OfCategory(BuiltInCategory.OST_ElectricalCircuit) \
        .WhereElementIsNotElementType() \
        .ToElements()

    for c in circuits:
        try:
            base = c.BaseEquipment
        except:
            base = None
        if base is None:
            continue
        try:
            base_id = base.Id.IntegerValue
        except:
            continue
        if wanted is not None and base_id not in wanted:
            continue
        try:
            members = list(c.Elements)
        except:
            continue
        result.setdefault(base_id, []).extend(members)

    return result


def build_loop_nodes(doc, device_els, address_by_id, isolator_keyword, level_param_name=None):
    """
    Узлы шлейфа для build_loop_tree — из элементов Revit.

    "floor" — имя этажа устройства (level_param_name, тот же параметр, что
    и у структурной схемы; при пустом значении — реальный Level элемента,
    см. sot_levels.get_level_display_name) — нужен, чтобы calc_loop_length_ft
    мог посчитать переход между этажами через стояк, если этаж соседних по
    адресу узлов различается.
    """
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
            "floor": get_level_display_name(doc, el, level_param_name),
            "element": el,
        })

    return nodes


def write_loop_length(circuit, ordered_nodes, panel_point, panel_floor, risers_by_floor, ring_loop, config):
    """Считает и записывает длину шлейфа и сопутствующие параметры цепи."""
    length_ft = calc_loop_length_ft(
        ordered_nodes, panel_point, panel_floor=panel_floor,
        risers_by_floor=risers_by_floor, ring_loop=ring_loop
    )
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
