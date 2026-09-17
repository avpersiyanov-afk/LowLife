# -*- coding: utf-8 -*-
"""
Логика кнопки «Заполнение LOI» (LOI.panel): клонирование значений
параметров из элементов категории «Форма» (см. loi_settings.py) во все
элементы активного вида, физически находящиеся внутри солида конкретной
«Формы».

Проверка «элемент внутри формы» — точно по солиду формы (не по bounding
box): для точечных элементов (LocationPoint) — попадание точки в солид
через ray-casting (point_in_solid), для линейных (LocationCurve, лотки/
короба/трубы) — пересечение кривой с солидом (curve_intersects_solid,
через Solid.IntersectWithCurve — та же проверка, что и для точки, просто
на всей длине кривой, а не в одной точке). Bounding box формы/элемента —
только дешёвый предварительный отсев пар, которые точно не пересекаются,
перед дорогой точной проверкой.

Линейный элемент может попасть сразу в несколько «Форм» (например лоток,
проходящий через границу двух форм) — для такого элемента однозначно
клонировать нечего, он идёт в список конфликтов, где источник выбирает
пользователь (see loi_conflict_dialog.py). Элемент, попавший ровно в одну
форму, клонируется автоматически.

«Формы» ищутся и в текущем файле, и во всех загруженных связях (обычно
это категория из связанной архитектурной модели) — геометрия и bbox
элементов связи трансформируются в координаты текущего файла через
RevitLinkInstance.GetTotalTransform(), тем же способом, что и у обычного
элемента текущего файла, только с дополнительным Transform. Кандидаты
(элементы, которые заполняются) ищутся только в текущем файле — писать
параметры в элементы связи API не позволяет (это отдельный открытый
Document, а не часть текущей транзакции).
"""

from Autodesk.Revit.DB import (
    Element, FilteredElementCollector, Options, Solid, GeometryInstance,
    LocationPoint, LocationCurve, Line, XYZ, SolidCurveIntersectionOptions,
    CategoryType, ViewDetailLevel, RevitLinkInstance, SolidUtils, BoundingBoxXYZ
)

from lowlife import params as params_mod

MIN_SOLID_VOLUME = 1e-9
RAY_LENGTH_FT = 10000.0
POINT_TOL_FT = 0.01
BBOX_TOL_FT = 0.01


# --- геометрия -----------------------------------------------------------

def _iter_solids(geometry_element):
    solids = []
    for gobj in geometry_element:
        if isinstance(gobj, Solid):
            if gobj.Volume > MIN_SOLID_VOLUME:
                solids.append(gobj)
        elif isinstance(gobj, GeometryInstance):
            try:
                inst_geom = gobj.GetInstanceGeometry()
            except:
                inst_geom = None
            if inst_geom is not None:
                solids.extend(_iter_solids(inst_geom))
    return solids


def get_element_solids(el, extra_transform=None):
    """
    Все твёрдые тела элемента (Volume > 0), в координатах его собственного
    документа. extra_transform (например RevitLinkInstance.GetTotalTransform())
    — для элемента из связи, чтобы получить солид в координатах текущего файла.
    """
    opts = Options()
    opts.ComputeReferences = False
    opts.IncludeNonVisibleObjects = False
    opts.DetailLevel = ViewDetailLevel.Fine

    try:
        geom = el.get_Geometry(opts)
    except:
        geom = None

    if geom is None:
        return []

    solids = _iter_solids(geom)

    if extra_transform is None or extra_transform.IsIdentity:
        return solids

    transformed = []
    for solid in solids:
        try:
            transformed.append(SolidUtils.CreateTransformed(solid, extra_transform))
        except:
            transformed.append(solid)
    return transformed


def _transform_bbox(bbox, transform):
    """Bbox элемента связи (в координатах связи) -> bbox в координатах текущего файла."""
    if bbox is None:
        return None
    if transform is None or transform.IsIdentity:
        return bbox

    xs, ys, zs = [], [], []
    for x in (bbox.Min.X, bbox.Max.X):
        for y in (bbox.Min.Y, bbox.Max.Y):
            for z in (bbox.Min.Z, bbox.Max.Z):
                p = transform.OfPoint(XYZ(x, y, z))
                xs.append(p.X)
                ys.append(p.Y)
                zs.append(p.Z)

    new_bbox = BoundingBoxXYZ()
    new_bbox.Min = XYZ(min(xs), min(ys), min(zs))
    new_bbox.Max = XYZ(max(xs), max(ys), max(zs))
    return new_bbox


