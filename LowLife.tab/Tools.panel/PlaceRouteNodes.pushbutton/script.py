# -*- coding: utf-8 -*-
__title__ = "Узлы трассы"
__doc__ = "Расставляет экземпляры образца в узлах и точках устройств трассы кабеля"
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

family_filter = u"Участок трассы"
cable_param_name = u"SMNX_Сегмент_Тип прокладки кабеля"
route_param_name = u"SMNX_Сегмент_Тип трассы"
route_param_value = u"Горизонтальный"
device_cable_type_value = u"Труба"

device_keywords = [u"коннектор", u"розетка", u"датчик", u"задание"]
device_exclude_keywords = [u"резервный"]

tolerance = 0.01
point_on_curve_tolerance = 0.05
merge_tolerance = 0.1

offset_param_names = [
    u"Отметка от уровня",
    u"Смещение от главной модели",
    u"SMNX_Отметка от уровня",
    "Offset"
]


def get_sample_element():
    """Образец берётся из текущего выделения в Revit"""
    selected_ids = uidoc.Selection.GetElementIds()

    if not selected_ids:
        forms.alert(
            "Сначала выберите экземпляр-образец в Revit, потом запустите кнопку.",
            exitscript=True
        )

    if len(selected_ids) > 1:
        forms.alert(
            "Выберите только один элемент-образец.",
            exitscript=True
        )

    el_id = list(selected_ids)[0]
    return doc.GetElement(el_id)


def get_point(el):
    try:
        if isinstance(el.Location, LocationPoint):
            return el.Location.Point
    except:
        pass
    return None


def get_curve_data(el):
    try:
        if isinstance(el.Location, LocationCurve):
            c = el.Location.Curve
            return c, c.GetEndPoint(0), c.GetEndPoint(1)
    except:
        pass
    try:
        bbox = el.get_BoundingBox(view)
        if bbox:
            return Line.CreateBound(bbox.Min, bbox.Max), bbox.Min, bbox.Max
    except:
        pass
    return None, None, None


def point_key(p, tol):
    return (
        int(round(p.X / tol)),
        int(round(p.Y / tol)),
        int(round(p.Z / tol))
    )


def points_close(p1, p2, tol):
    try:
        return p1.DistanceTo(p2) <= tol
    except:
        return False


def get_double_param(el, names):
    for name in names:
        try:
            p = el.LookupParameter(name)
            if p and p.HasValue and p.StorageType == StorageType.Double:
                return p.AsDouble()
        except:
            pass
    return None


def set_double_param(el, names, value):
    for name in names:
        try:
            p = el.LookupParameter(name)
            if p and not p.IsReadOnly and p.StorageType == StorageType.Double:
                p.Set(value)
        except:
            pass


def set_string_param(el, name, value):
    try:
        p = el.LookupParameter(name)
        if p and not p.IsReadOnly and p.StorageType == StorageType.String:
            p.Set(u"{}".format(value if value is not None else ""))
    except:
        pass


def detect_cable_type(el):
    names = []
    try:
        names.append((el.Symbol.Name or "").lower())
    except:
        pass
    try:
        names.append((el.Name or "").lower())
    except:
        pass
    try:
        names.append((el.Symbol.Family.Name or "").lower())
    except:
        pass

    for s in names:
        if (u"трубе" in s or u"труба" in s) and u"открыто" in s:
            return u"Труба открыто"
        if u"лотке" in s or u"лоток" in s:
            return u"Лоток"
        if u"трубе" in s or u"труба" in s:
            return u"Труба"
    return None


def is_point_on_curve(curve, pt, tol):
    try:
        proj = curve.Project(pt)
        if proj is None:
            return False, None
        p = proj.XYZPoint
        return p.DistanceTo(pt) <= tol, p
    except:
        return False, None


def sort_points(curve, points):
    try:
        p0 = curve.GetEndPoint(0)
        return sorted(points, key=lambda p: p0.DistanceTo(p))
    except:
        return points


