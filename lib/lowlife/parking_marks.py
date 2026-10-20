# -*- coding: utf-8 -*-
"""
Кнопка «Отметки парковки» (Tools.panel/ParkingMarks). Revit-часть; чистая
логика — parking_marks_core.py, настройки — parking_marks_settings.py.

Что делает на плане:
  1. collect — элементы категории «Парковка» из всех загруженных связей,
     видимых на виде и попадающих в его секущий диапазон (от глубины
     просмотра до секущей плоскости) и в подрезку. Верх/низ — по
     горизонтальным граням геометрии элемента, без граней — по габариту.
  2. annotate_view — у машиноместа отмечается верх; у зоны (в «Комментариях»
     есть слово из настроек) — верх и низ, а её контур (самая большая
     горизонтальная грань) заливается штриховкой. Отметка — высотная отметка
     Revit на грани элемента связи, где Revit её не принял — текст.
     Повторный запуск заменяет отметки, тексты и заливки прошлого запуска.

Вызывать внутри открытой транзакции.
"""

import math

from Autodesk.Revit.DB import (
    XYZ, Line, CurveLoop, ElementId, FilteredElementCollector, BuiltInCategory,
    BuiltInParameter, Level, TextNote, FilledRegion, FilledRegionType, ElementTypeGroup,
    Options, ViewDetailLevel, Solid, GeometryInstance, PlanarFace, RevitLinkInstance,
    Transform, SpotDimension, SpotDimensionType, DimensionStyleType, PlanViewPlane,
    BasePoint, Color, UV
)

from lowlife import parking_marks_core as core
from lowlife import slab_marks
from lowlife.scs import safe_element_name

FT_TO_MM = 304.8

# Типы текста и высотной отметки (копии типов по умолчанию): по ним повторный
# запуск находит и удаляет отметки прошлого запуска на виде.
TEXT_TYPE_NAME = u"LowLife — отметки парковки"
SPOT_TYPE_NAME = u"LowLife — отметки парковки"

# Тип заливки зон по умолчанию и метка в «Комментариях» её областей.
FILL_TYPE_NAME = u"LowLife — зона парковки"
FILL_COLOR = (240, 140, 40)
REGION_TAG = u"LowLife парковка"

# Отметка низа зоны сдвигается от отметки верха на столько мм на листе.
LABEL_GAP_MM = 6.0

# Горизонтальная грань: |нормаль.Z| не меньше; грани верха в пределах допуска — одна отметка.
_HORIZONTAL = 0.999
_SAME_Z_FT = 1.0 / FT_TO_MM

is_plan = slab_marks.is_plan


def mm(value_ft):
    return value_ft * FT_TO_MM


def ft(value_mm):
    return value_mm / FT_TO_MM


# ------------------------------------------------------------
# Геометрия элемента связи
# ------------------------------------------------------------

class HFace(object):
    """Горизонтальная плоская грань: грань, преобразование в координаты модели, отметка (футы)."""

    def __init__(self, face, transform, z, up):
        self.face = face
        self.transform = transform
        self.z = z
        self.up = up
        self.area = face.Area

    def point_at(self, x, y):
        """Точка грани над/под (x, y) модели или None — (x, y) вне грани."""
        try:
            local = self.transform.Inverse.OfPoint(XYZ(x, y, self.z))
            found = self.face.Project(local)
            if found is None or found.Distance > 1e-3 or not self.face.IsInside(found.UVPoint):
                return None
            return XYZ(x, y, self.z)
        except Exception:
            return None

    def inner_point(self):
        """Точка внутри грани (центр её UV-габарита, иначе узел сетки 5×5) в координатах модели."""
        box = self.face.GetBoundingBox()
        lo, hi = box.Min, box.Max
        steps = [0.5, 0.3, 0.7, 0.1, 0.9]
        for su in steps:
            for sv in steps:
                uv = UV(lo.U + (hi.U - lo.U) * su, lo.V + (hi.V - lo.V) * sv)
                if self.face.IsInside(uv):
                    return self.transform.OfPoint(self.face.Evaluate(uv))
        return None

    def loops(self, z):
        """Контуры грани (CurveLoop), опущенные на отметку z."""
        move = Transform.CreateTranslation(XYZ(0, 0, z - self.z)).Multiply(self.transform)
        result = []
        for edge_loop in self.face.EdgeLoops:
            loop = CurveLoop()
            for edge in edge_loop:
                loop.Append(edge.AsCurveFollowingFace(self.face).CreateTransformed(move))
            result.append(loop)
        return result


