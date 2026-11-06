# -*- coding: utf-8 -*-
"""Parse route descriptions and total their lengths, without Revit dependencies."""
import re
from collections import OrderedDict


CODES = (
    u"ПВХгст", u"ПНДгст", u"ПВХгл", u"ПВХгт", u"ПНДгл", u"ПНДгт",
    u"ПВХст", u"ПНДл", u"ПНДт", u"ПВХл", u"ПВХт", u"ППст", u"ППл",
    u"ППт", u"ПЛЛЛ", u"ПЛЛ", u"Лоток", u"КК", u"МР", u"СТн", u"СТ",
)
PATTERN = re.compile(
    u"(" + u"|".join(re.escape(code) for code in sorted(CODES, key=len, reverse=True))
    + u")([0-9]*)-([0-9]+(?:[.,][0-9]+)?)"
)


def calculate(route_texts):
    """Sum notation lengths; tray sizes share one group. Preserve first-seen order."""
    totals = OrderedDict()
    filled = parsed = unmatched = 0
    for text in route_texts:
        text = (text or u"").strip()
        if not text:
            continue
        filled += 1
        matches = PATTERN.findall(text)
        if not matches:
            unmatched += 1
        for code, size, quantity in matches:
            key = code if code == u"Лоток" else code + size
            totals[key] = totals.get(key, 0.0) + float(quantity.replace(u",", u"."))
            parsed += 1
    result = []
    for key, value in totals.items():
        value = int(round(value)) if abs(value - round(value)) < 0.0001 else round(value, 2)
        result.append((key, value))
    return dict(result=result, chains_with_route=filled, parsed_items=parsed,
                groups_count=len(result), unmatched=unmatched)


def read_text(element, parameter_name):
    """Missing or non-text parameters do not contribute a value."""
    param = element.LookupParameter(parameter_name)
    if param is None:
        return u""
    return (param.AsString() or u"").strip()


def packages(systems, parameter_name):
    return sorted(set(value for value in
                      (read_text(system, parameter_name) for system in systems) if value))


def summarize(systems, settings, package):
    selected = [system for system in systems
                if read_text(system, settings["package_param"]) == package.strip()]
    return len(selected), [
        calculate(read_text(system, settings[key]) for system in selected)
        for key in ("route_method_reserve_param", "route_method_param")
    ]
