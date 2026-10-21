# -*- coding: utf-8 -*-
"""
Кнопка «Отметки парковки» (Tools.panel/ParkingMarks). Revit-часть; чистая
логика — parking_marks_core.py, настройки — parking_marks_settings.py.

Что делает на плане:
  1. collect — элементы категории «Парковка» из всех загруженных связей,
     видимых на виде и попадающих в его диапазон (от глубины просмотра до
     верхней секущей плоскости) и в подрезку. Верх/низ — по горизонтальным
     граням геометрии элемента, без граней — по габариту. Группа (зона
     светильников, проезд, машиноместо, прочее) — по словам в «Комментариях»,
     имени рабочего набора и имени семейства/типа (core.classify).
  2. annotate_view — подпись с отметками верха/низа от уровня плана (текстом,
     по шаблону группы; подписи, попавшие в одно место, склеиваются в одну),
     у групп со штриховкой — область заливки по контуру элемента.
     Повторный запуск заменяет подписи и заливки прошлого запуска.

Вызывать внутри открытой транзакции.
"""

import math

from Autodesk.Revit.DB import (
    XYZ, Line, CurveLoop, ElementId, FilteredElementCollector, BuiltInCategory,
    BuiltInParameter, Level, TextNote, FilledRegion, FilledRegionType,
    Options, ViewDetailLevel, Solid, GeometryInstance, PlanarFace, RevitLinkInstance,
    Transform, SpotDimension, SpotDimensionType, PlanViewPlane, Color, UV, SolidUtils
)

from lowlife import parking_marks_core as core
from lowlife import slab_marks
from lowlife.scs import safe_element_name, get_workset_name

FT_TO_MM = 304.8

# Тип текста подписей (копия типа по умолчанию): по нему повторный запуск
# находит и удаляет подписи прошлого запуска на виде.
TEXT_TYPE_NAME = u"LowLife — отметки парковки"
# Высотные отметки этого типа ставила первая версия кнопки — удаляются при запуске.
SPOT_TYPE_NAME = u"LowLife — отметки парковки"

# Типы заливки групп — «LowLife — <имя группы>»; метка в «Комментариях» областей.
FILL_TYPE_PREFIX = u"LowLife — "
REGION_TAG = u"LowLife парковка"

# Элемент берётся, если заходит за уровень плана и не доходит до следующего хотя бы на столько.
LEVEL_TOLERANCE_MM = 100.0
# Уровень ближе этого над планом — не следующий этаж, а часть того же этажа на другой отметке.
MIN_FLOOR_MM = 2500.0

# Подписи, точки которых ближе этого (мм на листе), склеиваются в одну.
MERGE_MM = 8.0

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


def solid_faces(solid, solid_transform):
    """Горизонтальные плоские грани тела (HFace)."""
    faces = []
    for face in solid.Faces:
        if not isinstance(face, PlanarFace):
            continue
        normal = solid_transform.OfVector(face.FaceNormal)
        if abs(normal.Z) < _HORIZONTAL:
            continue
        z = solid_transform.OfPoint(face.Origin).Z
        faces.append(HFace(face, solid_transform, z, normal.Z > 0))
    return faces


def _solid_corners(solid, solid_transform):
    try:
        box = solid.GetBoundingBox()
        to_model = solid_transform.Multiply(box.Transform)
    except Exception:
        return []
    return [to_model.OfPoint(XYZ(x, y, z)) for x in (box.Min.X, box.Max.X)
            for y in (box.Min.Y, box.Max.Y) for z in (box.Min.Z, box.Max.Z)]


def element_bodies(element, transform):
    """[(горизонтальные грани, углы габарита в координатах модели)] — по
    одному на тело элемента (модель в контексте бывает из нескольких
    отдельных зон; составное тело делится SolidUtils.SplitVolumes)."""
    options = Options()
    options.DetailLevel = ViewDetailLevel.Fine
    bodies = []
    for solid, solid_transform in _solids(element.get_Geometry(options), transform):
        try:
            parts = list(SolidUtils.SplitVolumes(solid)) or [solid]
        except Exception:
            parts = [solid]
        for part in parts:
            corners = _solid_corners(part, solid_transform)
            if corners:
                bodies.append((solid_faces(part, solid_transform), corners))
    return bodies


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


def _family_and_type(element):
    try:
        param = element.get_Parameter(BuiltInParameter.ELEM_FAMILY_AND_TYPE_PARAM)
        return param.AsValueString() if param is not None else None
    except Exception:
        return None


