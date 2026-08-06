# -*- coding: utf-8 -*-
"""
Общая логика панели CableSchedule (журнал кабельных цепей):
настройки плагина, хранение проложенного маршрута цепи (ExtensibleStorage),
алгоритм Дейкстры для прокладки кабеля по трассе и общие Revit-хелперы.

Перенесено с C#-плагина CableSchedule (Inno Setup инсталлятор,
namespace СableSchedule) на pyRevit. Логика 1:1, за вычетом того,
что специфично для WPF/Revit .addin (регистрация ленты, окно
настроек) — это остаётся в script.py каждой кнопки.
"""

import os
import io
import json

from Autodesk.Revit.DB import (
    ElementId, BuiltInCategory, BuiltInParameter, UnitUtils, UnitTypeId, SpecTypeId,
    FilteredElementCollector, Level, XYZ, Line, HermiteSpline,
    LocationPoint, LocationCurve, MEPCurve,
)
from Autodesk.Revit.DB.Electrical import CableTray, Conduit
from Autodesk.Revit.DB.Plumbing import FlexPipe
from Autodesk.Revit.DB.ExtensibleStorage import Schema, SchemaBuilder, Entity, AccessLevel
from Autodesk.Revit.UI.Selection import ISelectionFilter

from System import Guid
from System.Collections.Generic import IList


# ------------------------------------------------------------
# НАСТРОЙКИ ПЛАГИНА
# ------------------------------------------------------------

SETTINGS_FILE_NAME = "LowLifeCableSchedule_settings.json"

DEFAULT_CABLE_MARK_PARAMETER = u"ITV_CRC_Тип кабеля"


def _settings_file_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(appdata, "pyRevit")

    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except:
            pass

    return os.path.join(folder, SETTINGS_FILE_NAME)


def load_settings():
    """Строковые настройки плагина: из JSON-файла, иначе — значения по умолчанию."""
    path = _settings_file_path()
    values = {"cable_mark_parameter": DEFAULT_CABLE_MARK_PARAMETER}

    if os.path.isfile(path):
        try:
            with io.open(path, "r", encoding="utf-8") as f:
                text = f.read()
            if text.strip():
                values.update(json.loads(text))
        except:
            pass

    return values


def save_settings(values):
    path = _settings_file_path()
    try:
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(unicode(json.dumps(values, ensure_ascii=False, indent=2, sort_keys=True)))
    except:
        pass


# ------------------------------------------------------------
# ОБЩИЕ REVIT-ХЕЛПЕРЫ
# ------------------------------------------------------------

def to_millimeters(internal_value):
    return UnitUtils.ConvertFromInternalUnits(internal_value, UnitTypeId.Millimeters)


def to_meters(internal_value):
    return UnitUtils.ConvertFromInternalUnits(internal_value, UnitTypeId.Meters)


def get_category_id(elem):
    """BuiltInCategory-совместимый int категории элемента, или None."""
    try:
        if elem is None or elem.Category is None:
            return None
        return elem.Category.Id.IntegerValue
    except:
        return None


class ElectricalEquipmentSelectionFilter(ISelectionFilter):
    """
    Фильтр выбора: только категория «Электрооборудование», не из связанного файла.
    Используется всеми кнопками, где пользователь выбирает приборы/панели.
    """

    def AllowElement(self, elem):
        if get_category_id(elem) == int(BuiltInCategory.OST_ElectricalEquipment):
            return not elem.Document.IsLinked
        return False

    def AllowReference(self, reference, position):
        return True


def get_mark(elem):
    """BuiltInParameter.ALL_MODEL_MARK элемента, либо его имя, либо '?'."""
    if elem is None:
        return u"?"
    try:
        p = elem.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if p is not None:
            v = p.AsString()
            if v:
                return v
    except:
        pass
    try:
        return elem.Name or u"?"
    except:
        return u"?"


def get_sorted_loads(circuit):
    """
    Нагрузки электрической цепи (все элементы кроме базового оборудования),
    отсортированные по Id коннектора панели — порядок подключения.
    Возвращает список (Element) в порядке возрастания Connector.Id.
    """
    result = {}
    base_id = circuit.BaseEquipment.Id if circuit.BaseEquipment else None

    for connector in circuit.ConnectorManager.Connectors:
        for ref in connector.AllRefs:
            if base_id is not None and ref.Owner.Id != base_id:
                result[connector.Id] = ref.Owner

    return [result[k] for k in sorted(result.keys())]


