# -*- coding: utf-8 -*-
"""Create a reproducible fixed-angle connection between two cable trays."""

from lowlife.i18n import tr
from lowlife import fire_boxes, tray_connection_core

from Autodesk.Revit import DB
from Autodesk.Revit.DB.Electrical import CableTray


_POINT_TOLERANCE = 1e-6


def _point(connector):
    return connector.Origin


def _horizontal_direction(connector):
    basis = connector.CoordinateSystem.BasisZ
    length = (basis.X * basis.X + basis.Y * basis.Y) ** 0.5
    if length <= _POINT_TOLERANCE:
        basis = connector.CoordinateSystem.BasisX
        length = (basis.X * basis.X + basis.Y * basis.Y) ** 0.5
    if length <= _POINT_TOLERANCE:
        return None
    return basis.X / length, basis.Y / length


def _free(connector):
    """Return whether an end connector can accept a new fitting."""
    try:
        if connector.IsConnected:
            return False
    except Exception:
        pass
    try:
        return not any(ref.Owner.Id != connector.Owner.Id for ref in connector.AllRefs)
    except Exception:
        return True


def _end_pair(first, second):
    first_ports = [c for c in fire_boxes.connectors(first) if _free(c)]
    second_ports = [c for c in fire_boxes.connectors(second) if _free(c)]
    if not first_ports or not second_ports:
        raise ValueError(tr(
            u"У выбранных лотков нет двух свободных торцевых соединений.",
            u"The selected trays do not have two free end connectors."
        ))
    pairs = [(a, b) for a in first_ports for b in second_ports]
    pairs.sort(key=lambda pair: _point(pair[0]).DistanceTo(_point(pair[1])))
    for first_port, second_port in pairs:
        if abs(_point(first_port).Z - _point(second_port).Z) > _POINT_TOLERANCE:
            return first_port, second_port
    raise ValueError(tr(
        u"Выберите лотки с концами на разных уровнях.",
        u"Select trays with ends at different elevations."
    ))


def _same_size(first, second):
    return (abs(first.Width - second.Width) <= _POINT_TOLERANCE and
            abs(first.Height - second.Height) <= _POINT_TOLERANCE)


def _level_id(tray):
    level_id = getattr(tray, "LevelId", None)
    if level_id is None:
        return DB.ElementId.InvalidElementId
    return level_id


def _type(doc, tray):
    return doc.GetElement(tray.GetTypeId())


def _create_segments(doc, source, points, end_level_id):
    element_type = _type(doc, source)
    width, height = fire_boxes.dimensions(source)
    segments = []
    point_pairs = list(zip(points[:-1], points[1:]))
    for index, (start, end) in enumerate(point_pairs):
        if start.DistanceTo(end) <= doc.Application.ShortCurveTolerance:
            raise ValueError(tr(
                u"Получился слишком короткий участок соединения.",
                u"The planned connection contains a segment that is too short."
            ))
        level_id = _level_id(source) if index == 0 else end_level_id
        segment = fire_boxes.create_curve(
            doc, element_type, None, level_id, start, end, width, height
        )
        segments.append(segment)
        if getattr(doc, "IsWorkshared", False):
            fire_boxes.assign_workset(segment, source.WorksetId)
    if not segments:
        raise ValueError(tr(
            u"Не удалось построить участок соединения.",
            u"No connection segment could be created."
        ))
    return segments


def create_connection(doc, first, second, angle_deg):
    """Create the planned tray pieces and connect every endpoint with fittings.

    The angle is measured from horizontal on the first, sloped piece.  The
    selected trays remain in place.  A horizontal tail is added when the ends
    have more plan distance than the requested slope requires.
    """
    if not isinstance(first, CableTray) or not isinstance(second, CableTray):
        raise ValueError(tr(
            u"Нужно выбрать два кабельных лотка.",
            u"Select two cable trays."
        ))
    if first.Id == second.Id:
        raise ValueError(tr(
            u"Нужно выбрать два разных лотка.",
            u"Select two different trays."
        ))
    if not _same_size(first, second):
        raise ValueError(tr(
            u"У лотков должны совпадать ширина и высота.",
            u"The trays must have the same width and height."
        ))

    first_port, second_port = _end_pair(first, second)
    start = _point(first_port)
    end = _point(second_port)
    point_values = tray_connection_core.plan_points(
        (start.X, start.Y, start.Z), (end.X, end.Y, end.Z), angle_deg,
        direction=_horizontal_direction(first_port)
    )
    points = [DB.XYZ(*values) for values in point_values]
    segments = _create_segments(doc, first, points, _level_id(second))
    doc.Regenerate()

    fire_boxes.join(doc, [first, segments[0]], points[0])
    for previous, current, point in zip(segments[:-1], segments[1:], points[1:-1]):
        fire_boxes.join(doc, [previous, current], point)
    fire_boxes.join(doc, [segments[-1], second], points[-1])
    doc.Regenerate()
    return segments
