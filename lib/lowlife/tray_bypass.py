# -*- coding: utf-8 -*-
"""Build a local cable-tray bypass around communication in linked models."""

try:
    unicode
except NameError:
    unicode = str

import re

from Autodesk.Revit import DB
from Autodesk.Revit.DB.Electrical import CableTray, CableTrayType
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List
from pyrevit import forms, script

from lowlife import fire_boxes, slab_marks, tray_boxes, tray_connection, tray_connection_core
from lowlife import tray_bypass_core as core
from lowlife.i18n import tr

FT_TO_MM = 304.8
CLEARANCE_MM = 50.0
_EXCLUDED_LINK_TOKENS = (u"АР", u"КР", u"AR", u"KR")
_COMMUNICATION_CATEGORIES = (
    "OST_DuctCurves", "OST_DuctFitting", "OST_DuctAccessory", "OST_FlexDuctCurves",
    "OST_PipeCurves", "OST_PipeFitting", "OST_PipeAccessory", "OST_FlexPipeCurves",
    "OST_CableTray", "OST_CableTrayFitting", "OST_Conduit", "OST_ConduitFitting",
    "OST_MechanicalEquipment", "OST_PlumbingFixtures", "OST_ElectricalEquipment",
    "OST_Walls", "OST_Columns", "OST_StructuralColumns", "OST_StructuralFraming",
)


def _title(document):
    try:
        return unicode(document.Title or u"")
    except Exception:
        return u""


def _id_int(element_id):
    try:
        return element_id.Value
    except Exception:
        return element_id.IntegerValue


def is_architecture_or_structure_model(title):
    tokens = set(re.findall(u"[A-ZА-ЯЁ0-9]+", (title or u"").upper()))
    return bool(tokens.intersection(_EXCLUDED_LINK_TOKENS))


def linked_sources(doc):
    result = []
    for key, (source_doc, transform) in sorted(slab_marks.model_sources(doc).items()):
        if key != -1 and not is_architecture_or_structure_model(_title(source_doc)):
            result.append((key, source_doc, transform))
    return result


def _candidates(source_doc, transform, bbox):
    categories = [getattr(DB.BuiltInCategory, name, None)
                  for name in _COMMUNICATION_CATEGORIES]
    categories = [category for category in categories if category is not None]
    if not categories:
        return []
    inverse = transform.Inverse
    points = [inverse.OfPoint(point) for point in tray_boxes._box_points(bbox)]
    outline = DB.Outline(
        DB.XYZ(min(point.X for point in points), min(point.Y for point in points),
               min(point.Z for point in points)),
        DB.XYZ(max(point.X for point in points), max(point.Y for point in points),
               max(point.Z for point in points)))
    ids = List[DB.BuiltInCategory](categories)
    try:
        return list(DB.FilteredElementCollector(source_doc)
                    .WherePasses(DB.ElementMulticategoryFilter(ids))
                    .WhereElementIsNotElementType()
                    .WherePasses(DB.BoundingBoxIntersectsFilter(outline)))
    except Exception:
        return []


def _projection(point, origin, direction):
    return point.Subtract(origin).DotProduct(direction)


def _category_id(element):
    try:
        return _id_int(element.Category.Id)
    except Exception:
        return None


def _is_tray_element(element):
    category_id = _category_id(element)
    for name in ("OST_CableTray", "OST_CableTrayFitting"):
        category = getattr(DB.BuiltInCategory, name, None)
        if category is not None and category_id == int(category):
            return True
    return False


def _side_vector(tray):
    direction = tray.Location.Curve.Direction
    side = DB.XYZ(-direction.Y, direction.X, 0.0)
    return side.Normalize() if side.GetLength() > 1e-9 else DB.XYZ.BasisX