# ------------------------------------------------------------
# ХРАНЕНИЕ МАРШРУТА ЦЕПИ (ExtensibleStorage)
# ------------------------------------------------------------

SCHEMA_NAME = "CableScheduleCircuitStorage"
_APP_GUID = Guid("c4e2a8f1-5b3d-4e9a-a6f0-1c8d2e4a7b6c")


def _find_schema():
    for schema in Schema.ListSchemas():
        if schema.SchemaName == SCHEMA_NAME:
            return schema
    return None


def _get_or_create_schema():
    schema = _find_schema()
    if schema is not None:
        return schema

    guid = Guid.NewGuid()
    existing_guids = set(str(s.GUID) for s in Schema.ListSchemas())
    while str(guid) in existing_guids:
        guid = Guid.NewGuid()

    builder = SchemaBuilder(guid)
    builder.SetReadAccessLevel(AccessLevel.Public)
    builder.SetWriteAccessLevel(AccessLevel.Public)
    builder.SetApplicationGUID(_APP_GUID)
    builder.SetVendorId("CableSchedule")

    builder.AddSimpleField("lengthCircuit", float).SetSpec(SpecTypeId.Length)
    builder.AddArrayField("itemInCircuitElement", ElementId)
    builder.AddArrayField("itemInCircuitHash", int)
    builder.AddArrayField("itemInCircuitOrigin", XYZ).SetSpec(SpecTypeId.Length)
    builder.AddArrayField("wayItemInCircuitElement", ElementId)
    builder.AddArrayField("wayItemInCircuitHash", int)
    builder.AddArrayField("wayItemInCircuitOrigin", XYZ).SetSpec(SpecTypeId.Length)
    builder.AddArrayField("segmentWayElement", ElementId)
    builder.AddArrayField("segmentWayLength", float).SetSpec(SpecTypeId.Length)
    builder.SetSchemaName(SCHEMA_NAME)

    return builder.Finish()


def get_route_entity(circuit):
    """Сохранённые данные маршрута цепи (Entity), либо None если ещё не прокладывали."""
    for schema_guid in circuit.GetEntitySchemaGuids():
        schema = Schema.Lookup(schema_guid)
        if schema is not None and schema.SchemaName == SCHEMA_NAME:
            entity = circuit.GetEntity(schema)
            if entity.IsValid():
                return entity
    return None


def save_route_metadata(doc, circuit, dijkstra):
    """Сохраняет результат Dijkstra.get_path() в ExtensibleStorage цепи."""
    schema = _get_or_create_schema()
    entity = Entity(schema)

    entity.Set[float](schema.GetField("lengthCircuit"), to_millimeters(circuit.Length), UnitTypeId.Millimeters)
    entity.Set[IList[ElementId]](schema.GetField("itemInCircuitElement"), list(dijkstra.item_in_circuit.keys()))
    entity.Set[IList[int]](schema.GetField("itemInCircuitHash"), list(dijkstra.item_in_circuit.values()))
    entity.Set[IList[XYZ]](schema.GetField("itemInCircuitOrigin"), dijkstra.item_in_circuit_origin, UnitTypeId.Millimeters)
    entity.Set[IList[ElementId]](schema.GetField("wayItemInCircuitElement"), list(dijkstra.way_item_in_circuit.keys()))
    entity.Set[IList[int]](schema.GetField("wayItemInCircuitHash"), list(dijkstra.way_item_in_circuit.values()))
    entity.Set[IList[XYZ]](schema.GetField("wayItemInCircuitOrigin"), dijkstra.way_item_in_circuit_origin, UnitTypeId.Millimeters)
    entity.Set[IList[ElementId]](schema.GetField("segmentWayElement"), dijkstra.segment_way_element)
    entity.Set[IList[float]](schema.GetField("segmentWayLength"), dijkstra.segment_way_length, UnitTypeId.Millimeters)

    circuit.SetEntity(entity)


def circuit_is_valid(circuit, route_entity, sorted_loads):
    """
    Проверяет, что сохранённый маршрут ещё актуален: длина цепи и состав/
    положение нагрузок не изменились с момента прокладки трассы.
    """
    try:
        stored_length = route_entity.Get[float]("lengthCircuit", UnitTypeId.Millimeters)
        if abs(stored_length - to_millimeters(circuit.Length)) > 1.0:
            return False

        hashes = list(route_entity.Get[IList[int]]("itemInCircuitHash"))
        origins = list(route_entity.Get[IList[XYZ]]("itemInCircuitOrigin", UnitTypeId.Millimeters))

        if len(sorted_loads) != len(hashes):
            return False

        for i, elem in enumerate(sorted_loads):
            if hash(elem.UniqueId) != hashes[i]:
                return False
            loc = elem.Location
            pt = loc.Point if isinstance(loc, LocationPoint) else None
            if pt is None or not pt.IsAlmostEqualTo(origins[i]):
                return False

        return True
    except:
        return False


