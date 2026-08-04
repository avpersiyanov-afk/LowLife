# -*- coding: utf-8 -*-
"""
Общие константы и логика для инструментов СКУД (контроль доступа).

Значения по умолчанию НЕ заданы намеренно — см. scs.py: имена
семейств/параметров вводятся в окне настроек (skud_settings.py) и
сохраняются в %APPDATA%\\pyRevit\\LowLifeSKUD_settings.json.
"""

from lowlife.scs import get_workset_name


CONTROLLER_WORKSET_KEYWORD = u""
CONTROLLER_TYPE_KEYWORD = u""


def is_controller(el, workset_param_name, workset_keyword, type_keyword):
    """Контроллер — рабочий набор содержит workset_keyword И имя типа содержит type_keyword."""
    ws = get_workset_name(el, workset_param_name)
    if not ws or workset_keyword.lower() not in ws.lower():
        return False

    try:
        type_name = el.Symbol.Name or u""
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


def hypotenuse_length_ft(pt_a, pt_b):
    """Длина по катетам (|dx| + |dy| + |dz|) между двумя точками, в футах (единицы Revit)."""
    return abs(pt_a.X - pt_b.X) + abs(pt_a.Y - pt_b.Y) + abs(pt_a.Z - pt_b.Z)


def is_near_controller(controller_pt, device_pt, threshold_ft):
    """True, если прямое 3D-расстояние между точками меньше порога (в футах)."""
    return controller_pt.DistanceTo(device_pt) < threshold_ft