def point_in_solid(solid, pt, tol=POINT_TOL_FT):
    """
    True, если точка pt лежит внутри solid — ray-casting: пускаем луч
    вверх ИЗ точки и смотрим, начинается ли первый "внутренний" отрезок
    пересечения ровно в pt (если pt внутри тела — луч сразу входит в
    "внутри", если снаружи — первый внутренний отрезок начнётся дальше,
    в точке входа в тело, либо пересечений не будет вовсе).
    """
    ray = Line.CreateBound(pt, XYZ(pt.X, pt.Y, pt.Z + RAY_LENGTH_FT))

    try:
        result = solid.IntersectWithCurve(ray, SolidCurveIntersectionOptions())
    except:
        return False

    if result is None or result.SegmentCount == 0:
        return False

    seg0 = result.GetCurveSegment(0)
    start = seg0.GetEndPoint(0)
    return start.DistanceTo(pt) <= tol


def curve_intersects_solid(solid, curve):
    """True, если хотя бы часть curve лежит внутри solid."""
    try:
        result = solid.IntersectWithCurve(curve, SolidCurveIntersectionOptions())
    except:
        return False

    return result is not None and result.SegmentCount > 0


def get_test_geometry(el):
    """
    ("point", XYZ) для точечных элементов, ("curve", Curve) для линейных,
    ("point", XYZ-центр bbox) как запасной вариант для всего остального
    (нет LocationPoint/LocationCurve — например элемент, заданный только
    солидом без явной точки/кривой вставки). None, если геометрию найти
    не удалось вовсе.
    """
    try:
        loc = el.Location
    except:
        loc = None

    if isinstance(loc, LocationPoint):
        return ("point", loc.Point)

    if isinstance(loc, LocationCurve):
        return ("curve", loc.Curve)

    try:
        bbox = el.get_BoundingBox(None)
    except:
        bbox = None

    if bbox is None:
        return None

    center = XYZ(
        (bbox.Min.X + bbox.Max.X) / 2.0,
        (bbox.Min.Y + bbox.Max.Y) / 2.0,
        (bbox.Min.Z + bbox.Max.Z) / 2.0,
    )
    return ("point", center)


def bbox_overlap(a, b, tol=BBOX_TOL_FT):
    """Дешёвый предварительный отсев: пересекаются ли габариты a и b (с запасом tol)."""
    if a is None or b is None:
        return True

    return not (
        a.Max.X + tol < b.Min.X or b.Max.X + tol < a.Min.X or
        a.Max.Y + tol < b.Min.Y or b.Max.Y + tol < a.Min.Y or
        a.Max.Z + tol < b.Min.Z or b.Max.Z + tol < a.Min.Z
    )


# --- сбор форм/кандидатов -------------------------------------------------

class FormRecord(object):
    def __init__(self, element, solids, bbox, label):
        self.element = element
        self.solids = solids
        self.bbox = bbox
        self.label = label


def _collect_form_records(collector, category_name, type_doc, transform, source_label):
    records = []

    for el in collector:
        cat = el.Category
        if cat is None or cat.Name != category_name:
            continue

        solids = get_element_solids(el, transform)
        if not solids:
            continue

        try:
            bbox = el.get_BoundingBox(None)
        except:
            bbox = None
        bbox = _transform_bbox(bbox, transform)

        label = u"{} (ID {})".format(element_display_name(type_doc, el), el.Id.IntegerValue)
        if source_label:
            label = u"{} [{}]".format(label, source_label)

        records.append(FormRecord(el, solids, bbox, label))

    return records


