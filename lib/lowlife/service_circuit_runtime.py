# -*- coding: utf-8 -*-
from lowlife.service_circuit_graph import build_graph
from lowlife.service_circuit_adapters import CircuitRecord

def _point(el):
    loc = getattr(el, "Location", None)
    if loc is None:
        return None
    if hasattr(loc, "Point") and loc.Point is not None:
        p = loc.Point
        return (p.X, p.Y, p.Z)
    if hasattr(loc, "Curve"):
        return loc.Curve.GetEndPoint(0), loc.Curve.GetEndPoint(1)
    return None

def collect_route_curves(doc):
    from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory, LocationCurve
    curves = []
    categories = [BuiltInCategory.OST_CableTray, BuiltInCategory.OST_GenericModel]
    for category in categories:
        for el in FilteredElementCollector(doc).OfCategory(category).WhereElementIsNotElementType():
            loc = getattr(el, "Location", None)
            if not isinstance(loc, LocationCurve):
                continue
            curve = loc.Curve
            p0 = curve.GetEndPoint(0); p1 = curve.GetEndPoint(1)
            curves.append({"id": el.Id.IntegerValue, "p0": (p0.X, p0.Y, p0.Z), "p1": (p1.X, p1.Y, p1.Z), "length": curve.Length, "install": getattr(getattr(el, "Symbol", None), "Name", "")})
    return curves

def collect_electrical_circuits(doc):
    from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory
    result = []
    for circuit in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalCircuit).WhereElementIsNotElementType():
        source = getattr(circuit, "BaseEquipment", None)
        if source is None:
            continue
        devices = [el for el in circuit.Elements if el.Id != source.Id]
        result.append(CircuitRecord("GENERIC", circuit.Id.IntegerValue, source.Id.IntegerValue, [el.Id.IntegerValue for el in devices], "sequence" if len(devices) > 1 else "per_device"))
    return result

def build_document_graph(doc, tolerance=0.01):
    return build_graph(collect_route_curves(doc), tolerance)
# -*- coding: utf-8 -*-
def collect_element_points(doc):
    from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory
    points = {}
    for category in (BuiltInCategory.OST_ElectricalEquipment, BuiltInCategory.OST_CommunicationDevices, BuiltInCategory.OST_DataDevices, BuiltInCategory.OST_ElectricalFixtures):
        for el in FilteredElementCollector(doc).OfCategory(category).WhereElementIsNotElementType():
            loc = getattr(el, "Location", None)
            point = getattr(loc, "Point", None) if loc is not None else None
            if point is not None:
                points[el.Id.IntegerValue] = (point.X, point.Y, point.Z)
    return points