def match_text(element):
    """Текст, в котором ищутся слова групп: комментарий, рабочий набор, семейство и тип."""
    parts = [_comment(element), get_workset_name(element), _family_and_type(element)]
    return u" | ".join(p for p in parts if p)


class ParkingItem(object):
    """Элемент «Парковка» связи: верх/низ (футы, координаты модели), грани, группа."""

    def __init__(self, link, link_name, element, transform, group):
        self.link = link
        self.link_name = link_name
        self.element = element
        self.transform = transform
        self.group = group
        self.top_face = None
        self.outline_faces = []   # грани контура для штриховки (по одной на тело)
        self.corners = []
        self.part = None          # номер части элемента (из нескольких тел) или None
        self.top_z = None
        self.bottom_z = None
        self.anchor = None  # точка подписи (координаты модели)

    @property
    def label(self):
        part = u", часть {}".format(self.part) if self.part else u""
        return u"{}: {} (Id {}{})".format(self.link_name, _family_and_type(self.element) or u"",
                                         self.element.Id.IntegerValue, part)

    def xy_range(self):
        xs = [p.X for p in self.corners]
        ys = [p.Y for p in self.corners]
        return min(xs), min(ys), max(xs), max(ys)


def _xy_box(corners):
    return (min(p.X for p in corners), min(p.Y for p in corners),
            max(p.X for p in corners), max(p.Y for p in corners))


def make_items(link, link_name, element, transform, group):
    """ParkingItem на каждую зону элемента: тела, пересекающиеся в плане, —
    одна зона (машина внутри машиноместа), отдельно стоящие — разные.
    [] — у элемента нет ни геометрии, ни габарита."""
    try:
        bodies = element_bodies(element, transform)
    except Exception:
        bodies = []
    if not bodies:
        corners = _box_corners(element, transform)
        return [_item(link, link_name, element, transform, group, [[]], [corners])] if corners else []
    clusters = core.group_boxes([_xy_box(c) for _f, c in bodies], _SAME_Z_FT)
    items = []
    for index, members in enumerate(clusters):
        item = _item(link, link_name, element, transform, group,
                     [bodies[i][0] for i in members], [bodies[i][1] for i in members])
        if len(clusters) > 1:
            item.part = index + 1
        items.append(item)
    return items


def _item(link, link_name, element, transform, group, body_faces, body_corners):
    item = ParkingItem(link, link_name, element, transform, group)
    faces = [f for fs in body_faces for f in fs]
    item.corners = [p for cs in body_corners for p in cs]
    item.top_z = max(p.Z for p in item.corners)
    item.bottom_z = min(p.Z for p in item.corners)
    item.top_face = _extreme([f for f in faces if f.up], True)
    bottom_face = _extreme([f for f in faces if not f.up], False)
    if item.top_face is not None:
        item.top_z = item.top_face.z
    if bottom_face is not None:
        item.bottom_z = bottom_face.z
    # контур — самая большая горизонтальная грань каждого тела, кроме тел,
    # целиком лежащих в плане внутри другого (машина внутри машиноместа)
    # (body_faces и body_corners — по элементу на тело; у элемента без тел — [[]] и габарит)
    largest = [max(fs, key=lambda f: f.area) if fs else None for fs in body_faces]
    keep = core.outer_boxes([_xy_box(cs) for cs in body_corners])
    item.outline_faces = [largest[i] for i in keep if i < len(largest) and largest[i] is not None]
    outline = max(item.outline_faces, key=lambda f: f.area) if item.outline_faces else None
    x0, y0, x1, y1 = item.xy_range()
    point = None
    for face in (outline, item.top_face):
        if face is not None and point is None:
            point = face.point_at((x0 + x1) / 2.0, (y0 + y1) / 2.0) or face.inner_point()
    item.anchor = point or XYZ((x0 + x1) / 2.0, (y0 + y1) / 2.0, item.top_z)
    return item


# ------------------------------------------------------------
# Что видно на плане
# ------------------------------------------------------------

def view_z_range(doc, view):
    """(низ, верх) отметок, в которых ищутся элементы, в футах модели —
    core.floor_range: от уровня плана до следующего этажа (уровни ближе
    MIN_FLOOR_MM — часть того же этажа на другой отметке), но не ниже верха
    секущего диапазона вида. Только по секущему диапазону нельзя: его верх по
    умолчанию — уровень +2300, а зона светильников выше."""
    level_z = view.GenLevel.ProjectElevation
    levels = [mm(level.ProjectElevation) for level in FilteredElementCollector(doc).OfClass(Level)]
    bottom, top = core.floor_range(mm(level_z), levels, _top_clip_mm(doc, view),
                                   LEVEL_TOLERANCE_MM, MIN_FLOOR_MM)
    return ft(bottom), (ft(top) if top is not None else None)


