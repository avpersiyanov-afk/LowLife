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


def _merged_crossings(crossings, length, clearance, tolerance, group_gap):
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
            "mode": crossing.get("mode", "side"),
            "perp_min": float(crossing.get("perp_min", 0.0)),
            "perp_max": float(crossing.get("perp_max", 0.0)),
            "vertical_min": crossing.get("vertical_min"),
            "vertical_max": crossing.get("vertical_max"),
        })
    prepared.sort(key=lambda item: (item["start"], item["end"]))

    merged = []
    for item in prepared:
        if (not merged or item["mode"] != merged[-1]["mode"] or
                item["start"] > merged[-1]["end"] + group_gap + tolerance):
            merged.append(item)
            continue
        current = merged[-1]
        current["end"] = max(current["end"], item["end"])
        current["perp_min"] = min(current["perp_min"], item["perp_min"])
        current["perp_max"] = max(current["perp_max"], item["perp_max"])
        if current["vertical_min"] is not None and item["vertical_min"] is not None:
            current["vertical_min"] = min(current["vertical_min"], item["vertical_min"])
        if current["vertical_max"] is not None and item["vertical_max"] is not None:
            current["vertical_max"] = max(current["vertical_max"], item["vertical_max"])
    return merged


def plan_bypass(start, end, perpendicular, crossings, tray_half_width,
                clearance, tolerance=1.0e-6, tray_half_height=None,
                group_gap=None, vertical_side=None, horizontal_side=None):
    """Return a polyline that detours around all crossing intervals."""
    axis = _sub(end, start)
    length = _length(axis)
    if length <= tolerance:
        raise ValueError("The tray axis is too short.")
    direction = _mul(axis, 1.0 / length)
    side = _unit(perpendicular)
    side = _sub(side, _mul(direction, _dot(side, direction)))
    side = _unit(side)

    if group_gap is None:
        group_gap = max(clearance * 2.0, tray_half_width * 2.0 + clearance)
    groups = _merged_crossings(crossings, length, clearance, tolerance, group_gap)
    if not groups:
        return [tuple(start), tuple(end)]

    points = [tuple(start)]
    for group in groups:
        if group["mode"] == "vertical":
            if (group["vertical_min"] is None or
                    group["vertical_max"] is None or tray_half_height is None):
                raise ValueError("Vertical crossing geometry is incomplete.")
            entry_z = start[2] + direction[2] * group["start"]
            exit_z = start[2] + direction[2] * group["end"]
            positive = max(group["vertical_max"] - entry_z,
                           group["vertical_max"] - exit_z)
            positive += tray_half_height + clearance
            negative = min(entry_z - group["vertical_min"],
                           exit_z - group["vertical_min"])
            negative += tray_half_height + clearance
            detour_vector = (0.0, 0.0, 1.0)
            if vertical_side in (-1, 1):
                offset = positive if vertical_side > 0 else -negative
            else:
                offset = positive if positive <= negative else -negative
        else:
            positive = group["perp_max"] + tray_half_width + clearance
            negative = -group["perp_min"] + tray_half_width + clearance
            detour_vector = side
            if horizontal_side in (-1, 1):
                offset = positive if horizontal_side > 0 else -negative
            else:
                offset = positive if positive <= negative else -negative

        entry = _add(start, _mul(direction, group["start"]))
        exit_ = _add(start, _mul(direction, group["end"]))
        points.extend((entry, _add(entry, _mul(detour_vector, offset)),
                       _add(exit_, _mul(detour_vector, offset)), exit_))
    points.append(tuple(end))
    return _clean_points(points, tolerance)

