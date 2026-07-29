# -*- coding: utf-8 -*-
"""
Логика кнопки BuildSkudSchematic ("Структурная схема СКУД"):
размножение типовой группы-эталона по числу контроллеров, сопоставление
схемных семейств внутри копии группы с реальными устройствами контроллера
по категории/типу, копирование адреса.

Работает с Revit Group API — не чистые dict-структуры, в отличие от
scs_addressing/scs_circuits, т.к. размещение/поиск элементов группы
неотделимо от Revit API.
"""

from lowlife.geometry import get_point


def find_template_group_type(doc, group_name):
    """GroupType с именем group_name (первое совпадение), или None."""
    from Autodesk.Revit.DB import FilteredElementCollector, GroupType

    for gt in FilteredElementCollector(doc).OfClass(GroupType):
        try:
            if gt.Name == group_name:
                return gt
        except:
            continue

    return None


def group_member_elements(doc, group_instance):
    """Элементы (не ElementId) — члены группы."""
    result = []
    for eid in group_instance.GetMemberIds():
        el = doc.GetElement(eid)
        if el is not None:
            result.append(el)
    return result


def device_category_key(el, category_rules):
    """
    Категория схемного/реального устройства по правилам classify_element
    (category_rules — тот же формат, что categories в scs.classify_element:
    список (name, keywords, exclude_keywords)).
    """
    from lowlife.scs import classify_element
    return classify_element(el, category_rules)


def group_bounding_width(doc, group_type):
    """
    Примерная ширина типовой группы по X (для шага автораскладки) —
    диагональ bounding box первого попавшегося экземпляра типа, если он
    уже есть в проекте; иначе None (вызывающий код использует запасной
    отступ из настроек).
    """
    from Autodesk.Revit.DB import FilteredElementCollector, Group

    for g in FilteredElementCollector(doc).OfClass(Group):
        try:
            if g.GroupType.Id == group_type.Id:
                bbox = g.get_BoundingBox(None)
                if bbox:
                    return bbox.Max.X - bbox.Min.X
        except:
            continue

    return None


def layout_points(base_point, count, gap_ft, per_row):
    """
    Точки вставки для count копий группы, рядами по per_row штук,
    начиная от base_point, с шагом gap_ft по X (внутри ряда) и по Y
    (между рядами, вниз).
    """
    from Autodesk.Revit.DB import XYZ

    points = []
    for i in range(count):
        row = i // per_row
        col = i % per_row
        points.append(XYZ(
            base_point.X + col * gap_ft,
            base_point.Y - row * gap_ft,
            base_point.Z
        ))
    return points


def match_devices_by_category(template_members, real_devices, category_rules):
    """
    Сопоставляет схемные семейства (template_members, элементы копии
    типовой группы) с реальными устройствами контроллера (real_devices) по
    категории (считыватель<->считыватель, замок<->замок и т.п.).

    В пределах одной категории — по порядку (оба списка предварительно
    сортируются вызывающим кодом одинаковым образом, например по адресу).
    Возвращает список пар (schematic_el, real_el); устройства, для которых
    не нашлось схемного аналога (или наоборот), не включаются — вызывающий
    код должен отдельно посчитать и отчитаться о таких "лишних" элементах.
    """
    template_by_category = {}
    for el in template_members:
        cat = device_category_key(el, category_rules)
        if cat:
            template_by_category.setdefault(cat, []).append(el)

    real_by_category = {}
    for el in real_devices:
        cat = device_category_key(el, category_rules)
        if cat:
            real_by_category.setdefault(cat, []).append(el)

    pairs = []
    unmatched_real = []

    for cat, real_list in real_by_category.items():
        template_list = template_by_category.get(cat, [])
        for i, real_el in enumerate(real_list):
            if i < len(template_list):
                pairs.append((template_list[i], real_el))
            else:
                unmatched_real.append(real_el)

    return pairs, unmatched_real