# ------------------------------------------------------------
# АЛГОРИТМ ДЕЙКСТРЫ (прокладка кабеля по трассе)
# ------------------------------------------------------------

class _Vertex(object):
    __slots__ = ("number", "weight", "coord", "parent_element", "previous", "visited")

    def __init__(self, coord, number, parent_element):
        self.number = number
        self.weight = float("inf")
        self.coord = coord
        self.parent_element = parent_element
        self.previous = None
        self.visited = False


def _dot(p1, p2):
    return p1.X * p2.X + p1.Y * p2.Y + p1.Z * p2.Z


class Dijkstra(object):
    """
    Прокладывает кратчайший путь от базового оборудования цепи через
    точки трассы (лотки/короба/трубы, выделенные пользователем) до
    каждой нагрузки цепи по очереди, используя алгоритм Дейкстры на
    графе, где вершины — концы/пересечения сегментов трассы.

    doc, elec_system — Document и ElectricalSystem (Revit API).
    trace_points — список Element (сегменты кабеленесущих систем).
    mult — множитель "штрафа" за движение не по трассе (по воздуху).
    """

    _STEP_COST_MM = 0.016

    def __init__(self, doc, elec_system, trace_points, mult=2.0):
        self.doc = doc
        self.view_active = doc.ActiveView
        self.elec_system = elec_system
        self.trace_points = trace_points
        self.mult = mult

        self._circuit_points = []
        self.length_circuit = 0.0
        self.item_in_circuit = {}
        self.item_in_circuit_origin = []
        self.way_item_in_circuit = {}
        self.way_item_in_circuit_origin = []
        self.segment_way_element = []
        self.segment_way_length = []

    def reset_path(self):
        self._circuit_points = []

    def _get_weight(self, frm, to):
        dist = frm.coord.DistanceTo(to.coord)

        if frm.parent_element is None or to.parent_element is None:
            return dist * self.mult

        if frm.parent_element.Id == to.parent_element.Id:
            elem = frm.parent_element
            if not _is_carrier(elem):
                return self._STEP_COST_MM

            loc = elem.Location
            curve = loc.Curve if isinstance(loc, LocationCurve) else None

            if isinstance(curve, Line):
                pts = curve.Tessellate()
                seg_len = pts[0].DistanceTo(pts[1])
                return self._STEP_COST_MM * (dist / seg_len) if seg_len else self._STEP_COST_MM

            if isinstance(curve, HermiteSpline):
                pts = curve.Tessellate()
                between = False
                run_len = 0.0
                run_count = 0
                prev = pts[0]
                for pt in pts:
                    if between:
                        run_len += prev.DistanceTo(pt)
                        run_count += 1
                    if pt.IsAlmostEqualTo(frm.coord) or pt.IsAlmostEqualTo(to.coord):
                        between = not between
                    prev = pt
                full_len = elem.get_Parameter(BuiltInParameter.CURVE_ELEM_LENGTH).AsDouble()
                if full_len and len(pts) > 1:
                    return self._STEP_COST_MM * float(run_count) / float(len(pts) - 1) * (run_len / full_len)
                return self._STEP_COST_MM

            return self._STEP_COST_MM

        if _is_mep_curve(frm.parent_element) and _is_mep_curve(to.parent_element):
            owners_at_from = set()
            for c in frm.parent_element.ConnectorManager.Connectors:
                if c.Origin.IsAlmostEqualTo(frm.coord):
                    for ref in c.AllRefs:
                        owners_at_from.add(ref.Owner.Id)

            if owners_at_from:
                for c in to.parent_element.ConnectorManager.Connectors:
                    if c.Origin.IsAlmostEqualTo(to.coord):
                        for ref in c.AllRefs:
                            if ref.Owner.Id in owners_at_from:
                                return self._STEP_COST_MM

        return dist * self.mult

    def _get_neighbors(self, current, all_vertices):
        if all_vertices[-1].number == current.number:
            return []

        candidates = {}
        for v in all_vertices:
            if v.number == current.number or v.visited:
                continue
            w = self._get_weight(current, v)
            new_weight = current.weight + w
            if v.weight - new_weight > 1e-6:
                v.previous = current
                v.weight = new_weight
                candidates[v.weight] = v

        return [candidates[k] for k in sorted(candidates.keys())]

    def _get_xyz_projection(self, p, line_pts):
        a = line_pts[0]
        ab = line_pts[1] - a
        ap = a - p
        proj = a - (_dot(ap, ab) / _dot(ab, ab)) * ab
        is_owner = abs(
            line_pts[0].DistanceTo(line_pts[1])
            - line_pts[0].DistanceTo(proj)
            - proj.DistanceTo(line_pts[1])
        ) < 0.001
        return proj, is_owner

    def _get_projections(self, all_vertices, line_elements, count):
        seen = {}
        extra = []

        for v in all_vertices:
            for line_elem in line_elements:
                if v.parent_element.Id == line_elem.Id:
                    continue

                loc = line_elem.Location
                curve = loc.Curve if isinstance(loc, LocationCurve) else None
                if not isinstance(curve, Line):
                    continue

                line_pts = list(curve.Tessellate())
                proj, is_owner = self._get_xyz_projection(v.coord, line_pts)
                key = "{0:.6f}{1:.6f}{2:.6f}".format(proj.X, proj.Y, proj.Z)

                if is_owner and key not in seen:
                    seen[key] = line_elem.Id
                    extra.append(_Vertex(proj, count, line_elem))
                    count += 1

        return extra

    def get_path(self):
        if self._circuit_points:
            return self._circuit_points

        base_equipment = self.elec_system.BaseEquipment
        coordinate = base_equipment.Location.Point

        loads_by_connector = {}
        for connector in self.elec_system.ConnectorManager.Connectors:
            for ref in connector.AllRefs:
                if ref.Owner.Id != base_equipment.Id:
                    loads_by_connector[connector.Id] = ref.Owner

        for load in [loads_by_connector[k] for k in sorted(loads_by_connector.keys())]:
            target_coord = None
            for c in load.MEPModel.ConnectorManager.Connectors:
                for ref in c.AllRefs:
                    if ref.Owner.Id == self.elec_system.Id:
                        target_coord = c.Origin
                        break
                if target_coord is not None:
                    break

            vertices = [_Vertex(coordinate, 0, base_equipment)]
            line_elements = []
            num = 1

            levels = list(FilteredElementCollector(self.doc).OfClass(Level).ToElements())

            for trace_point in self.trace_points:
                loc = trace_point.Location

                if isinstance(loc, LocationPoint):
                    bbox = trace_point.get_BoundingBox(self.view_active)
                    if bbox is None:
                        vertices.append(_Vertex(loc.Point, num, trace_point))
                        num += 1
                    else:
                        on_level = any(
                            bbox.Min.Z < lvl.Elevation < bbox.Max.Z for lvl in levels
                        )
                        cx = bbox.Min.X + (bbox.Max.X - bbox.Min.X) / 2.0
                        cy = bbox.Min.Y + (bbox.Max.Y - bbox.Min.Y) / 2.0

                        if on_level:
                            vertices.append(_Vertex(XYZ(cx, cy, bbox.Min.Z), num, trace_point)); num += 1
                            vertices.append(_Vertex(XYZ(cx, cy, bbox.Max.Z), num, trace_point)); num += 1
                        elif (bbox.Max.X - bbox.Min.X) > (bbox.Max.Y - bbox.Min.Y):
                            cz = bbox.Min.Z + (bbox.Max.Z - bbox.Min.Z) / 2.0
                            vertices.append(_Vertex(XYZ(bbox.Min.X, cy, cz), num, trace_point)); num += 1
                            vertices.append(_Vertex(XYZ(bbox.Max.X, cy, cz), num, trace_point)); num += 1
                        else:
                            cz = bbox.Min.Z + (bbox.Max.Z - bbox.Min.Z) / 2.0
                            vertices.append(_Vertex(XYZ(cx, bbox.Min.Y, cz), num, trace_point)); num += 1
                            vertices.append(_Vertex(XYZ(cx, bbox.Max.Y, cz), num, trace_point)); num += 1

                elif isinstance(loc, LocationCurve) and isinstance(loc.Curve, Line):
                    for pt in loc.Curve.Tessellate():
                        vertices.append(_Vertex(pt, num, trace_point))
                        num += 1
                    line_elements.append(trace_point)

                elif isinstance(loc, LocationCurve) and isinstance(loc.Curve, HermiteSpline):
                    for pt in loc.Curve.Tessellate():
                        vertices.append(_Vertex(pt, num, trace_point))
                        num += 1

            vertices.append(_Vertex(target_coord, num, load))
            extra = self._get_projections(vertices, line_elements, num)
            vertices[-1:-1] = extra
            vertices[-1].number = len(vertices) - 1

            vertices[0].weight = 0.0
            frontier = self._get_neighbors(vertices[0], vertices)
            while frontier:
                current = frontier[0]
                for n in self._get_neighbors(current, vertices):
                    if not any(f.number == n.number for f in frontier):
                        frontier.append(n)
                frontier.pop(0)

            end_vertex = vertices[-1]
            path_points = [end_vertex.coord]
            path_elements = []
            path_lengths = []

            v = end_vertex
            while v.number != 0:
                prev = v.previous
                path_points.insert(0, prev.coord)

                if v.parent_element.Id == prev.parent_element.Id:
                    path_elements.insert(0, prev.parent_element.Id)
                else:
                    path_elements.insert(0, ElementId.InvalidElementId)

                path_lengths.insert(0, to_millimeters(v.coord.DistanceTo(prev.coord)))

                if v.parent_element.Id not in self.way_item_in_circuit:
                    self.way_item_in_circuit[v.parent_element.Id] = hash(v.parent_element.UniqueId)
                    p_loc = v.parent_element.Location
                    if isinstance(p_loc, LocationPoint):
                        self.way_item_in_circuit_origin.append(p_loc.Point)
                    elif isinstance(p_loc, LocationCurve):
                        if isinstance(p_loc.Curve, Line):
                            pts = list(p_loc.Curve.Tessellate())
                            self.way_item_in_circuit_origin.append(pts[0])
                            self.way_item_in_circuit_origin.append(pts[-1])
                        elif isinstance(p_loc.Curve, HermiteSpline):
                            for pt in p_loc.Curve.Tessellate():
                                self.way_item_in_circuit_origin.append(pt)

                v = prev

            self.segment_way_element.extend(path_elements)
            self.segment_way_length.extend(path_lengths)
            self.segment_way_element.append(load.Id)
            self.segment_way_length.append(-1.0)

            if load.Id not in self.item_in_circuit:
                self.item_in_circuit[load.Id] = hash(load.UniqueId)
            self.item_in_circuit_origin.append(load.Location.Point)

            if self._circuit_points and self._circuit_points[-1].IsAlmostEqualTo(path_points[0]):
                path_points.pop(0)
            self._circuit_points.extend(path_points)

            coordinate = target_coord

        return self._circuit_points