def _solids(geometry, transform):
    for item in geometry or []:
        if isinstance(item, Solid):
            if item.Faces.Size:
                yield item, transform
        elif isinstance(item, GeometryInstance):
            for nested in _solids(item.GetSymbolGeometry(), transform.Multiply(item.Transform)):
                yield nested


def horizontal_faces(element, transform):
    options = Options()
    options.ComputeReferences = True
    options.DetailLevel = ViewDetailLevel.Fine
    faces = []
    for solid, solid_transform in _solids(element.get_Geometry(options), transform):
        for face in solid.Faces:
            if not isinstance(face, PlanarFace):
                continue
            normal = solid_transform.OfVector(face.FaceNormal)
            if abs(normal.Z) < _HORIZONTAL:
                continue
            z = solid_transform.OfPoint(face.Origin).Z
            faces.append(HFace(face, solid_transform, z, normal.Z > 0))
    return faces


def _extreme(faces, highest):
    """Самая высокая (или низкая) грань; из равных по отметке — самая большая."""
    if not faces:
        return None
    z = max(f.z for f in faces) if highest else min(f.z for f in faces)
    return max([f for f in faces if abs(f.z - z) <= _SAME_Z_FT], key=lambda f: f.area)


def _box_corners(element, transform):
    """8 углов габарита элемента в координатах модели или []."""
    try:
        box = element.get_BoundingBox(None)
    except Exception:
        box = None
    if box is None:
        return []
    to_model = transform.Multiply(box.Transform)
    corners = []
    for x in (box.Min.X, box.Max.X):
        for y in (box.Min.Y, box.Max.Y):
            for z in (box.Min.Z, box.Max.Z):
                corners.append(to_model.OfPoint(XYZ(x, y, z)))
    return corners


def _comment(element):
    try:
        param = element.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        return param.AsString() if param is not None else None
    except Exception:
        return None


class ParkingItem(object):
    """Элемент «Парковка» связи: верх/низ (футы, координаты модели), грани, зона ли."""

    def __init__(self, link, link_name, element, transform, zone):
        self.link = link
        self.link_name = link_name
        self.element = element
        self.transform = transform
        self.zone = zone
        self.top_face = None
        self.bottom_face = None
        self.outline_face = None
        self.corners = []
        self.top_z = None
        self.bottom_z = None
        self.anchor = None  # точка отметки верха (x, y модели)

    @property
    def label(self):
        return u"{}: {} (Id {})".format(self.link_name, safe_element_name(self.element) or u"",
                                       self.element.Id.IntegerValue)

    def xy_range(self):
        xs = [p.X for p in self.corners]
        ys = [p.Y for p in self.corners]
        return min(xs), min(ys), max(xs), max(ys)


def make_item(link, link_name, element, transform, zone_words):
    """ParkingItem или None — у элемента нет ни геометрии, ни габарита."""
    item = ParkingItem(link, link_name, element, transform,
                       core.is_zone(_comment(element), zone_words))
    try:
        faces = horizontal_faces(element, transform)
    except Exception:
        faces = []
    item.corners = _box_corners(element, transform)
    item.top_face = _extreme([f for f in faces if f.up], True)
    item.bottom_face = _extreme([f for f in faces if not f.up], False)
    if faces:
        item.outline_face = max(faces, key=lambda f: f.area)
    if item.corners:
        item.top_z = max(p.Z for p in item.corners)
        item.bottom_z = min(p.Z for p in item.corners)
    if item.top_face is not None:
        item.top_z = item.top_face.z
    if item.bottom_face is not None:
        item.bottom_z = item.bottom_face.z
    if item.top_z is None or item.bottom_z is None:
        return None
    if not item.corners:
        item.corners = [p for f in faces for p in [f.inner_point()] if p is not None]
        if not item.corners:
            return None
    point = None
    for face in (item.top_face, item.outline_face):
        if face is not None and point is None:
            x0, y0, x1, y1 = item.xy_range()
            point = face.point_at((x0 + x1) / 2.0, (y0 + y1) / 2.0) or face.inner_point()
    if point is None:
        x0, y0, x1, y1 = item.xy_range()
        point = XYZ((x0 + x1) / 2.0, (y0 + y1) / 2.0, item.top_z)
    item.anchor = point
    return item