def _top_clip_mm(doc, view):
    """Верх секущего диапазона вида, мм; None — не задан уровнем (неограниченный)."""
    try:
        view_range = view.GetViewRange()
        level = doc.GetElement(view_range.GetLevelId(PlanViewPlane.TopClipPlane))
        if isinstance(level, Level):
            return mm(level.ProjectElevation + view_range.GetOffset(PlanViewPlane.TopClipPlane))
    except Exception:
        pass
    return None


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


def group_words(settings):
    """[(ключ группы, [слова]), ...] в порядке core.GROUPS."""
    result = []
    for group in core.GROUPS:
        words = settings.get(group.key + "_words")
        result.append((group.key, core.split_words(group.words if words is None else words)))
    return result


class Collected(object):
    def __init__(self):
        self.items = []
        self.links = []           # имена связей, в которых искали
        self.unloaded = []        # имена выгруженных связей
        self.hidden_links = []    # скрытых на виде (всё равно проверены)
        self.skipped = []         # (группа, подпись, низ мм, верх мм от уровня, причина)
        self.no_geometry = []     # подписи элементов без геометрии
        self.category_hidden = False


def collect(doc, view, settings):
    result = Collected()
    try:
        result.category_hidden = view.GetCategoryHidden(ElementId(BuiltInCategory.OST_Parking))
    except Exception:
        pass
    words = group_words(settings)
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
        # скрытая на плане связь тоже проверяется: зоны светильников бывают
        # в модели, которую на плане не показывают
        try:
            if link.IsHidden(view):
                result.hidden_links.append(name)
        except Exception:
            pass
        result.links.append(name)
        transform = link.GetTotalTransform()
        elements = (FilteredElementCollector(link_doc).OfCategory(BuiltInCategory.OST_Parking)
                    .WhereElementIsNotElementType())
        for element in elements:
            group = core.classify(match_text(element), words) or core.OTHER.key
            items = make_items(link, name, element, transform, group)
            if not items:
                result.no_geometry.append(u"{}: Id {}".format(name, element.Id.IntegerValue))
            for item in items:
                reason = None
                if not core.overlaps(item.bottom_z, item.top_z, bottom, top):
                    reason = u"не на этом этаже"
                elif not _in_crop(view, item):
                    reason = u"вне подрезки вида"
                if reason is not None:
                    level_z = view.GenLevel.ProjectElevation
                    result.skipped.append((group, item.label, mm(item.bottom_z - level_z),
                                           mm(item.top_z - level_z), reason))
                    continue
                result.items.append(item)
    return result


# ------------------------------------------------------------
# Типы
# ------------------------------------------------------------

def text_type(doc):
    return slab_marks.text_type(doc, TEXT_TYPE_NAME)


def fill_type(doc, group):
    """(тип заливки группы «LowLife — <имя>», ошибка): создаётся при отсутствии
    копией первого немаскирующего типа, штриховка диагональная, цвет группы."""
    name = FILL_TYPE_PREFIX + group.name.lower()
    for candidate in FilteredElementCollector(doc).OfClass(FilledRegionType):
        if safe_element_name(candidate) == name:
            return candidate, None
    base = slab_marks.region_type(doc, None)
    if base is None:
        return None, u"в проекте нет ни одного типа области заливки"
    created = base.Duplicate(name)
    try:
        pattern = slab_marks.hatch_pattern(doc)
        if pattern is not None:
            created.ForegroundPatternId = pattern.Id
        created.ForegroundPatternColor = Color(*group.color)
        created.BackgroundPatternId = ElementId.InvalidElementId
    except Exception:
        pass
    return created, None


def group_by_key(key):
    for group in core.GROUPS + [core.OTHER]:
        if group.key == key:
            return group
    return core.OTHER


# ------------------------------------------------------------
# План
# ------------------------------------------------------------

