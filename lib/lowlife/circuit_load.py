# -*- coding: utf-8 -*-
"""Read electrical circuit data and calculate reserve and voltage drop."""

from __future__ import division


FT_TO_M = 0.3048


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
    voltage_v = voltage or settings.get("voltage_v", 230.0)
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
        equipment.append({"id": getattr(getattr(element, "Id", None), "IntegerValue", None), "name": getattr(element, "Name", u"") or u"", "category": category, "type": type_name})
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
        "ampacity_a": ampacity,
        "reserve_a": reserve_a,
        "voltage_drop_v": drop_v,
        "voltage_drop_pct": (100.0 * drop_v / voltage_v) if drop_v is not None and voltage_v else None,
    }


def summarize(records):
    return {
        "count": len(records),
        "load_va": sum((r["load_va"] or 0.0) for r in records),
        "overloaded": sum(1 for r in records if r["reserve_a"] is not None and r["reserve_a"] < 0),
        "drop_over_5": sum(1 for r in records if r["voltage_drop_pct"] is not None and r["voltage_drop_pct"] > 5.0),
    }
