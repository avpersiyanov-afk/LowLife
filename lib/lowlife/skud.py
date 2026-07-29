# -*- coding: utf-8 -*-
"""
Общие константы и логика для инструментов СКУД (контроль доступа).

Значения по умолчанию НЕ заданы намеренно — см. scs.py: имена
семейств/параметров вводятся в окне настроек (skud_settings.py) и
сохраняются в %APPDATA%\\pyRevit\\LowLifeSKUD_settings.json.
"""

from lowlife.scs import classify_element, get_workset_name


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


def parse_device_cable_map(text):
    """
    "урд:КабельА, считыватель:КабельБ\nзамок:КабельВ" ->
    [(u"урд", u"КабельА"), (u"считыватель", u"КабельБ"), (u"замок", u"КабельВ")].

    Разделитель строк — запятая и/или перенос строки; ключ и значение
    разделяются первым двоеточием. Порядок сохраняется — важен для
    приоритета первого совпадения в pick_cable_type (как classify_element).
    """
    pairs = []
    if not text:
        return pairs

    raw_items = text.replace(u"\r\n", u"\n").replace(u"\n", u",").split(u",")

    for item in raw_items:
        item = item.strip()
        if not item or u":" not in item:
            continue
        keyword, _, value = item.partition(u":")
        keyword = keyword.strip()
        value = value.strip()
        if keyword and value:
            pairs.append((keyword, value))

    return pairs


def pick_cable_type(device_el, cable_map_pairs):
    """
    Тип кабеля для устройства по первому совпавшему ключевому слову
    в имени семейства/типа устройства (тот же паттерн, что
    scs.detect_cable_type, но словарь конфигурируется пользователем).
    """
    categories = [(value, [keyword], []) for keyword, value in cable_map_pairs]
    return classify_element(device_el, categories)


def parse_device_categories(text):
    """
    "считыватель:считыватель,card reader\nзамок:замок,урд" ->
    [(u"считыватель", [u"считыватель", u"card reader"], []),
     (u"замок", [u"замок", u"урд"], [])]
    — формат, ожидаемый scs.classify_element (categories argument).
    """
    categories = []
    if not text:
        return categories

    raw_items = text.replace(u"\r\n", u"\n").split(u"\n")

    for item in raw_items:
        item = item.strip()
        if not item or u":" not in item:
            continue
        name, _, keywords_text = item.partition(u":")
        name = name.strip()
        keywords = [k.strip() for k in keywords_text.split(u",") if k.strip()]
        if name and keywords:
            categories.append((name, keywords, []))

    return categories


def hypotenuse_length_ft(pt_a, pt_b):
    """Длина по катетам (|dx| + |dy| + |dz|) между двумя точками, в футах (единицы Revit)."""
    return abs(pt_a.X - pt_b.X) + abs(pt_a.Y - pt_b.Y) + abs(pt_a.Z - pt_b.Z)


def is_near_controller(controller_pt, device_pt, threshold_ft):
    """True, если прямое 3D-расстояние между точками меньше порога (в футах)."""
    return controller_pt.DistanceTo(device_pt) < threshold_ft
