# -*- coding: utf-8 -*-
def shaft_matches_type(type_name, keywords):
    value = (type_name or u"").upper()
    return any(k and k.upper() in value for k in keywords)

def direction_for_path(path, levels):
    values = [levels[n] for n in path if n in levels]
    if len(values) < 2:
        return "unknown"
    up = any(values[i+1] > values[i] for i in range(len(values)-1))
    down = any(values[i+1] < values[i] for i in range(len(values)-1))
    if up and down:
        return "up/down"
    if up:
        return "up"
    if down:
        return "down"
    return "same"

def shaft_bbox_contains_xy(bbox, point, tolerance=0.0):
    x, y = point
    return (bbox["min_x"] - tolerance <= x <= bbox["max_x"] + tolerance and
            bbox["min_y"] - tolerance <= y <= bbox["max_y"] + tolerance)