# ------------------------------------------------------------
# Что видно на плане
# ------------------------------------------------------------

def view_z_range(doc, view):
    """(низ, верх) секущего диапазона плана в футах модели: от глубины
    просмотра до секущей плоскости; None — без ограничения."""
    try:
        view_range = view.GetViewRange()
    except Exception:
        return None, None

    def plane_z(plane):
        try:
            level = doc.GetElement(view_range.GetLevelId(plane))
            if isinstance(level, Level):
                return level.ProjectElevation + view_range.GetOffset(plane)
        except Exception:
            pass
        return None

    cut = plane_z(PlanViewPlane.CutPlane)
    depth = plane_z(PlanViewPlane.ViewDepthPlane)
    if cut is None or depth is None:
        return depth, cut   # план: глубина просмотра ниже секущей плоскости
    return min(cut, depth), max(cut, depth)


def _in_crop(view, item):
    try:
        if not view.CropBoxActive:
            return True
        box = view.CropBox
        inverse = box.Transform.Inverse
        local = [inverse.OfPoint(p) for p in item.corners]
    except Exception:
        return True
    return (min(p.X for p in local) <= box.Max.X and max(p.X for p in local) >= box.Min.X and
            min(p.Y for p in local) <= box.Max.Y and max(p.Y for p in local) >= box.Min.Y)


class Collected(object):
    def __init__(self):
        self.items = []
        self.links = []           # имена связей, в которых искали
        self.unloaded = []        # имена выгруженных связей
        self.hidden_links = []    # скрытых на виде
        self.out_of_range = 0     # вне секущего диапазона
        self.out_of_crop = 0      # вне подрезки
        self.no_geometry = []     # подписи элементов без геометрии
        self.category_hidden = False


def collect(doc, view, zone_words):
    result = Collected()
    try:
        result.category_hidden = view.GetCategoryHidden(ElementId(BuiltInCategory.OST_Parking))
    except Exception:
        pass
    bottom, top = view_z_range(doc, view)
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        name = safe_element_name(link) or u"связь {}".format(link.Id.IntegerValue)
        try:
            link_doc = link.GetLinkDocument()
        except Exception:
            link_doc = None
        if link_doc is None:
            result.unloaded.append(name)
            continue
        try:
            if link.IsHidden(view):
                result.hidden_links.append(name)
                continue
        except Exception:
            pass
        result.links.append(name)
        transform = link.GetTotalTransform()
        elements = (FilteredElementCollector(link_doc).OfCategory(BuiltInCategory.OST_Parking)
                    .WhereElementIsNotElementType())
        for element in elements:
            item = make_item(link, name, element, transform, zone_words)
            if item is None:
                result.no_geometry.append(u"{}: Id {}".format(name, element.Id.IntegerValue))
                continue
            if not core.overlaps(item.bottom_z, item.top_z, bottom, top):
                result.out_of_range += 1
                continue
            if not _in_crop(view, item):
                result.out_of_crop += 1
                continue
            result.items.append(item)
    return result


# ------------------------------------------------------------
# Типы
# ------------------------------------------------------------

def text_type(doc):
    return slab_marks.text_type(doc, TEXT_TYPE_NAME)


def spot_type(doc):
    """Тип высотной отметки SPOT_TYPE_NAME (копия типа по умолчанию) или None."""
    types = []
    for candidate in FilteredElementCollector(doc).OfClass(SpotDimensionType):
        try:
            if candidate.StyleType != DimensionStyleType.SpotElevation:
                continue
        except Exception:
            continue
        if safe_element_name(candidate) == SPOT_TYPE_NAME:
            return candidate
        types.append(candidate)
    base = None
    try:
        base = doc.GetElement(doc.GetDefaultElementTypeId(ElementTypeGroup.SpotElevationType))
    except Exception:
        pass
    if base is None and types:
        base = types[0]
    if base is None:
        return None
    try:
        return base.Duplicate(SPOT_TYPE_NAME)
    except Exception:
        return None