def _crossing(tray, element, transform, options, curve_options):
    curve = tray.Location.Curve
    origin = curve.GetEndPoint(0)
    direction = curve.Direction
    local_curve = curve.CreateTransformed(transform.Inverse)
    spans = []
    for solid in tray_boxes._solids(element, options):
        try:
            hit = solid.IntersectWithCurve(local_curve, curve_options)
        except Exception:
            continue
        try:
            for index in range(hit.SegmentCount):
                segment = hit.GetCurveSegment(index)
                try:
                    first = transform.OfPoint(segment.GetEndPoint(0))
                    second = transform.OfPoint(segment.GetEndPoint(1))
                    spans.append((_projection(first, origin, direction),
                                  _projection(second, origin, direction)))
                finally:
                    segment.Dispose()
        finally:
            hit.Dispose()
    if not spans:
        return None
    bbox = element.get_BoundingBox(None)
    if bbox is None:
        return None
    world_points = [transform.OfPoint(point)
                    for point in tray_boxes._box_points(bbox)]
    side = _side_vector(tray)
    side_values = [_projection(point, origin, side) for point in world_points]
    vertical_values = [point.Z for point in world_points]
    return {
        "start": min(min(span) for span in spans),
        "end": max(max(span) for span in spans),
        "mode": "vertical" if _is_tray_element(element) else "side",
        "perp_min": min(side_values),
        "perp_max": max(side_values),
        "vertical_min": min(vertical_values),
        "vertical_max": max(vertical_values),
    }


def find_linked_crossings(doc, tray):
    bbox = tray.get_BoundingBox(None)
    if bbox is None:
        return []
    options = DB.Options()
    options.DetailLevel = DB.ViewDetailLevel.Fine
    curve_options = DB.SolidCurveIntersectionOptions()
    result = []
    try:
        for _key, source_doc, transform in linked_sources(doc):
            for element in _candidates(source_doc, transform, bbox):
                item = _crossing(tray, element, transform, options, curve_options)
                if item is not None:
                    result.append(item)
    finally:
        curve_options.Dispose()
    return result


def _level_id(tray):
    level = getattr(tray, "ReferenceLevel", None)
    if level is not None:
        return level.Id
    return getattr(tray, "LevelId", DB.ElementId.InvalidElementId)


def _neighbors(tray):
    result = []
    seen = set()
    for connector in fire_boxes.connectors(tray):
        try:
            refs = connector.AllRefs
        except Exception:
            refs = []
        for reference in refs:
            owner = reference.Owner
            if owner is None or owner.Id == tray.Id:
                continue
            key = _id_int(owner.Id)
            if key not in seen:
                seen.add(key)
                result.append(owner)
    return result


class _TrayFilter(ISelectionFilter):
    def AllowElement(self, element):
        return isinstance(element, CableTray)

    def AllowReference(self, reference, point):
        return False


def _pick_tray(uidoc):
    selected = [uidoc.Document.GetElement(element_id)
                for element_id in uidoc.Selection.GetElementIds()]
    selected = [element for element in selected if isinstance(element, CableTray)]
    if len(selected) == 1:
        return selected[0]
    try:
        reference = uidoc.Selection.PickObject(
            ObjectType.Element, _TrayFilter(),
            tr(u"Выберите лоток для обхода",
               u"Select the cable tray to bypass"))
    except OperationCanceledException:
        return None
    return uidoc.Document.GetElement(reference)


