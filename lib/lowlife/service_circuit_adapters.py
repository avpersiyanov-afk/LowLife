# -*- coding: utf-8 -*-
try:
    unicode
except NameError:
    unicode = str
ALIASES = {u"СКС":"SCS",u"SCS":"SCS",u"СКУД":"SKUD",u"SKUD":"SKUD",u"СПС":"SPS",u"SPS":"SPS",u"СОУЭ":"SOUE",u"SOUE":"SOUE"}
def normalize_system_kind(value):
    value = unicode(value or u"").strip().upper()
    return ALIASES.get(value, value)
def sequence_mode(system_kind):
    return normalize_system_kind(system_kind) in ("SPS", "SOUE")
def collect_element_points(doc):
    from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory, LocationCurve
    def xyz(point):
        return (float(point.X), float(point.Y), float(point.Z)) if point is not None else None
    def connector_point(element):
        managers = []
        mep = getattr(element, "MEPModel", None)
        if mep is not None and getattr(mep, "ConnectorManager", None) is not None:
            managers.append(mep.ConnectorManager)
        if getattr(element, "ConnectorManager", None) is not None:
            managers.append(element.ConnectorManager)
        for manager in managers:
            connectors = getattr(manager, "Connectors", None)
            if connectors is not None:
                for connector in connectors:
                    point = xyz(getattr(connector, "Origin", None))
                    if point is not None:
                        return point
        return None
    categories = []
    for name in ("OST_ElectricalEquipment", "OST_CommunicationDevices", "OST_DataDevices", "OST_ElectricalFixtures", "OST_FireAlarmDevices", "OST_SecurityDevices", "OST_NurseCallDevices", "OST_GenericModel"):
        category = getattr(BuiltInCategory, name, None)
        if category is not None:
            categories.append(category)
    points = {}
    for category in categories:
        for element in FilteredElementCollector(doc).OfCategory(category).WhereElementIsNotElementType():
            location = getattr(element, "Location", None)
            point = xyz(getattr(location, "Point", None)) if location is not None else None
            if point is None and isinstance(location, LocationCurve):
                point = xyz(location.Curve.Evaluate(0.5, True))
            if point is None:
                point = connector_point(element)
            if point is not None:
                points[element.Id.IntegerValue] = point
    return points

def element_point(element):
    """Return a usable connection point for any Revit family instance."""
    location = getattr(element, "Location", None)
    point = getattr(location, "Point", None) if location is not None else None
    if point is None and location is not None and hasattr(location, "Curve"):
        point = location.Curve.Evaluate(0.5, True)
    if point is None:
        mep = getattr(element, "MEPModel", None)
        manager = getattr(mep, "ConnectorManager", None) if mep is not None else getattr(element, "ConnectorManager", None)
        connectors = getattr(manager, "Connectors", None) if manager is not None else None
        if connectors is not None:
            for connector in connectors:
                point = getattr(connector, "Origin", None)
                if point is not None:
                    break
    return (float(point.X), float(point.Y), float(point.Z)) if point is not None else None
class CircuitRecord(object):
    def __init__(self, system_kind, circuit_id, source_id, device_ids, route_mode="per_device", ring=False):
        self.system_kind=normalize_system_kind(system_kind); self.circuit_id=circuit_id; self.source_id=source_id; self.device_ids=list(device_ids or []); self.route_mode=route_mode; self.ring=bool(ring)
def adapt_revit_circuits(doc, system_kind="SCS"):
    from lowlife.service_circuit_runtime import collect_electrical_circuits
    requested=normalize_system_kind(system_kind); records=[]
    for record in collect_electrical_circuits(doc):
        record.system_kind=requested
        record.route_mode="sequence" if sequence_mode(requested) else ("per_device" if len(record.device_ids)>1 else record.route_mode)
        records.append(record)
    return records
def route_points_for_circuit(doc, circuit, point_by_id):
    return point_by_id.get(circuit.source_id), [point_by_id[i] for i in circuit.device_ids if i in point_by_id]
