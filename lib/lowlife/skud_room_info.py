# -*- coding: utf-8 -*-
"""
Имя помещения для устройств СКУД — надстройка над room_info.py.

Отличие от кнопки «Помещение из связи» (её используют СПС и СОТ): элементы
одной точки прохода (считыватель, замок, кнопка выхода, геркон, доводчик)
физически стоят в разных помещениях — считыватель снаружи, замок в
дверном проёме и т.д. Поэтому по каждой точке прохода берётся ОДНО
значение — самое частое среди её устройств — и назначается всем
устройствам этой точки прохода. Так у всей точки прохода в спецификации
одно помещение.

Имена параметров (куда писать, из какого параметра Room связи брать
номер) — общие с СПС/СОТ, берутся из room_info_settings, здесь не
дублируются.
"""

from lowlife.room_info import get_point, find_room_info, format_room_value
# majority_value живёт в skud_schematic (чистая функция, тестируется вне Revit).
from lowlife.skud_schematic import majority_value  # noqa: F401 (реэкспорт)


def device_room_value(doc, el, room_number_param):
    """"Имя (Номер)" для одного элемента по связям, либо "" если не нашлось."""
    name, number = find_room_info(doc, get_point(el), room_number_param)
    return format_room_value(name, number)


def assign_rooms_by_passage_point(doc, passage_points, target_param, room_number_param):
    """
    passage_points — список списков устройств (по одному списку на точку
    прохода). Для каждой точки прохода: значение помещения по каждому
    устройству, выбор самого частого непустого (majority_value), запись
    его ВСЕМ устройствам точки прохода в target_param.

    Транзакцию открывает вызывающий скрипт. Возвращает список кортежей
    (passage_point_index, value, written_count, status), где status —
    "written" / "no_room" (ни у одного устройства не нашлось помещения) /
    "no_devices".
    """
    from lowlife.params import set_param_any

    results = []

    for idx, devices in enumerate(passage_points):
        if not devices:
            results.append((idx, u"", 0, "no_devices"))
            continue

        per_device = [device_room_value(doc, d, room_number_param) for d in devices]
        value = majority_value(per_device)

        if not value:
            results.append((idx, u"", 0, "no_room"))
            continue

        written = 0
        for d in devices:
            if d.LookupParameter(target_param) is None:
                continue
            if set_param_any(d, target_param, value):
                written += 1

        results.append((idx, value, written, "written"))

    return results
