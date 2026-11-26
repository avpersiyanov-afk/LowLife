# -*- coding: utf-8 -*-
"""Read electrical circuit data and calculate reserve and voltage drop."""

from __future__ import division
import re


FT_TO_M = 0.3048
COPPER_RESISTIVITY = 0.018
EXCLUDED_CATEGORIES = (u"Обобщенные модели", u"Generic Models")


def conductor_parts(label, mask=u"{mark} {section}мм²"):
    """Extract conductor mark and copper cross-section using a configurable mask."""
    text = label or u""
    match = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*(?:мм2|мм²|mm2|mm²)", text, re.I)
    section = float(match.group(1).replace(",", ".")) if match else None
    mark = text[:match.start()].strip(" -") if match else text.strip()
    return {"mark": mark, "section_mm2": section, "label": text, "mask": mask}


def voltage_drop(current_a, length_m, section_mm2, voltage_v):
    """Voltage drop for copper conductor using a two-conductor single-phase loop."""
    if not current_a or not length_m or not section_mm2 or not voltage_v:
        return {"volts": None, "percent": None}
    factor = 2.0
    volts = factor * length_m * current_a * COPPER_RESISTIVITY / section_mm2
    return {"volts": volts, "percent": 100.0 * volts / voltage_v}


def equipment_type_summary(equipment):
    """Return stable ``category / type (count)`` labels for the circuit window."""
    counts = {}
    for item in equipment or []:
        key = item.get("category", u"")
        if item.get("type"):
            key += u" / " + item["type"]
        counts[key] = counts.get(key, 0) + 1
    return u", ".join(k + u" (" + str(v) + u")" for k, v in sorted(counts.items()))


def equipment_rows(record):
    """Return plain row objects for reliable WPF binding of a selected circuit."""
    result = []
    for item in (record or {}).get("equipment", []):
        result.append(EquipmentRow(item))
    return result


class EquipmentRow(object):
    def __init__(self, item):
        self.Category = item.get("category", u"")
        self.Type = item.get("type", u"")
        self.Voltage = item.get("voltage_v")
        self.Current = item.get("current_a")
        self.Power = item.get("power_w")
        self.Name = item.get("name", u"")
        self.Id = item.get("id")


def filter_records(records, query):
    """Filter circuit records by circuit, panel, name, category, or equipment type."""
    query = (query or u"").lower()
    if not query:
        return list(records)
    result = []
    for row in records:
        text = u" ".join((row.get("number", u""), row.get("panel", u""), row.get("name", u""),
                           u" ".join(e.get("category", u"") + u" " + e.get("type", u"")
                                     for e in row.get("equipment", [])))).lower()
        if query in text:
            result.append(row)
    return result


def family_parameter_rules(text):
    result = {}
    for line in (text or u"").splitlines():
        if u"=" in line:
            family, parameter = line.split(u"=", 1)
            if family.strip() and parameter.strip():
                result[family.strip().lower()] = parameter.strip()
    return result


def _param(element, builtin, names=()):
    value = None
    if builtin is not None:
        try:
            value = element.get_Parameter(builtin)
        except Exception:
            value = None
    if value is not None:
        return value
    for name in names:
        try:
            value = element.LookupParameter(name)
        except Exception:
            value = None
        if value is not None:
            return value
    return None


def _double(param):
    if param is None:
        return None
    try:
        return param.AsDouble()
    except Exception:
        return None


def _text(param):
    if param is None:
        return u""
    try:
        return param.AsValueString() or param.AsString() or u""
    except Exception:
        return u""


