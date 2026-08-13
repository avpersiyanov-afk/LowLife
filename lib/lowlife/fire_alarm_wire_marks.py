# -*- coding: utf-8 -*-
"""
Маркировка линий проводки СПС/СОУЭ номером/именем цепи.

Провод между устройствами рисуется в модели вручную (см. fire-alarm-panels.md)
линейными семействами Generic Model — тем же способом, что и трассы СКС
(lowlife.route_nodes.collect_segments). Кнопки цепей сами линии не рисуют,
только находят уже нарисованные рядом с устройствами цепи (по геометрической
близости конца линии к точке устройства/панели/изолятора) и подписывают им
параметр «Марка» номером/именем цепи.
"""

from lowlife.geometry import get_point, points_close
from lowlife.params import set_string_param
from lowlife.route_nodes import collect_segments

# Допуск «конец линии рядом с устройством», в футах (~300 мм) — провод
# рисуется вручную и не обязан попадать в точку вставки устройства день в
# день, поэтому допуск заметно шире, чем у сегментов трассы СКС.
DEVICE_MATCH_TOLERANCE_FT = 1.0


def collect_member_points(devices, extra_el=None):
    """Точки устройств цепи (+ панели/изолятора, если задан) для геопривязки линий."""
    points = [p for p in (get_point(d) for d in devices) if p is not None]
    if extra_el is not None:
        p = get_point(extra_el)
        if p is not None:
            points.append(p)
    return points


def mark_wire_lines(doc, view, member_points, label, family_filter, mark_param):
    """
    Находит на view линии проводки (Generic Model, имя семейства содержит
    family_filter), у которых хотя бы один конец лежит рядом (в пределах
    DEVICE_MATCH_TOLERANCE_FT) с одной из member_points, и пишет им в
    mark_param значение label.

    Возвращает число помеченных линий. Ничего не делает (0), если
    family_filter/mark_param не заданы в настройках или нет точек цепи.
    """
    if not family_filter or not mark_param or not member_points or view is None:
        return 0

    segments, _, _ = collect_segments(doc, view, family_filter)

    marked = 0
    for seg in segments:
        near = any(
            points_close(seg["p1"], pt, DEVICE_MATCH_TOLERANCE_FT) or
            points_close(seg["p2"], pt, DEVICE_MATCH_TOLERANCE_FT)
            for pt in member_points
        )
        if near and set_string_param(seg["element"], mark_param, label):
            marked += 1

    return marked