def fill_type(doc, name):
    """(тип области заливки, ошибка). Пустое имя — FILL_TYPE_NAME, создаётся
    при отсутствии копией первого немаскирующего типа с диагональной штриховкой."""
    name = (name or u"").strip()
    types = list(FilteredElementCollector(doc).OfClass(FilledRegionType))
    for candidate in types:
        if safe_element_name(candidate) == (name or FILL_TYPE_NAME):
            return candidate, None
    if name:
        return None, u"в проекте нет типа области заливки «{}»".format(name)
    base = slab_marks.region_type(doc, None)
    if base is None:
        return None, u"в проекте нет ни одного типа области заливки"
    created = base.Duplicate(FILL_TYPE_NAME)
    try:
        pattern = slab_marks.hatch_pattern(doc)
        if pattern is not None:
            created.ForegroundPatternId = pattern.Id
        created.ForegroundPatternColor = Color(*FILL_COLOR)
        created.BackgroundPatternId = ElementId.InvalidElementId
    except Exception:
        pass
    return created, None


def elevation_base(doc, mode):
    """(отметка базы в мм внутренних координат, её собственная отметка в мм) для core.elevation_mm."""
    if mode == "internal":
        return 0.0, 0.0
    try:
        point = BasePoint.GetProjectBasePoint(doc)
        shared = mm(point.SharedPosition.Z) if mode == "shared" else 0.0
        return mm(point.Position.Z), shared
    except Exception:
        return 0.0, 0.0


# ------------------------------------------------------------
# План
# ------------------------------------------------------------

def _comment_of(element):
    return _comment(element) or u""


def clear_view(doc, view, note_type, spot):
    """Удалить с вида отметки, тексты и заливки прошлого запуска."""
    from System.Collections.Generic import List
    ids = List[ElementId]()
    for note in FilteredElementCollector(doc, view.Id).OfClass(TextNote):
        if note.GetTypeId() == note_type.Id:
            ids.Add(note.Id)
    if spot is not None:
        for dimension in FilteredElementCollector(doc, view.Id).OfClass(SpotDimension):
            if dimension.GetTypeId() == spot.Id:
                ids.Add(dimension.Id)
    for region in FilteredElementCollector(doc, view.Id).OfClass(FilledRegion):
        if _comment_of(region).startswith(REGION_TAG):
            ids.Add(region.Id)
    if ids.Count:
        doc.Delete(ids)
    return ids.Count


class ViewResult(object):
    def __init__(self, view):
        self.view = view
        self.parking = 0
        self.zones = 0
        self.spots = 0
        self.texts = 0
        self.fills = 0
        self.spot_errors = []     # (элемент, причина) — вместо отметки текст
        self.no_prefix = False    # Revit не дал задать префикс высотной отметке
        self.errors = []


def _place_spot(doc, view, item, face, point, spot, template, result):
    """Высотная отметка на грани элемента связи; False — не вышло (причина в result)."""
    try:
        reference = face.face.Reference
        if reference is None:
            raise ValueError(u"у грани нет ссылки")
        reference = reference.CreateLinkReference(item.link)
        dimension = doc.Create.NewSpotElevation(view, reference, point, point, point, point, False)
        if dimension is None:
            raise ValueError(u"Revit не создал отметку")
    except Exception as ex:
        result.spot_errors.append((item.label, u"{}".format(ex)))
        return False
    try:
        if spot is not None:
            dimension.ChangeTypeId(spot.Id)
    except Exception:
        pass
    prefix, suffix = core.split_template(template)
    try:
        dimension.Prefix = prefix
        dimension.Suffix = suffix
    except Exception:
        if prefix or suffix:
            result.no_prefix = True
    result.spots += 1
    return True


def _place_text(doc, view, point, text, note_type, result, item):
    try:
        TextNote.Create(doc, view.Id, point, text.replace(u"\n", u"\r"), note_type.Id)
        result.texts += 1
    except Exception as ex:
        result.errors.append(u"{}: текст — {}".format(item.label, ex))


def _bottom_point(item, offset_ft, up):
    """Точка низа зоны: со сдвигом от отметки верха вниз по листу (иначе вверх, иначе там же)."""
    face = item.bottom_face
    x, y = item.anchor.X, item.anchor.Y
    for sign in (-1.0, 1.0):
        point = face.point_at(x + up.X * offset_ft * sign, y + up.Y * offset_ft * sign)
        if point is not None:
            return point
    return face.point_at(x, y) or face.inner_point()


