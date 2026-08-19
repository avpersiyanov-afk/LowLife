# -*- coding: utf-8 -*-
"""
Перенос имени и номера помещения из связанной модели в параметр элемента
активного документа.

Для каждого элемента ищется точка (точка вставки, середина кривой для
line-based элементов, либо центр bounding box), затем среди ВСЕХ
подключённых связей ищется Room, в который попадает эта точка, и в целевой
параметр элемента записывается "Имя (Номер)" (или только то, что удалось
найти).

Имена параметров (куда писать результат, из какого параметра связанного
Room брать номер) — соглашения конкретного проекта, поэтому не зашиты
здесь, а приходят из room_info_settings.py.
"""

from Autodesk.Revit.DB import RevitLinkInstance, FilteredElementCollector, BuiltInCategory, BuiltInParameter, LocationCurve

from lowlife.geometry import get_point as get_location_point
from lowlife.params import set_param_any, get_string_param


def get_point(el):
    """
    Точка для поиска помещения. Шире, чем geometry.get_point (только
    LocationPoint) — кнопка должна работать с произвольными категориями
    элементов, поэтому дополнительно берёт середину кривой (line-based
    элементы) и центр bounding box как последний резерв.
    """
    p = get_location_point(el)
    if p is not None:
        return p

    try:
        loc = el.Location
        if isinstance(loc, LocationCurve):
            return loc.Curve.Evaluate(0.5, True)
    except:
        pass

    try:
        bbox = el.get_BoundingBox(None)
        if bbox:
            return (bbox.Min + bbox.Max) / 2
    except:
        pass

    return None


def find_room_info(doc, point, room_number_param_name):
    """
    Ищет Room, в который попадает point, во всех RevitLinkInstance
    активного документа. Возвращает (имя, номер) первого найденного
    помещения — имя берётся из нативного BuiltInParameter.ROOM_NAME,
    номер — из room_number_param_name (общий параметр, специфичный для
    проекта). Любое из двух может быть None, если не заполнено/не найдено.
    """
    if point is None:
        return None, None

    link_instances = FilteredElementCollector(doc).OfClass(RevitLinkInstance).ToElements()

    for link in link_instances:
        linked_doc = link.GetLinkDocument()
        if linked_doc is None:
            continue

        rooms = FilteredElementCollector(linked_doc) \
            .OfCategory(BuiltInCategory.OST_Rooms) \
            .WhereElementIsNotElementType() \
            .ToElements()

        for room in rooms:
            try:
                in_room = room.IsPointInRoom(point)
            except:
                in_room = False

            if not in_room:
                continue

            name_param = room.get_Parameter(BuiltInParameter.ROOM_NAME)
            room_name = name_param.AsString() if name_param and name_param.HasValue else None

            room_number = get_string_param(room, room_number_param_name) if room_number_param_name else None

            return room_name, room_number

    return None, None


def format_room_value(room_name, room_number):
    """"Имя (Номер)" — либо то, что удалось найти по отдельности, либо пустая строка."""
    if room_name and room_number:
        return u"{} ({})".format(room_name, room_number)
    if room_name:
        return room_name
    if room_number:
        return u"({})".format(room_number)
    return u""


def apply_room_info(doc, elements, target_param_name, room_number_param_name):
    """
    Для каждого элемента ищет связанное помещение и пишет результат в
    target_param_name. Возвращает список (element, status, value), где
    status — "written"/"not_found"/"no_point"/"no_param"/"write_error".
    Транзакцию открывает вызывающий скрипт кнопки.
    """
    results = []

    for el in elements:
        if el is None:
            continue

        point = get_point(el)
        if point is None:
            results.append((el, "no_point", u""))
            continue

        room_name, room_number = find_room_info(doc, point, room_number_param_name)
        value = format_room_value(room_name, room_number)

        if not value:
            results.append((el, "not_found", u""))
            continue

        if el.LookupParameter(target_param_name) is None:
            results.append((el, "no_param", value))
            continue

        ok = set_param_any(el, target_param_name, value)
        results.append((el, "written" if ok else "write_error", value))

    return results
