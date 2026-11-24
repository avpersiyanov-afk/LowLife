# -*- coding: utf-8 -*-
"""Pure geometry for local cable-tray bypasses."""

import math


EPS = 1.0e-9


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(a, value):
    return (a[0] * value, a[1] * value, a[2] * value)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(a):
    return math.sqrt(_dot(a, a))


def _unit(a):
    length = _length(a)
    if length <= EPS:
        raise ValueError("The tray axis is too short.")
    return _mul(a, 1.0 / length)


def _clean_points(points, tolerance):
    result = []
    for point in points:
        if not result or _length(_sub(point, result[-1])) > tolerance:
            result.append(point)
    return result


def _merged_crossings(crossings, length, clearance, tolerance):
    """Merge crossing intervals that would produce touching detours."""
    prepared = []
    for crossing in crossings:
        start = max(0.0, float(crossing["start"]) - clearance)
        end = min(length, float(crossing["end"]) + clearance)
        if end - start <= tolerance:
            continue
        prepared.append({
            "start": start,
            "end": end,
            "perp_min": float(crossing.get("perp_min", 0.0)),
            "perp_max": float(crossing.get("perp_max", 0.0)),
        })
    prepared.sort(key=lambda item: (item["start"], item["end"]))

    merged = []
    for item in prepared:
        if not merged or item["start"] > merged[-1]["end"] + tolerance:
            merged.append(item)
            continue
        current = merged[-1]
        current["end"] = max(current["end"], item["end"])
        current["perp_min"] = min(current["perp_min"], item["perp_min"])
        current["perp_max"] = max(current["perp_max"], item["perp_max"])
    return merged


def plan_bypass(start, end, perpendicular, crossings, tray_half_width,
                clearance, tolerance=1.0e-6):
    """Return a polyline that detours around all crossing intervals."""
    axis = _sub(end, start)
    length = _length(axis)
    if length <= tolerance:
        raise ValueError("The tray axis is too short.")
    direction = _mul(axis, 1.0 / length)
    side = _unit(perpendicular)
    side = _sub(side, _mul(direction, _dot(side, direction)))
    side = _unit(side)

    groups = _merged_crossings(crossings, length, clearance, tolerance)
    if not groups:
        return [tuple(start), tuple(end)]

    points = [tuple(start)]
    for group in groups:
        positive = group["perp_max"] + tray_half_width + clearance
        negative = -group["perp_min"] + tray_half_width + clearance
        offset = positive if positive <= negative else -negative

        entry = _add(start, _mul(direction, group["start"]))
        exit_ = _add(start, _mul(direction, group["end"]))
        points.extend((entry, _add(entry, _mul(side, offset)),
                       _add(exit_, _mul(side, offset)), exit_))
    points.append(tuple(end))
    return _clean_points(points, tolerance)