def _is_carrier(elem):
    """
    CableTray/Conduit/FlexPipe — типы элементов, для которых Dijkstra
    считает вес шага "по трассе" (0.016), а не "по воздуху" (dist * mult).
    Соответствует оригинальному C#-плагину: проверка по .NET-типу
    элемента, не по BuiltInCategory.
    """
    return isinstance(elem, (CableTray, Conduit, FlexPipe))


def _is_mep_curve(elem):
    return isinstance(elem, MEPCurve)


def order_xyz_list(points, min_length=0.0164):
    """
    Схлопывает точки маршрута ближе min_length друг к другу и разбивает
    диагональные (по XY и Z одновременно) переходы на прямые сегменты —
    так же, как оригинальный OrderXYZList в RouteByDijkstra.
    """
    result = [points[0]]

    for i in range(len(points) - 1):
        p, q = points[i], points[i + 1]
        if p.DistanceTo(q) < min_length:
            continue

        horiz = XYZ(p.X, p.Y, 0.0).DistanceTo(XYZ(q.X, q.Y, 0.0))
        vert = abs(p.Z - q.Z)

        if horiz < vert:
            if horiz < min_length:
                result.append(XYZ(q.X + min_length, q.Y + min_length, p.Z))
            result.append(XYZ(q.X, q.Y, p.Z))
            if vert < min_length:
                result.append(XYZ(q.X, q.Y, q.Z + min_length))
            result.append(XYZ(q.X, q.Y, q.Z))
        else:
            if vert < min_length:
                result.append(XYZ(p.X, p.Y, q.Z + min_length))
            result.append(XYZ(p.X, p.Y, q.Z))
            if horiz < min_length:
                result.append(XYZ(q.X + min_length, q.Y + min_length, q.Z))
            result.append(XYZ(q.X, q.Y, q.Z))

    return result