def clear_view(doc, view, note_type):
    """Удалить с вида подписи, заливки и высотные отметки прошлых запусков."""
    from System.Collections.Generic import List
    ids = List[ElementId]()
    for note in FilteredElementCollector(doc, view.Id).OfClass(TextNote):
        if note.GetTypeId() == note_type.Id:
            ids.Add(note.Id)
    spot_ids = set(t.Id.IntegerValue for t in FilteredElementCollector(doc).OfClass(SpotDimensionType)
                   if safe_element_name(t) == SPOT_TYPE_NAME)
    if spot_ids:
        for dimension in FilteredElementCollector(doc, view.Id).OfClass(SpotDimension):
            if dimension.GetTypeId().IntegerValue in spot_ids:
                ids.Add(dimension.Id)
    for region in FilteredElementCollector(doc, view.Id).OfClass(FilledRegion):
        if (_comment(region) or u"").startswith(REGION_TAG):
            ids.Add(region.Id)
    if ids.Count:
        doc.Delete(ids)
    return ids.Count


class ViewResult(object):
    def __init__(self, view):
        self.view = view
        self.counts = {}          # ключ группы → элементов
        self.texts = 0
        self.fills = 0
        self.errors = []


def annotate_view(doc, view, items, settings, note_type):
    """Подписи отметок от уровня плана и заливки по элементам collect(); ViewResult."""
    result = ViewResult(view)
    clear_view(doc, view, note_type)
    level_z = view.GenLevel.ProjectElevation
    try:
        merge_ft = ft(MERGE_MM * view.Scale)
    except Exception:
        merge_ft = ft(MERGE_MM * 100)

    labels = []   # (точка, текст)
    fill_types = {}
    for item in items:
        group = group_by_key(item.group)
        result.counts[group.key] = result.counts.get(group.key, 0) + 1
        template = settings.get(group.key + "_text_format")
        if template is None:
            template = group.text_format
        if template.strip():
            labels.append((item.anchor, core.label(template, mm(item.top_z - level_z),
                                                   mm(item.bottom_z - level_z))))
        fill = settings.get(group.key + "_fill") or group.fill
        if group is core.OTHER or fill != "yes":
            continue
        if group.key not in fill_types:
            fill_types[group.key] = fill_type(doc, group)
        region_type, error = fill_types[group.key]
        if region_type is None:
            if u"штриховка: " + error not in result.errors:
                result.errors.append(u"штриховка: " + error)
            continue
        regions, error = _regions(doc, view, item, region_type, level_z)
        if not regions:
            result.errors.append(u"{}: штриховка — {}".format(item.label, error))
            continue
        for region in regions:
            try:
                param = region.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                if param is not None and not param.IsReadOnly:
                    param.Set(u"{} {}".format(REGION_TAG, group.name))
            except Exception:
                pass
        result.fills += 1

    # подписи в одном месте (зона светильников над проездом) — одной заметкой,
    # строки в порядке групп
    for indexes in core.cluster([(p.X, p.Y) for p, _t in labels], merge_ft):
        texts = []
        for index in indexes:
            if labels[index][1] not in texts:
                texts.append(labels[index][1])
        point = labels[indexes[0]][0]
        try:
            TextNote.Create(doc, view.Id, XYZ(point.X, point.Y, level_z),
                            u"\r".join(t.replace(u"\n", u"\r") for t in texts), note_type.Id)
            result.texts += 1
        except Exception as ex:
            result.errors.append(u"подпись — {}".format(ex))
    return result


def _box_loop(item, z):
    """Прямоугольник габарита элемента (с поворотом связи и семейства) на отметке z."""
    bottom = sorted(item.corners, key=lambda p: p.Z)[:4]
    if len(bottom) < 4:
        return None
    cx = sum(p.X for p in bottom) / 4.0
    cy = sum(p.Y for p in bottom) / 4.0
    bottom.sort(key=lambda p: math.atan2(p.Y - cy, p.X - cx))
    points = [XYZ(p.X, p.Y, z) for p in bottom]
    loop = CurveLoop()
    for i in range(4):
        loop.Append(Line.CreateBound(points[i], points[(i + 1) % 4]))
    return loop


def _regions(doc, view, item, region_type, z):
    """([области заливки по контурам тел зоны], ошибка): самая большая
    горизонтальная грань каждого тела, не вышло — прямоугольник габарита."""
    from System.Collections.Generic import List
    regions = []
    last_error = None
    for face in item.outline_faces:
        try:
            loops = face.loops(z)
            regions.append(FilledRegion.Create(doc, region_type.Id, view.Id, List[CurveLoop](loops)))
        except Exception as ex:
            last_error = ex
    if regions:
        return regions, None
    try:
        loop = _box_loop(item, z)
        if loop is not None:
            return [FilledRegion.Create(doc, region_type.Id, view.Id, List[CurveLoop]([loop]))], None
    except Exception as ex:
        last_error = ex
    return [], u"{}".format(last_error)
