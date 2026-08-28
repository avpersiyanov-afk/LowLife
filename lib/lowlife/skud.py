# -*- coding: utf-8 -*-
"""
Общие константы и логика для инструментов СКУД (контроль доступа).

Значения по умолчанию НЕ заданы намеренно — см. scs.py: имена
семейств/параметров вводятся в окне настроек (skud_settings.py) и
сохраняются в %APPDATA%\\pyRevit\\LowLifeSKUD_settings.json.
"""

from lowlife.scs import get_workset_name, safe_element_name


CONTROLLER_WORKSET_KEYWORD = u""
CONTROLLER_TYPE_KEYWORD = u""


def is_controller(el, workset_param_name, workset_keyword, type_keyword):
    """Контроллер — рабочий набор содержит workset_keyword И имя типа содержит type_keyword."""
    ws = get_workset_name(el, workset_param_name)
    if not ws or workset_keyword.lower() not in ws.lower():
        return False

    try:
        type_name = safe_element_name(el.Symbol) or u""
    except:
        return False

    return type_keyword.lower() in type_name.lower()


def parse_category_names(text):
    """
    "контроллер\nсчитыватель\nзамок" -> [u"контроллер", u"считыватель", u"замок"]
    — имена категорий устройств схемы, по одной на строку. Сопоставление
    категории с реальными устройствами идёт по точному типу семейства
    (см. category_by_type_id), не по ключевым словам.
    """
    names = []
    if not text:
        return names

    raw_items = text.replace(u"\r\n", u"\n").split(u"\n")

    for item in raw_items:
        name = item.strip()
        if name and name not in names:
            names.append(name)

    return names


def category_by_type_id(el, category_type_ids):
    """
    Категория реального устройства по точному совпадению ElementId его
    типа (category_type_ids — {имя_категории: set(int)} из настроек,
    см. skud_settings.get_schematic_category_device_type_ids). Заменяет
    сопоставление по ключевым словам — категория определяется явным
    выбором типов в настройках, а не текстовым совпадением имени.
    """
    try:
        type_id = el.GetTypeId().IntegerValue
    except:
        return None

    for name, type_ids in category_type_ids.items():
        if type_id in type_ids:
            return name

    return None


def collect_controller_devices(doc, workset_param, workset_keyword, type_keyword,
                               circuit_panel_param, excluded_keywords):
    """
    [(контроллер, [устройства])] — контроллеры СКУД и их подключённые
    устройства: по всем цепям контроллера (параметр цепи
    circuit_panel_param == Name контроллера), без самого контроллера и
    без исключённых по ключевому слову, с дедупликацией по ElementId.

    Единая точка сбора для BuildSkudSchematic / AssignSkudRooms /
    UpdateSkudSchematic — чтобы «что считается устройством контроллера»
    было определено в одном месте.
    """
    from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory
    from lowlife.scs import is_excluded_device
    from lowlife.scs_circuits import norm
    from lowlife.params import get_string_param

    equipment = FilteredElementCollector(doc) \
        .OfCategory(BuiltInCategory.OST_ElectricalEquipment) \
        .WhereElementIsNotElementType().ToElements()

    controllers = [
        e for e in equipment
        if is_controller(e, workset_param, workset_keyword, type_keyword)
    ]

    circuits = FilteredElementCollector(doc) \
        .OfCategory(BuiltInCategory.OST_ElectricalCircuit) \
        .WhereElementIsNotElementType().ToElements()

    circuits_by_name = {}
    for c in circuits:
        name = norm(get_string_param(c, circuit_panel_param))
        if name:
            circuits_by_name.setdefault(name, []).append(c)

    result = []
    for controller in controllers:
        name = norm(controller.Name)
        devices = []
        for c in circuits_by_name.get(name, []):
            try:
                raw = [x for x in c.Elements if x.Id != controller.Id]
            except:
                continue
            devices.extend([d for d in raw if not is_excluded_device(d, excluded_keywords)])

        seen = set()
        unique = []
        for d in devices:
            key = d.Id.IntegerValue
            if key in seen:
                continue
            seen.add(key)
            unique.append(d)

        result.append((controller, unique))

    return result


def hypotenuse_length_ft(pt_a, pt_b):
    """Длина по катетам (|dx| + |dy| + |dz|) между двумя точками, в футах (единицы Revit)."""
    return abs(pt_a.X - pt_b.X) + abs(pt_a.Y - pt_b.Y) + abs(pt_a.Z - pt_b.Z)


def is_near_controller(controller_pt, device_pt, threshold_ft):
    """True, если прямое 3D-расстояние между точками меньше порога (в футах)."""
    return controller_pt.DistanceTo(device_pt) < threshold_ft