def circuit_record(circuit, settings=None):
    """Return a serialisable record for one Revit ElectricalSystem."""
    settings = settings or {}
    family_rules = family_parameter_rules(settings.get("family_rules"))
    from Autodesk.Revit.DB import BuiltInParameter

    load = _double(_param(circuit, getattr(BuiltInParameter, "RBS_ELEC_APPARENT_LOAD", None),
                          (u"Полная нагрузка", u"Apparent Load")))
    voltage = _double(_param(circuit, getattr(BuiltInParameter, "RBS_ELEC_VOLTAGE", None),
                             (u"Напряжение", u"Voltage")))
    length = _double(_param(circuit, getattr(BuiltInParameter, "RBS_ELEC_CIRCUIT_LENGTH_PARAM", None),
                            (u"Длина цепи", u"Circuit Length")))
    number = _text(_param(circuit, getattr(BuiltInParameter, "RBS_ELEC_CIRCUIT_NUMBER", None),
                          (u"Номер цепи", u"Circuit Number")))
    panel = getattr(circuit, "BaseEquipment", None)
    wire = getattr(circuit, "WireType", None)
    wire_name = getattr(wire, "Name", u"") if wire is not None else u""
    ampacity = _double(_param(wire, None, (u"Допустимый ток", u"Ampacity", u"Номинальный ток"))) if wire else None
    section = settings.get("section_mm2")
    resistance = settings.get("resistance_ohm_mm2_m", 0.018)
    voltage_v = voltage
    load_va = load or 0.0
    current_a = load_va / voltage_v if voltage_v else None
    length_m = length * FT_TO_M if length is not None else None
    drop_v = None
    if current_a is not None and length_m is not None and section:
        drop_v = 2.0 * length_m * current_a * resistance / section
    reserve_a = ampacity - current_a if ampacity is not None and current_a is not None else None
    equipment = []
    for element in list(circuit.Elements) if getattr(circuit, "Elements", None) else []:
        category = getattr(getattr(element, "Category", None), "Name", u"") or u""
        type_name = u""
        try:
            type_name = element.Document.GetElement(element.GetTypeId()).Name or u""
        except Exception:
            pass
        if category in EXCLUDED_CATEGORIES:
            continue
        family_name = getattr(getattr(getattr(element, "Symbol", None), "Family", None), "Name", u"") or u""
        parameter_name = family_rules.get(family_name.lower(), settings.get("power_param", u"Мощность"))
        power = _double(_param(element, None, (parameter_name, u"Мощность", u"Power", u"Apparent Load")))
        equipment.append({"id": getattr(getattr(element, "Id", None), "IntegerValue", None), "name": getattr(element, "Name", u"") or u"", "category": category, "type": type_name, "family": family_name,
                          "voltage_v": _double(_param(element, None, (u"Напряжение", u"Voltage"))),
                          "current_a": _double(_param(element, None, (u"Ток", u"Current", u"Номинальный ток"))),
                          "power_w": power, "power_param": parameter_name})
    conductor = conductor_parts(wire_name, settings.get("conductor_mask", u"{mark} {section}мм²"))
    equipment_power = sum((item.get("power_w") or 0.0) for item in equipment)
    if equipment_power:
        load_va = equipment_power
        current_a = load_va / voltage_v if voltage_v else None
    drop = voltage_drop(current_a, length_m, conductor["section_mm2"], voltage_v)
    return {
        "id": getattr(getattr(circuit, "Id", None), "IntegerValue", None),
        "number": number,
        "name": getattr(circuit, "Name", u""),
        "panel": getattr(panel, "Name", u"") if panel else u"",
        "element_count": len(equipment),
        "equipment": equipment,
        "load_va": load_va,
        "voltage_v": voltage_v,
        "current_a": current_a,
        "length_m": length_m,
        "wire": wire_name,
        "conductor": conductor,
        "ampacity_a": ampacity,
        "reserve_a": reserve_a,
        "voltage_drop_v": drop.get("volts") if drop.get("volts") is not None else drop_v,
        "voltage_drop_pct": drop.get("percent") if drop.get("percent") is not None else ((100.0 * drop_v / voltage_v) if drop_v is not None and voltage_v else None),
    }


def summarize(records):
    return {
        "count": len(records),
        "load_va": sum((r["load_va"] or 0.0) for r in records),
        "overloaded": sum(1 for r in records if r["reserve_a"] is not None and r["reserve_a"] < 0),
        "drop_over_5": sum(1 for r in records if r["voltage_drop_pct"] is not None and r["voltage_drop_pct"] > 5.0),
    }