def text_match_device(el):
    values = []
    try:
        values.append((el.Name or "").lower())
    except:
        pass
    try:
        values.append((el.Symbol.Name or "").lower())
    except:
        pass
    try:
        values.append((el.Symbol.Family.Name or "").lower())
    except:
        pass

    text = " | ".join(values)

    for word in device_exclude_keywords:
        if word in text:
            return False

    for word in device_keywords:
        if word in text:
            return True

    return False


def merge_nodes(nodes, tol):
    result = []

    for n in nodes:
        found = None
        for r in result:
            if points_close(n["point"], r["point"], tol):
                found = r
                break

        if found is None:
            result.append({
                "point": n["point"],
                "node_key": n.get("node_key"),
                "source_types": [n.get("source_type")],
                "segment_ids": list(set(n.get("segment_ids", []))),
                "device": n.get("device")
            })
        else:
            found["source_types"].append(n.get("source_type"))

            for sid in n.get("segment_ids", []):
                if sid not in found["segment_ids"]:
                    found["segment_ids"].append(sid)

            if found.get("node_key") is None and n.get("node_key") is not None:
                found["node_key"] = n.get("node_key")

            if found.get("device") is None and n.get("device") is not None:
                found["device"] = n.get("device")

    return result


# ------------------------------------------------------------
# ОСНОВНОЙ КОД
# ------------------------------------------------------------

sample = get_sample_element()
sample_point = get_point(sample)

if sample_point is None:
    forms.alert("Не удалось получить точку образца.", exitscript=True)

sample_type_id = sample.GetTypeId()

generic = FilteredElementCollector(doc, view.Id) \
    .OfCategory(BuiltInCategory.OST_GenericModel) \
    .WhereElementIsNotElementType() \
    .ToElements()

segments = []
segments_by_id = {}

for el in generic:
    try:
        fam_name = el.Symbol.Family.Name
    except:
        continue

    if family_filter not in fam_name:
        continue

    curve, p1, p2 = get_curve_data(el)
    if curve is None:
        continue

    data = {
        "element": el,
        "id": el.Id.IntegerValue,
        "curve": curve,
        "p1": p1,
        "p2": p2
    }
    segments.append(data)
    segments_by_id[data["id"]] = data

if not segments:
    forms.alert("Сегменты трассы не найдены.", exitscript=True)

all_endpoints = []
for s in segments:
    all_endpoints.append(s["p1"])
    all_endpoints.append(s["p2"])

split_points_by_segment = {}

for s in segments:
    pts = [s["p1"], s["p2"]]
    for pt in all_endpoints:
        ok, projected = is_point_on_curve(s["curve"], pt, point_on_curve_tolerance)
        if ok and projected is not None:
            exists = False
            for ex in pts:
                if ex.DistanceTo(projected) <= tolerance:
                    exists = True
                    break
            if not exists:
                pts.append(projected)

    split_points_by_segment[s["id"]] = sort_points(s["curve"], pts)

graph = {}
node_points = {}
segment_ids_by_node = {}

for s in segments:
    pts = split_points_by_segment[s["id"]]
    for i in range(len(pts) - 1):
        a = pts[i]
        b = pts[i + 1]

        if a.DistanceTo(b) <= tolerance:
            continue

        k1 = point_key(a, tolerance)
        k2 = point_key(b, tolerance)

        node_points[k1] = a
        node_points[k2] = b

        if k1 not in graph:
            graph[k1] = []
        if k2 not in graph:
            graph[k2] = []

        if k2 not in graph[k1]:
            graph[k1].append(k2)
        if k1 not in graph[k2]:
            graph[k2].append(k1)

        if k1 not in segment_ids_by_node:
            segment_ids_by_node[k1] = set()
        if k2 not in segment_ids_by_node:
            segment_ids_by_node[k2] = set()

        segment_ids_by_node[k1].add(s["id"])
        segment_ids_by_node[k2].add(s["id"])