def find_forms(doc, view, category_name):
    """
    Элементы категории category_name — в текущем файле (видимые на view) и
    во всех загруженных связях (без привязки к виду — у связи нет вида
    текущего файла; геометрия/bbox трансформируются в координаты текущего
    файла через RevitLinkInstance.GetTotalTransform()).
    """
    records = []

    host_collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
    records.extend(_collect_form_records(host_collector, category_name, doc, None, u""))

    link_collector = FilteredElementCollector(doc).OfClass(RevitLinkInstance)
    for link_inst in link_collector:
        try:
            link_doc = link_inst.GetLinkDocument()
        except:
            link_doc = None
        if link_doc is None:
            continue

        try:
            transform = link_inst.GetTotalTransform()
        except:
            transform = None

        link_name = _safe_name(link_inst)
        link_elems = FilteredElementCollector(link_doc).WhereElementIsNotElementType()
        records.extend(_collect_form_records(link_elems, category_name, link_doc, transform, link_name))

    return records


def collect_candidates(doc, view, exclude_category_name):
    """Все элементы модели активного вида, кроме самих «Форм» и не-модельных категорий."""
    result = []

    collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
    for el in collector:
        cat = el.Category
        if cat is None:
            continue
        if cat.Name == exclude_category_name:
            continue
        try:
            if cat.CategoryType != CategoryType.Model:
                continue
        except:
            continue

        result.append(el)

    return result


class MatchRecord(object):
    def __init__(self, element, forms_matched):
        self.element = element
        self.forms = forms_matched  # list of FormRecord


def classify_elements(form_records, candidates):
    """
    {ElementId: MatchRecord} только для кандидатов, попавших хотя бы в
    одну форму (0 совпадений — элемент просто не участвует).
    """
    matches = {}

    for el in candidates:
        test = get_test_geometry(el)
        if test is None:
            continue

        try:
            el_bbox = el.get_BoundingBox(None)
        except:
            el_bbox = None

        matched_forms = []
        for form in form_records:
            if not bbox_overlap(el_bbox, form.bbox):
                continue

            hit = False
            for solid in form.solids:
                if test[0] == "point":
                    if point_in_solid(solid, test[1]):
                        hit = True
                        break
                else:
                    if curve_intersects_solid(solid, test[1]):
                        hit = True
                        break

            if hit:
                matched_forms.append(form)

        if matched_forms:
            matches[el.Id] = MatchRecord(el, matched_forms)

    return matches


# --- параметры -------------------------------------------------------------

def _safe_name(el):
    # Element.Name.GetValue(el) avoids the ambiguous-binding error some
    # element types throw on plain el.Name under IronPython (see
    # scs_settings._safe_element_name / cable_tray._safe_type_name).
    try:
        return Element.Name.GetValue(el)
    except:
        try:
            return el.Name
        except:
            return u""


def element_type_name(doc, el):
    """Имя типа (FamilySymbol/ElementType) элемента el, иначе — имя самого el."""
    type_el = None
    try:
        type_id = el.GetTypeId()
        if type_id is not None:
            type_el = doc.GetElement(type_id)
    except:
        type_el = None

    if type_el is not None:
        name = _safe_name(type_el)
        if name:
            return name

    return _safe_name(el)


def element_display_name(doc, el):
    try:
        cat_name = el.Category.Name
    except:
        cat_name = u"?"
    return u"{}: {}".format(cat_name, element_type_name(doc, el))


def collect_form_values(form_el, param_names):
    """{имя_параметра: строковое_значение} только для параметров, у которых есть значение."""
    values = {}
    for name in param_names:
        val = params_mod.get_param_any(form_el, name)
        if val is not None:
            values[name] = val
    return values


def format_values(values, param_names):
    parts = []
    for name in param_names:
        if name in values:
            parts.append(u"{}={}".format(name, values[name]))
    return u"; ".join(parts) if parts else u"—"


def apply_values(target_el, values):
    """
    Записывает values в target_el. Возвращает список (имя, значение, успех)
    — вызывающий код сам решает, что делать с неуспешными записями.
    Вызывать внутри revit.Transaction.
    """
    applied = []
    for name, val in values.items():
        ok = params_mod.set_param_any(target_el, name, val)
        applied.append((name, val, ok))
    return applied
