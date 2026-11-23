# -*- coding: utf-8 -*-
"""Geometry planning for the fixed-angle cable-tray connection button.

The Revit adapter creates the planned straight pieces and native fittings.  Keeping
the point calculation here makes the geometric contract testable without Revit.
Angles are measured from the horizontal projection of the sloped piece.
"""

import math


MIN_ANGLE_DEG = 2.0
MAX_ANGLE_DEG = 88.0
GEOMETRY_TOLERANCE = 1e-9


def _number(value):
    return float(value)


def horizontal_distance(a, b):
    return math.hypot(_number(b[0]) - _number(a[0]),
                      _number(b[1]) - _number(a[1]))


def plan_points(start, end, angle_deg, direction=None, tolerance=GEOMETRY_TOLERANCE):
    """Return the points for a fixed-angle connection path.

    The first segment rises or drops at ``angle_deg``.  If the selected ends
    have additional horizontal separation, the remaining segment is horizontal
    at the elevation of ``end``.  A two-item result means one sloped segment is
    sufficient.  A three-item result contains the intermediate elbow point.

    ``ValueError`` is raised when the ends are on the same level, the requested
    angle is outside the range supported by the command, or the requested
    slope cannot reach the second end without moving an existing tray.
    """
    a = tuple(_number(v) for v in start)
    b = tuple(_number(v) for v in end)
    angle = _number(angle_deg)
    if not MIN_ANGLE_DEG <= angle <= MAX_ANGLE_DEG:
        raise ValueError("angle must be between {} and {} degrees".format(
            MIN_ANGLE_DEG, MAX_ANGLE_DEG))

    dz = b[2] - a[2]
    if abs(dz) <= tolerance:
        raise ValueError("tray ends must have different elevations")

    run = abs(dz) / math.tan(math.radians(angle))
    distance = horizontal_distance(a, b)
    if distance <= tolerance:
        if direction is None:
            raise ValueError("a vertical offset needs horizontal space for this angle")
        direction = (_number(direction[0]), _number(direction[1]))
        direction_length = math.hypot(direction[0], direction[1])
        if direction_length <= tolerance:
            raise ValueError("connection direction is undefined")
        ux, uy = direction[0] / direction_length, direction[1] / direction_length
        middle = (a[0] + ux * run, a[1] + uy * run, b[2])
        return (a, middle, b)

    if distance + tolerance < run:
        raise ValueError("the selected ends are too close for this angle")

    if abs(distance - run) <= tolerance:
        return (a, b)

    ux = (b[0] - a[0]) / distance
    uy = (b[1] - a[1]) / distance
    middle = (a[0] + ux * run, a[1] + uy * run, b[2])
    return (a, middle, b)


def slope_angle_deg(start, end):
    """Return the absolute angle of a 3D segment from the horizontal."""
    distance = horizontal_distance(start, end)
    if distance <= GEOMETRY_TOLERANCE:
        return 90.0 if abs(_number(end[2]) - _number(start[2])) > GEOMETRY_TOLERANCE else 0.0
    return math.degrees(math.atan2(abs(_number(end[2]) - _number(start[2])), distance))


def parse_angle(text):
    """Parse the degrees entered in the command dialog."""
    if text is None:
        raise ValueError("angle was cancelled")
    value = str(text).strip().replace(",", ".")
    if not value:
        raise ValueError("angle is empty")
    try:
        angle = float(value)
    except (TypeError, ValueError):
        raise ValueError("angle is not a number")
    if not MIN_ANGLE_DEG <= angle <= MAX_ANGLE_DEG:
        raise ValueError("angle must be between {} and {} degrees".format(
            MIN_ANGLE_DEG, MAX_ANGLE_DEG))
    return angle