def annotate_view(doc, view, items, settings, note_type, spot, zone_fill, zone_fill_error=None):
    """Отметки и заливки зон на плане по элементам collect(); ViewResult."""
    result = ViewResult(view)
    clear_view(doc, view, note_type, spot)

    level_z = view.GenLevel.ProjectElevation
    base_z, base_shared = elevation_base(doc, settings.get("elevation_base") or "project")
    # без своего типа отметки повторный запуск не нашёл бы их — тогда текстом
    use_spots = spot is not None and (settings.get("mark_mode") or "spot") == "spot"
    top_format = settings.get("top_text_format") or u"{h}"
    zone_top_format = settings.get("zone_top_text_format") or u"Верх зоны {h}"
    zone_bottom_format = settings.get("zone_bottom_text_format") or u"Низ зоны {h}"
    try:
        up = view.UpDirection
        offset_ft = ft(LABEL_GAP_MM * view.Scale)
    except Exception:
        up, offset_ft = XYZ(0, 1, 0), ft(LABEL_GAP_MM * 100)

    def value(z):
        return core.elevation_mm(mm(z), base_z, base_shared)

    def text_point(point):
        return XYZ(point.X, point.Y, level_z)

    for item in items:
        anchor = item.anchor
        if not item.zone:
            result.parking += 1
            if not (use_spots and item.top_face is not None and
                    _place_spot(doc, view, item, item.top_face, anchor, spot, top_format, result)):
                _place_text(doc, view, text_point(anchor), core.label(top_format, value(item.top_z)),
                            note_type, result, item)
            continue

        result.zones += 1
        top_done = bottom_done = False
        if use_spots and item.top_face is not None and item.bottom_face is not None:
            top_done = _place_spot(doc, view, item, item.top_face, anchor, spot,
                                   zone_top_format, result)
            if top_done:
                bottom = _bottom_point(item, offset_ft, up)
                bottom_done = bottom is not None and _place_spot(
                    doc, view, item, item.bottom_face, bottom, spot, zone_bottom_format, result)
        if not top_done:
            _place_text(doc, view, text_point(anchor),
                        core.zone_label(zone_top_format, zone_bottom_format,
                                        value(item.top_z), value(item.bottom_z)),
                        note_type, result, item)
        elif not bottom_done:
            shifted = XYZ(anchor.X - up.X * offset_ft, anchor.Y - up.Y * offset_ft, level_z)
            _place_text(doc, view, shifted, core.label(zone_bottom_format, value(item.bottom_z)),
                        note_type, result, item)

        if zone_fill is None:
            if zone_fill_error and zone_fill_error not in result.errors:
                result.errors.append(u"штриховка зон: " + zone_fill_error)
            continue
        region, error = _zone_region(doc, view, item, zone_fill, level_z)
        if region is None:
            result.errors.append(u"{}: штриховка — {}".format(item.label, error))
            continue
        try:
            param = region.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if param is not None and not param.IsReadOnly:
                param.Set(u"{} {}".format(REGION_TAG, item.label))
        except Exception:
            pass
        result.fills += 1
    return result


def _box_loop(item, z):
    """Прямоугольник габарита элемента (с поворотом связи и семейства) на отметке z."""
    bottom = sorted(item.corners, key=lambda p: p.Z)[:4]
    if len(bottom) < 4:
        return None
    center = XYZ(sum(p.X for p in bottom) / 4.0, sum(p.Y for p in bottom) / 4.0, 0)
    bottom.sort(key=lambda p: math.atan2(p.Y - center.Y, p.X - center.X))
    points = [XYZ(p.X, p.Y, z) for p in bottom]
    loop = CurveLoop()
    for i in range(4):
        loop.Append(Line.CreateBound(points[i], points[(i + 1) % 4]))
    return loop


def _zone_region(doc, view, item, region_type, z):
    """(область заливки по контуру зоны, ошибка): самая большая горизонтальная
    грань, не вышло — прямоугольник габарита."""
    from System.Collections.Generic import List
    last_error = None
    attempts = []
    if item.outline_face is not None:
        attempts.append(lambda: item.outline_face.loops(z))
    attempts.append(lambda: [_box_loop(item, z)])
    for build in attempts:
        try:
            loops = [loop for loop in build() if loop is not None]
            if not loops:
                continue
            return FilledRegion.Create(doc, region_type.Id, view.Id, List[CurveLoop](loops)), None
        except Exception as ex:
            last_error = ex
    return None, u"{}".format(last_error)