def _ask_bypass_sides(crossings):
    vertical_side = None
    horizontal_side = None
    if any(item.get("mode") == "vertical" for item in crossings):
        above = forms.alert(
            tr(u"\u041e\u0431\u0445\u043e\u0434 \u043f\u043e\u0434\u043d\u044f\u0442\u044c \u0432\u044b\u0448\u0435 \u043b\u043e\u0442\u043a\u043e\u0432 \u0438\u043b\u0438 \u043e\u043f\u0443\u0441\u0442\u0438\u0442\u044c?\n\n"
               u"\u0414\u0430 — \u0432\u044b\u0448\u0435, \u041d\u0435\u0442 — \u043d\u0438\u0436\u0435.",
               u"Should the tray bypass go above the crossing trays?\n\n"
               u"Yes means above, No means below."),
            yes=True, no=True)
        vertical_side = 1 if above else -1
    if any(item.get("mode") != "vertical" for item in crossings):
        left = forms.alert(
            tr(u"\u041e\u0431\u0445\u043e\u0434\u0438\u0442\u044c \u0441\u043b\u0435\u0432\u0430 \u0438\u043b\u0438 \u0441\u043f\u0440\u0430\u0432\u0430 \u043e\u0442 \u043f\u0435\u0440\u0435\u0441\u0435\u0447\u0435\u043d\u0438\u044f?\n\n"
               u"\u0414\u0430 — \u0441\u043b\u0435\u0432\u0430, \u041d\u0435\u0442 — \u0441\u043f\u0440\u0430\u0432\u0430, \u0435\u0441\u043b\u0438 \u0441\u043c\u043e\u0442\u0440\u0435\u0442\u044c \u043e\u0442 \u043d\u0430\u0447\u0430\u043b\u0430 \u043b\u043e\u0442\u043a\u0430 \u043a \u0435\u0433\u043e \u043a\u043e\u043d\u0446\u0443.",
               u"Should the tray bypass go to the left of the crossing?\n\n"
               u"Yes means left, No means right, looking from the tray start to its end."),
            yes=True, no=True)
        horizontal_side = 1 if left else -1
    return vertical_side, horizontal_side

def _ask_connection_angle():
    raw = forms.ask_for_string(
        default="45",
        prompt=tr(
            u"\u0423\u0433\u043e\u043b \u0441\u043e\u0435\u0434\u0438\u043d\u0435\u043d\u0438\u044f \u043b\u043e\u0442\u043a\u0430 \u0441 \u043f\u043e\u0434\u044a\u0451\u043c\u043e\u043c, \u0433\u0440\u0430\u0434\u0443\u0441\u044b (2-88):",
            u"Tray connection angle with the rise, degrees (2-88):"
        ),
        title=tr(u"\u0421\u043e\u0435\u0434\u0438\u043d\u0435\u043d\u0438\u0435 \u043b\u043e\u0442\u043a\u043e\u0432",
                  u"Connect trays")
    )
    try:
        return tray_connection_core.parse_angle(raw)
    except ValueError as exc:
        forms.alert(tr(u"\u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 \u0443\u0433\u043e\u043b: {}",
                       u"Invalid angle: {}").format(exc), exitscript=True)


def _create_segments(doc, tray, points):
    tray_type = doc.GetElement(tray.GetTypeId())
    if not isinstance(tray_type, CableTrayType):
        raise ValueError(tr(u"Выберите свойство кабельного лотка.",
                            u"Select a cable tray."))
    width, height = fire_boxes.dimensions(tray)
    result = []
    for first, second in zip(points[:-1], points[1:]):
        segment = fire_boxes.create_curve(
            doc, tray_type, None, _level_id(tray), DB.XYZ(*first), DB.XYZ(*second),
            width, height)
        fire_boxes.assign_workset(segment, getattr(tray, "WorksetId", None))
        result.append(segment)
    doc.Regenerate()
    return result


def _try_connect_route(doc, created, points, neighbors, start, end,
                       angle=None, grouped_vertical=False):
    """Add fittings after the geometry is committed.

    A rejected fitting must not be able to roll back the already-created
    bypass. The optional fitting transaction is discarded as a whole on the
    first Revit rejection.
    """
    fitting_transaction = DB.Transaction(doc, tr(
        u"Соединить сегменты обхода",
        u"Connect tray bypass segments"))
    try:
        fitting_transaction.Start()
        if grouped_vertical:
            additions = []
            additions.extend(tray_connection.create_connection(
                doc, created[0], created[1], angle))
            additions.extend(tray_connection.create_connection(
                doc, created[1], created[2], angle))
        else:
            joins = list(zip(created[:-1], created[1:], points[1:-1]))
            if neighbors:
                joins.insert(0, (neighbors[0], created[0], start))
            if len(neighbors) > 1:
                joins.append((created[-1], neighbors[-1], end))
            for first, second, point in joins:
                fire_boxes.join(doc, [first, second], DB.XYZ(*point))
            additions = []
        if fitting_transaction.Commit() != DB.TransactionStatus.Committed:
            raise ValueError("Revit rejected the bypass fittings.")
        return additions
    except Exception:
        if fitting_transaction.GetStatus() == DB.TransactionStatus.Started:
            fitting_transaction.RollBack()
        return []