device_categories = [
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_DataDevices
]

all_devices = []

for cat in device_categories:
    all_devices.extend(
        FilteredElementCollector(doc, view.Id)
        .OfCategory(cat)
        .WhereElementIsNotElementType()
        .ToElements()
    )

devices = []

for el in all_devices:
    if not text_match_device(el):
        continue

    pt = get_point(el)
    if pt is None:
        continue

    nearest_key = None
    nearest_dist = None

    for k, p in node_points.items():
        try:
            d = pt.DistanceTo(p)
            if nearest_dist is None or d < nearest_dist:
                nearest_dist = d
                nearest_key = k
        except:
            pass

    devices.append({
        "element": el,
        "point": pt,
        "node_key": nearest_key
    })

raw_nodes = []

for nk, neighbors in graph.items():
    if len(neighbors) >= 2:
        raw_nodes.append({
            "point": node_points[nk],
            "node_key": nk,
            "source_type": "graph_node",
            "segment_ids": list(segment_ids_by_node.get(nk, []))
        })

for d in devices:
    raw_nodes.append({
        "point": d["point"],
        "node_key": d["node_key"],
        "source_type": "device_point",
        "segment_ids": list(segment_ids_by_node.get(d["node_key"], [])) if d["node_key"] in segment_ids_by_node else [],
        "device": d
    })

insert_nodes = merge_nodes(raw_nodes, merge_tolerance)

existing_by_key = {}
for el in generic:
    try:
        if el.GetTypeId() == sample_type_id:
            pt = get_point(el)
            if pt is not None:
                existing_by_key[point_key(pt, merge_tolerance)] = el
    except:
        pass

actions = []
for n in insert_nodes:
    k = point_key(n["point"], merge_tolerance)
    if k in existing_by_key:
        actions.append(("update", n, existing_by_key[k]))
    else:
        actions.append(("create", n, None))

created = []
updated = []

with revit.Transaction("Place Route Nodes"):

    for action, node, existing in actions:
        point = node["point"]
        line_offset_value = None
        cable_type_value = None

        device = node.get("device")
        source_types = node.get("source_types", [])
        is_device = device is not None and "device_point" in source_types

        if is_device:
            cable_type_value = device_cable_type_value
            dev_el = device.get("element")
            if dev_el is not None:
                line_offset_value = get_double_param(dev_el, offset_param_names)

        for sid in node.get("segment_ids", []):
            if sid not in segments_by_id:
                continue

            seg_el = segments_by_id[sid]["element"]

            if line_offset_value is None:
                line_offset_value = get_double_param(seg_el, offset_param_names)

            if not is_device and cable_type_value is None:
                cable_type_value = detect_cable_type(seg_el)

            if line_offset_value is not None and cable_type_value is not None:
                break

        if action == "create":
            vector = XYZ(point.X - sample_point.X, point.Y - sample_point.Y, 0)
            new_ids = ElementTransformUtils.CopyElement(doc, sample.Id, vector)
            el = doc.GetElement(new_ids[0]) if new_ids else None

            if el:
                if line_offset_value is not None:
                    set_double_param(el, offset_param_names, line_offset_value)

                if cable_type_value is not None:
                    set_string_param(el, cable_param_name, cable_type_value)

                set_string_param(el, route_param_name, route_param_value)
                created.append(el)

        else:
            el = existing

            if line_offset_value is not None:
                set_double_param(el, offset_param_names, line_offset_value)

            if cable_type_value is not None:
                set_string_param(el, cable_param_name, cable_type_value)

            set_string_param(el, route_param_name, route_param_value)
            updated.append(el)


forms.alert(
    "Готово.\n\n"
    "Создано элементов: {}\n"
    "Обновлено элементов: {}\n"
    "Всего узлов: {}".format(
        len(created),
        len(updated),
        len(insert_nodes)
    )
)