def _try_grouped_connection(doc, created, angle):
    subtransaction = DB.SubTransaction(doc)
    try:
        subtransaction.Start()
        additions = []
        additions.extend(tray_connection.create_connection(
            doc, created[0], created[1], angle))
        additions.extend(tray_connection.create_connection(
            doc, created[1], created[2], angle))
        subtransaction.Commit()
        return additions
    except Exception:
        if subtransaction.GetStatus() == DB.TransactionStatus.Started:
            subtransaction.RollBack()
        script.get_logger().exception("Grouped tray connection failed")
        return []


def run_tray_bypass(doc, uidoc):
    tray = _pick_tray(uidoc)
    if tray is None:
        return
    if not isinstance(getattr(tray.Location, "Curve", None), DB.Line):
        forms.alert(tr(u"Выберите прямой кабельный лоток.",
                       u"Only a straight cable tray can be bypassed"), exitscript=True)
        return
    crossings = find_linked_crossings(doc, tray)
    if not crossings:
        forms.alert(tr(u"В связанных моделях инженерные коммуникации не пересекают лоток.",
                       u"No linked engineering communication crosses the tray."),
                    exitscript=True)
        return
    vertical_side, horizontal_side = _ask_bypass_sides(crossings)
    curve = tray.Location.Curve
    start, end = curve.GetEndPoint(0), curve.GetEndPoint(1)
    width, height = fire_boxes.dimensions(tray)
    side = _side_vector(tray)
    route = core.plan_bypass(
        (start.X, start.Y, start.Z), (end.X, end.Y, end.Z),
        (side.X, side.Y, side.Z), crossings,
        (width / FT_TO_MM) / 2.0,
        CLEARANCE_MM / FT_TO_MM,
        tray_half_height=(height / FT_TO_MM) / 2.0,
        group_gap=max(CLEARANCE_MM * 2.0 / FT_TO_MM,
                      width / FT_TO_MM + CLEARANCE_MM / FT_TO_MM),
        vertical_side=vertical_side,
        horizontal_side=horizontal_side)
    grouped_vertical = (
        len(route) == 6 and crossings and
        all(item.get("mode") == "vertical" for item in crossings))
    angle = _ask_connection_angle() if grouped_vertical else None
    transaction = DB.Transaction(doc, tr(u"Обход коммуникации лотком",
                                         u"Bypass cable tray communication"))
    transaction.Start()
    try:
        neighbors = _neighbors(tray)
        if grouped_vertical:
            created = []
            for first, second in ((route[0], route[1]),
                                  (route[2], route[3]),
                                  (route[4], route[5])):
                created.extend(_create_segments(doc, tray, [first, second]))
        else:
            created = _create_segments(doc, tray, route)
        additions = _try_grouped_connection(doc, created, angle) if grouped_vertical else []
        doc.Delete(tray.Id)
        if transaction.Commit() != DB.TransactionStatus.Committed:
            raise ValueError(tr(u"Revit не применил обход.",
                                u"Revit rolled back the bypass."))
    except Exception:
        if transaction.GetStatus() == DB.TransactionStatus.Started:
            transaction.RollBack()
        raise
    if not grouped_vertical:
        additions = _try_connect_route(doc, created, route, neighbors, start, end)
    all_created = created + additions
    uidoc.Selection.SetElementIds(List[DB.ElementId]([element.Id for element in all_created]))
    forms.alert(tr(u"Обход построен. Сегментов лотка: {}.",
                   u"Bypass created. Tray segments: {}.").format(len(all_created)))


def run(doc, uidoc):
    try:
        run_tray_bypass(doc, uidoc)
    except OperationCanceledException:
        return
    except Exception as exc:
        script.get_logger().exception("Tray bypass failed")
        forms.alert(tr(u"Не удалось построить обход лотка:\n{}",
                       u"Could not create the tray bypass:\n{}").format(exc))

