# -*- coding: utf-8 -*-
"""
Кнопка «Извещатели на перекрытие» (SPS.panel/DetectorsToSlab). Revit-часть;
чистая логика — slab_marks_core.py, настройки — slab_marks_settings.py.

Что делает:
  1. move_detectors — каждый пожарный извещатель (категория «Пожарная
     сигнализация», отбор по словам в имени семейства/типа) поднимается или
     опускается так, чтобы точка вставки встала на низ перекрытия над ним.
     Перекрытие ищется лучом вверх (ReferenceIntersector по временному
     3D-виду, с элементами связей АР/КР) из точки над уровнем извещателя —
     поэтому разные отметки перекрытий в здании учитываются сами.
  2. annotate_view — на плане для каждого помещения (связей и модели) на
     уровне вида — подпись высоты низа перекрытия от пола (пол — ближайшее
     перекрытие под точкой), «Δ» — на сколько перекрытие выше/ниже типового
     для этого вида, а в помещениях с подвесным потолком — область заливки
     по контуру помещения и подпись «ПП» с высотой потолка от пола.
     Перепады плиты — толстые красные линии детализации (draw_steps) там,
     где сходятся края нижних граней перекрытий с разной отметкой.
     Повторный запуск заменяет подписи, области и линии прошлого запуска на виде.

Вызывать внутри одной открытой транзакции (временный 3D-вид создаётся и
удаляется в ней же — SlabProbe.close()).
"""

from Autodesk.Revit.DB import (
    XYZ, Line, CurveLoop, ElementId, FilteredElementCollector, BuiltInCategory,
    BuiltInParameter, FamilyInstance, LocationPoint, Level, ViewPlan, TextNote, TextNoteType,
    FilledRegion, FilledRegionType, ElementTypeGroup, ElementTransformUtils,
    SpatialElementBoundaryOptions, CurveElement, GraphicsStyleType, Color, Options,
    ViewDetailLevel, Solid, GeometryInstance, PlanarFace, RevitLinkInstance, Transform
)

from lowlife import slab_marks_core as core
from lowlife.scs import safe_element_name
from lowlife.soue_floor import room_sources, room_name

FT_TO_MM = 304.8

# Тип текста подписей (создаётся копией типа текста по умолчанию). По нему
# повторный запуск находит и удаляет подписи прошлого запуска на виде.
TEXT_TYPE_NAME = u"LowLife — отметки перекрытий"

# Метка в «Комментариях» областей заливки подвесного потолка.
REGION_TAG = u"LowLife ПП"

# Стиль линий перепада плиты (подкатегория «Линии», красная, толстая). По нему
# повторный запуск находит и удаляет линии прошлого запуска на виде.
STEP_LINE_STYLE = u"LowLife — перепад плиты"
STEP_LINE_COLOR = (255, 0, 0)

# Перепад плиты: отметки, различающиеся меньше, — одна плита; края короче — не линия.
STEP_MIN_DZ_MM = 20.0
STEP_MIN_LEN_MM = 100.0

# Расхождение после перемещения, при котором извещатель считается не сдвинутым.
MOVE_TOLERANCE_MM = 5.0

# Отрезки контура помещения короче этого не строятся (меньше допуска Revit).
_MIN_SEG_FT = 0.01


def mm(value_ft):
    return value_ft * FT_TO_MM


def ft(value_mm):
    return float(value_mm) / FT_TO_MM


# ------------------------------------------------------------
# Луч вверх/вниз
# ------------------------------------------------------------

class SlabProbe(object):
    """
    Лучи вверх и вниз из точки (ReferenceIntersector по временному 3D-виду,
    с элементами связей): перекрытия («Перекрытия», «Крыши») и подвесные
    потолки («Потолки»). Вид создаётся при первом запросе; close() удаляет
    его в той же транзакции.

    Скорость: на виде скрыты все категории модели, кроме перекрытий, крыш,
    потолков и связей, — луч иначе собирает попадания во всё подряд
    (мебель, трубы, воздуховоды, оборудование во всех связях), и на сотнях
    точек это основное время. Результаты кэшируются по точке (повторные
    запросы той же точки — подпись помещения, проверка перепада).
    """

    _VISIBLE = (
        BuiltInCategory.OST_Floors, BuiltInCategory.OST_Roofs,
        BuiltInCategory.OST_Ceilings, BuiltInCategory.OST_RvtLinks,
    )

    _KINDS = {
        int(BuiltInCategory.OST_Floors): core.SLAB,
        int(BuiltInCategory.OST_Roofs): core.SLAB,
        int(BuiltInCategory.OST_Ceilings): core.CEILING,
    }

    def __init__(self, doc, opening_size_mm=0.0):
        self.doc = doc
        # Отверстия в перекрытии (шахты, проёмы): луч проходит насквозь до
        # плиты следующих этажей. Если найденная плита выше следующего уровня,
        # проверяются 4 точки на этом расстоянии вокруг (см. _check_opening).
        # 0 — не проверять.
        self.opening_ft = ft(opening_size_mm or 0.0)
        self._levels = None
        self.view = None
        self.intersector = None
        self.error = None
        self._cache = {}
        # Перекрытия, в которые лучи упёрлись как в ближайшие сверху, по
        # уровню, от которого шёл луч: {отметка уровня, мм: {(Id связи или -1
        # для модели, Id элемента)}} — по ним ищутся перепады (slabs_above).
        self.slab_elements = {}
        self.openings = 0  # точек над отверстиями в перекрытии (для отчёта)

    def _hide_other_categories(self):
        from Autodesk.Revit.DB import CategoryType
        keep = set(int(c) for c in self._VISIBLE)
        for category in self.doc.Settings.Categories:
            try:
                if category.CategoryType != CategoryType.Model:
                    continue
                if category.Id.IntegerValue in keep:
                    continue
                if self.view.CanCategoryBeHidden(category.Id):
                    self.view.SetCategoryHidden(category.Id, True)
            except Exception:
                pass

    def _open(self):
        from Autodesk.Revit.DB import (
            View3D, ViewFamilyType, ViewFamily, ReferenceIntersector, FindReferenceTarget
        )
        vft = None
        for candidate in FilteredElementCollector(self.doc).OfClass(ViewFamilyType):
            if candidate.ViewFamily == ViewFamily.ThreeDimensional:
                vft = candidate
                break
        if vft is None:
            raise Exception(u"в проекте нет типа 3D-вида")
        self.view = View3D.CreateIsometric(self.doc, vft.Id)
        try:
            self.view.ViewTemplateId = ElementId.InvalidElementId
        except Exception:
            pass
        self._hide_other_categories()
        self.doc.Regenerate()
        self.intersector = ReferenceIntersector(self.view)
        self.intersector.TargetType = FindReferenceTarget.Face
        self.intersector.FindReferencesInRevitLinks = True

    def _kind(self, reference):
        """(вид попадания или None, ключ элемента (Id связи или -1, Id элемента))."""
        element = self.doc.GetElement(reference.ElementId)
        key = (-1, reference.ElementId.IntegerValue)
        if reference.LinkedElementId != ElementId.InvalidElementId:
            key = (reference.ElementId.IntegerValue, reference.LinkedElementId.IntegerValue)
            try:
                element = element.GetLinkDocument().GetElement(reference.LinkedElementId)
            except Exception:
                return None, key
        try:
            return self._KINDS.get(element.Category.Id.IntegerValue), key
        except Exception:
            return None, key

    def _hits(self, origin, direction):
        """[(расстояние мм, вид, ключ элемента)]."""
        hits = []
        for context in self.intersector.Find(origin, direction):
            kind, key = self._kind(context.GetReference())
            if kind is not None:
                hits.append((mm(context.Proximity), kind, key))
        return hits

    def _remember_slab(self, up_hits, level_z):
        best = None
        for distance, kind, key in up_hits:
            if kind == core.SLAB and distance > 0 and (best is None or distance < best[0]):
                best = (distance, key)
        if best is not None:
            self.slab_elements.setdefault(int(round(mm(level_z))), set()).add(best[1])

    def slabs_above(self, level_z, tolerance):
        """Перекрытия, найденные лучами от уровней не дальше tolerance (футы) от level_z."""
        result = set()
        for level_mm, keys in self.slab_elements.items():
            if abs(ft(level_mm) - level_z) <= tolerance + ft(1.0):
                result.update(keys)
        return result

    def _raw(self, x, y, origin_z, level_z):
        """(core.Probe или None, лучи вверх) без проверки отверстия; кэшируется."""
        key = (round(x, 3), round(y, 3), round(origin_z, 3), round(level_z, 3))
        if key in self._cache:
            return self._cache[key]
        if self.intersector is None:
            self._open()
        origin = XYZ(x, y, origin_z)
        up = self._hits(origin, XYZ.BasisZ)
        down = self._hits(origin, XYZ.BasisZ.Negate())
        found = core.probe(mm(origin_z), [h[:2] for h in up], [h[:2] for h in down], mm(level_z))
        self._cache[key] = (found, up)
        return found, up

    def _next_level_z(self, level_z):
        if self._levels is None:
            self._levels = [z for _level, z in plan_levels(self.doc)]
        for z in self._levels:
            if z > level_z + ft(1000.0):
                return z
        return None

    def _check_opening(self, found, x, y, origin_z, level_z):
        """
        Над точкой отверстие (шахта, проём)? Только если найденная плита выше
        следующего уровня — луч мог пройти сквозь перекрытие этого этажа.
        Тогда 4 точки вокруг на opening_ft: если везде плита ниже — отверстие,
        возвращается Probe с плитой вокруг него; иначе None (высокая зона).
        """
        if self.opening_ft <= 0 or found is None:
            return None
        next_z = self._next_level_z(level_z)
        if next_z is None or found.slab_z_mm <= mm(next_z):
            return None
        d = self.opening_ft
        around = []
        for dx, dy in ((d, 0), (-d, 0), (0, d), (0, -d)):
            neighbor, _up = self._raw(x + dx, y + dy, origin_z, level_z)
            around.append(None if neighbor is None else neighbor.slab_z_mm)
        slab_z = core.opening_slab_z(found.slab_z_mm, around)
        return None if slab_z is None else core.replace_slab(found, slab_z)

    def probe(self, x, y, origin_z, level_z):
        """
        core.Probe для точки (x, y) с началом лучей на высоте origin_z (футы)
        или None. Над отверстием — перекрытие вокруг отверстия
        (through_opening=True), плита сверху в поиск перепадов не идёт.
        """
        if self.error is not None:
            return None
        try:
            found, up = self._raw(x, y, origin_z, level_z)
            opening = self._check_opening(found, x, y, origin_z, level_z)
        except Exception as ex:
            self.error = ex
            return None
        if opening is not None:
            self.openings += 1
            return opening
        self._remember_slab(up, level_z)
        return found

    def close(self):
        if self.view is not None:
            try:
                self.doc.Delete(self.view.Id)
            except Exception:
                pass
            self.view = None


# ------------------------------------------------------------
# Извещатели
# ------------------------------------------------------------

def _names(instance):
    names = []
    try:
        symbol = instance.Symbol
        names.append(safe_element_name(symbol.Family) or u"")
        names.append(safe_element_name(symbol) or u"")
    except Exception:
        pass
    return names


def _point(instance):
    try:
        location = instance.Location
        if isinstance(location, LocationPoint):
            return location.Point
    except Exception:
        pass
    return None


def plan_levels(doc):
    """Уровни модели по высоте: [(уровень, ProjectElevation в футах)]."""
    levels = [(level, level.ProjectElevation)
              for level in FilteredElementCollector(doc).OfClass(Level)]
    return sorted(levels, key=lambda item: item[1])


def level_of(doc, instance, levels):
    """(уровень, отметка) извещателя: его LevelId, иначе ближайший уровень снизу."""
    try:
        level = doc.GetElement(instance.LevelId)
    except Exception:
        level = None
    if isinstance(level, Level):
        return level, level.ProjectElevation
    point = _point(instance)
    if point is None or not levels:
        return None, None
    best = levels[0]
    for item in levels:
        if item[1] <= point.Z + 1e-6:
            best = item
    return best


def collect_detectors(doc, settings, element_ids=None):
    """Извещатели модели (или только из element_ids), подходящие по словам из настроек."""
    include = core.split_words(settings.get("detector_include_words"))
    exclude = core.split_words(settings.get("detector_exclude_words"))
    if element_ids:
        candidates = [doc.GetElement(element_id) for element_id in element_ids]
    else:
        candidates = (FilteredElementCollector(doc)
                      .OfCategory(BuiltInCategory.OST_FireAlarmDevices)
                      .WhereElementIsNotElementType())
    result = []
    for element in candidates:
        if not isinstance(element, FamilyInstance) or _point(element) is None:
            continue
        try:
            if element.Category.Id.IntegerValue != int(BuiltInCategory.OST_FireAlarmDevices):
                continue
        except Exception:
            continue
        if core.is_detector(_names(element), include, exclude):
            result.append(element)
    return result


class MoveResult(object):
    def __init__(self):
        self.moved = 0
        self.already = 0
        self.no_slab = []      # извещатели без перекрытия над ними
        self.failed = []       # (извещатель, причина)
        self.under_ceiling = 0  # извещателей над подвесным потолком (для отчёта)
        self.to_ceiling = 0     # встраиваемых, поставленных на подвесной потолок


def _writable(param):
    return param is not None and not param.IsReadOnly


def _shift(doc, instance, delta_ft):
    """Сдвиг точки вставки по Z: параметром смещения, иначе переносом. Ошибка — текст."""
    host = None
    try:
        host = instance.Host
    except Exception:
        pass
    face_hosted = False
    try:
        face_hosted = instance.HostFace is not None
    except Exception:
        pass
    if not face_hosted:
        for bip in (BuiltInParameter.INSTANCE_ELEVATION_PARAM,
                    BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM):
            param = instance.get_Parameter(bip)
            if _writable(param):
                try:
                    param.Set(param.AsDouble() + delta_ft)
                    return None
                except Exception:
                    pass
    try:
        ElementTransformUtils.MoveElement(doc, instance.Id, XYZ(0, 0, delta_ft))
        return None
    except Exception as ex:
        if face_hosted or host is not None:
            return u"размещён на грани/основе — сдвинуть по высоте нельзя ({})".format(ex)
        return u"{}".format(ex)


def move_detectors(doc, detectors, settings, probe, progress=None):
    """
    Поднять/опустить извещатели на низ перекрытия над ними; встраиваемые
    (слово из ceiling_mount_words в имени семейства/типа) — на низ
    подвесного потолка. Возвращает MoveResult.
    """
    result = MoveResult()
    levels = plan_levels(doc)
    probe_ft = ft(settings.get("probe_height_mm") or 1500.0)
    offset_mm = settings.get("mount_offset_mm") or 0.0
    ceiling_words = core.split_words(settings.get("ceiling_mount_words"))
    targets = []
    for index, detector in enumerate(detectors):
        if progress is not None:
            progress(index, len(detectors))
        point = _point(detector)
        _level, level_z = level_of(doc, detector, levels)
        if level_z is None:
            result.failed.append((detector, u"не определён уровень"))
            continue
        found = probe.probe(point.X, point.Y, level_z + probe_ft, level_z)
        if found is None:
            result.no_slab.append(detector)
            continue
        ceiling_mount = bool(ceiling_words) and core.is_detector(_names(detector), ceiling_words, [])
        surface_mm, skip = core.mount_surface(found, ceiling_mount)
        if skip:
            result.failed.append((detector, skip))
            continue
        if ceiling_mount:
            result.to_ceiling += 1
        elif found.ceiling_mm is not None:
            result.under_ceiling += 1
        # встраиваемый — точка вставки ровно в плоскости потолка, без отступа
        delta_mm = core.move_delta(mm(point.Z), surface_mm, 0.0 if ceiling_mount else offset_mm)
        if abs(delta_mm) < MOVE_TOLERANCE_MM:
            result.already += 1
            continue
        error = _shift(doc, detector, ft(delta_mm))
        if error:
            result.failed.append((detector, error))
        else:
            targets.append((detector, mm(point.Z) + delta_mm))
    if probe.error is not None:
        result.failed.append((None, u"луч к перекрытию: {}".format(probe.error)))
    if targets:
        doc.Regenerate()
    for detector, target_mm in targets:
        point = _point(detector)
        if point is not None and abs(mm(point.Z) - target_mm) < MOVE_TOLERANCE_MM:
            result.moved += 1
        else:
            result.failed.append((detector, u"Revit не сдвинул элемент по высоте (размещён на грани?)"))
    return result


# ------------------------------------------------------------
# Подписи на плане
# ------------------------------------------------------------

def is_plan(view):
    try:
        return (isinstance(view, ViewPlan) and not view.IsTemplate
                and view.GenLevel is not None)
    except Exception:
        return False


def text_type(doc):
    """Тип текста подписей (TEXT_TYPE_NAME), создаётся копией типа по умолчанию."""
    for candidate in FilteredElementCollector(doc).OfClass(TextNoteType):
        if safe_element_name(candidate) == TEXT_TYPE_NAME:
            return candidate
    base = doc.GetElement(doc.GetDefaultElementTypeId(ElementTypeGroup.TextNoteType))
    if base is None:
        base = FilteredElementCollector(doc).OfClass(TextNoteType).FirstElement()
    return base.Duplicate(TEXT_TYPE_NAME)


def region_type(doc, name):
    """Тип области заливки по имени, иначе первый немаскирующий; None — нет ни одного."""
    types = list(FilteredElementCollector(doc).OfClass(FilledRegionType))
    name = (name or u"").strip()
    if name:
        for candidate in types:
            if safe_element_name(candidate) == name:
                return candidate
    for candidate in types:
        try:
            if not candidate.IsMasking:
                return candidate
        except Exception:
            return candidate
    return types[0] if types else None


def _comment(element):
    try:
        param = element.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        return param.AsString() if param is not None else None
    except Exception:
        return None


def step_line_style(doc, weight):
    """GraphicsStyle линий перепада (STEP_LINE_STYLE): создаётся при отсутствии,
    цвет и толщина выставляются на каждом запуске. None — не удалось."""
    try:
        categories = doc.Settings.Categories
        lines = categories.get_Item(BuiltInCategory.OST_Lines)
        sub = None
        for candidate in lines.SubCategories:
            if candidate.Name == STEP_LINE_STYLE:
                sub = candidate
                break
        if sub is None:
            sub = categories.NewSubcategory(lines, STEP_LINE_STYLE)
        try:
            sub.LineColor = Color(*STEP_LINE_COLOR)
            sub.SetLineWeight(int(weight), GraphicsStyleType.Projection)
        except Exception:
            pass
        return sub.GetGraphicsStyle(GraphicsStyleType.Projection)
    except Exception:
        return None


def _line_style_name(curve_element):
    try:
        style = curve_element.LineStyle
        return safe_element_name(style) if style is not None else None
    except Exception:
        return None


def clear_view(doc, view, note_type):
    """Удалить с вида подписи, области заливки и линии перепада прошлого запуска."""
    from System.Collections.Generic import List
    ids = List[ElementId]()
    for note in FilteredElementCollector(doc, view.Id).OfClass(TextNote):
        if note.GetTypeId() == note_type.Id:
            ids.Add(note.Id)
    for curve in FilteredElementCollector(doc, view.Id).OfClass(CurveElement):
        if _line_style_name(curve) == STEP_LINE_STYLE:
            ids.Add(curve.Id)
    for region in FilteredElementCollector(doc, view.Id).OfClass(FilledRegion):
        if (_comment(region) or u"").startswith(REGION_TAG):
            ids.Add(region.Id)
    if ids.Count:
        doc.Delete(ids)
    return ids.Count


class RoomMark(object):
    """Помещение на виде: точки проверки и их Probe, контур, место подписи."""

    def __init__(self, source, room, name):
        self.source = source
        self.room = room
        self.name = name
        self.probes = []
        self.anchor = None

    def slab_values(self):
        return [p.slab_mm for p in self.probes]

    def ceiling_values(self):
        return [p.ceiling_mm for p in self.probes]


def _room_level_z(source, room):
    """Отметка уровня помещения в координатах модели (футы) или None."""
    try:
        level = source.doc.GetElement(room.LevelId)
        z = level.ProjectElevation
    except Exception:
        return None
    return source.transform.OfPoint(XYZ(0, 0, z)).Z


def _room_points(room, level_z_link, probe_ft):
    """Точки внутри помещения (координаты его документа): точка помещения + сетка до 3×3."""
    test_z = level_z_link + min(probe_ft, ft(1000.0))
    points = []
    try:
        location = room.Location.Point
        if room.IsPointInRoom(XYZ(location.X, location.Y, test_z)):
            points.append(XYZ(location.X, location.Y, test_z))
    except Exception:
        pass
    bbox = room.get_BoundingBox(None)
    if bbox is None:
        return points
    nx = core.grid_steps(mm(bbox.Max.X - bbox.Min.X))
    ny = core.grid_steps(mm(bbox.Max.Y - bbox.Min.Y))
    for i in range(nx):
        for j in range(ny):
            x = bbox.Min.X + (bbox.Max.X - bbox.Min.X) * (i + 0.5) / nx
            y = bbox.Min.Y + (bbox.Max.Y - bbox.Min.Y) * (j + 0.5) / ny
            point = XYZ(x, y, test_z)
            try:
                if room.IsPointInRoom(point):
                    points.append(point)
            except Exception:
                pass
    return points


def _boundary_loops(room, transform, z):
    """CurveLoop'ы контура помещения в координатах модели на высоте z."""
    loops = []
    try:
        segments_loops = room.GetBoundarySegments(SpatialElementBoundaryOptions())
    except Exception:
        segments_loops = None
    for segments in segments_loops or []:
        points = []
        for segment in segments:
            try:
                tessellated = list(segment.GetCurve().Tessellate())
            except Exception:
                continue
            for p in tessellated:
                p = transform.OfPoint(p)
                p = XYZ(p.X, p.Y, z)
                if not points or points[-1].DistanceTo(p) > _MIN_SEG_FT:
                    points.append(p)
        if len(points) >= 2 and points[0].DistanceTo(points[-1]) <= _MIN_SEG_FT:
            points.pop()
        if len(points) < 3:
            continue
        loop = CurveLoop()
        try:
            for i in range(len(points)):
                loop.Append(Line.CreateBound(points[i], points[(i + 1) % len(points)]))
        except Exception:
            continue
        loops.append(loop)
    return loops


def _filled_region(doc, view, region_type_id, room, transform, z):
    from System.Collections.Generic import List
    last_error = None
    for plane_z in (z, 0.0):
        loops = _boundary_loops(room, transform, plane_z)
        if not loops:
            return None, u"нет контура помещения"
        try:
            return FilledRegion.Create(doc, region_type_id, view.Id, List[CurveLoop](loops)), None
        except Exception as ex:
            last_error = ex
    return None, u"{}".format(last_error)


# ------------------------------------------------------------
# Перепады плиты
# ------------------------------------------------------------

def _model_sources(doc):
    """{Id связи или -1: (документ, преобразование в координаты модели)}."""
    sources = {-1: (doc, Transform.Identity)}
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        try:
            link_doc = link.GetLinkDocument()
        except Exception:
            link_doc = None
        if link_doc is not None:
            sources[link.Id.IntegerValue] = (link_doc, link.GetTotalTransform())
    return sources


def _solids(geometry, transform):
    """(Solid, преобразование в координаты модели) из геометрии элемента."""
    for item in geometry or []:
        if isinstance(item, Solid):
            if item.Faces.Size:
                yield item, transform
        elif isinstance(item, GeometryInstance):
            for nested in _solids(item.GetSymbolGeometry(),
                                  transform.Multiply(item.Transform)):
                yield nested


def slab_bottom_edges(doc, element_keys, bottom_z):
    """
    Края нижних горизонтальных граней перекрытий из element_keys
    ({(Id связи или -1, Id элемента)} — SlabProbe.slabs_above: только те
    плиты, в которые лучи с этого уровня упёрлись как в ближайшее перекрытие
    сверху), выше bottom_z (футы, координаты модели): [(x1, y1, x2, y2, z)]
    в мм. Все перекрытия связей не перебираются — иначе в кандидаты попадают
    отделка полов, плиты следующего этажа, пандусы, и поиск перепадов на
    большой модели длится часами. Верхней границы нет: плиты уже отобраны
    лучами, а высокие зоны (двусветные, техпространства) бывают выше
    следующего уровня.
    """
    options = Options()
    options.DetailLevel = ViewDetailLevel.Fine
    sources = _model_sources(doc)
    edges = []
    for source_key, element_id in sorted(element_keys):
        if source_key not in sources:
            continue
        source_doc, transform = sources[source_key]
        element = source_doc.GetElement(ElementId(element_id))
        if element is None:
            continue
        try:
            bbox = element.get_BoundingBox(None)
            z0 = transform.OfPoint(bbox.Min).Z
            z1 = transform.OfPoint(bbox.Max).Z
        except Exception:
            continue
        if max(z0, z1) < bottom_z:
            continue
        try:
            geometry = element.get_Geometry(options)
        except Exception:
            continue
        for solid, solid_transform in _solids(geometry, transform):
            for face in solid.Faces:
                if not isinstance(face, PlanarFace):
                    continue
                normal = solid_transform.OfVector(face.FaceNormal)
                if normal.Z > -0.99:
                    continue
                z = solid_transform.OfPoint(face.Origin).Z
                if z < bottom_z:
                    continue
                for loop in face.EdgeLoops:
                    for edge in loop:
                        points = [solid_transform.OfPoint(p)
                                  for p in edge.AsCurve().Tessellate()]
                        for a, b in zip(points, points[1:]):
                            edges.append((mm(a.X), mm(a.Y), mm(b.X), mm(b.Y), mm(z)))
    return edges


def _slab_mm_at(probe, x, y, level_z, probe_ft):
    found = probe.probe(x, y, level_z + probe_ft, level_z)
    return None if found is None else found.slab_z_mm


def draw_steps(doc, view, settings, probe, style):
    """
    Красные линии перепада плиты на плане: по краям нижних граней перекрытий
    над уровнем вида (slab_marks_core.step_segments); каждый кандидат
    проверяется лучами по обе стороны линии — там должны быть перекрытия
    с разной отметкой. Возвращает StepStats.
    """
    stats = StepStats()
    level_z = view.GenLevel.ProjectElevation
    probe_ft = ft(settings.get("probe_height_mm") or 1500.0)
    tol_mm = settings.get("step_search_mm") or 300.0
    slabs = probe.slabs_above(level_z, ft(settings.get("level_tolerance_mm") or 0.0))
    stats.slabs = len(slabs)
    edges = slab_bottom_edges(doc, slabs, level_z + probe_ft)
    stats.edges = len(edges)
    candidates = core.step_segments(edges, tol_mm, STEP_MIN_DZ_MM, STEP_MIN_LEN_MM)
    stats.candidates = len(candidates)
    side = tol_mm + 150.0
    for x1, y1, x2, y2, _dz in candidates:
        length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        nx, ny = -(y2 - y1) / length * side, (x2 - x1) / length * side
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        left = _slab_mm_at(probe, ft(mx + nx), ft(my + ny), level_z, probe_ft)
        right = _slab_mm_at(probe, ft(mx - nx), ft(my - ny), level_z, probe_ft)
        if left is None or right is None or abs(left - right) < STEP_MIN_DZ_MM:
            stats.rejected += 1
            continue
        try:
            line = Line.CreateBound(XYZ(ft(x1), ft(y1), level_z), XYZ(ft(x2), ft(y2), level_z))
            curve = doc.Create.NewDetailCurve(view, line)
            if style is not None:
                curve.LineStyle = style
            stats.drawn += 1
        except Exception as ex:
            stats.errors.append(u"линия перепада плиты — {}".format(ex))
    return stats


class StepStats(object):
    """Счётчики поиска перепадов — для отчёта (где отсеялись кандидаты)."""

    def __init__(self):
        self.slabs = 0        # плит, в которые упёрлись лучи с уровня
        self.edges = 0        # краёв их нижних граней
        self.candidates = 0   # пар краёв с разной отметкой рядом в плане
        self.rejected = 0     # кандидатов, не подтверждённых лучами по сторонам
        self.drawn = 0
        self.errors = []


class ViewResult(object):
    def __init__(self, view):
        self.view = view
        self.rooms = 0
        self.ceiling_rooms = 0
        self.steps = 0
        self.step_stats = None
        self.typical_mm = None
        self.changed = []      # (помещение, основная высота мм)
        self.no_slab = []      # имена помещений без перекрытия над ними
        self.errors = []


def annotate_view(doc, view, settings, probe, note_type, fill_type, step_style=None,
                  progress=None):
    """Подписи высот перекрытий и подвесных потолков в помещениях уровня вида. ViewResult."""
    result = ViewResult(view)
    clear_view(doc, view, note_type)

    level_z = view.GenLevel.ProjectElevation
    tolerance = ft(settings.get("level_tolerance_mm") or 0.0)
    probe_ft = ft(settings.get("probe_height_mm") or 1500.0)
    step = settings.get("round_mm") or 10.0

    marks = []
    for source in room_sources(doc):
        for room in source.rooms():
            room_z = _room_level_z(source, room)
            if room_z is None or abs(room_z - level_z) > tolerance + 1e-6:
                continue
            link_level_z = source.doc.GetElement(room.LevelId).ProjectElevation
            mark = RoomMark(source, room, room_name(room))
            for point in _room_points(room, link_level_z, probe_ft):
                host = source.transform.OfPoint(point)
                found = probe.probe(host.X, host.Y, room_z + probe_ft, room_z)
                if mark.anchor is None:
                    mark.anchor = XYZ(host.X, host.Y, level_z)
                if found is not None:
                    mark.probes.append(found)
            if mark.anchor is not None:
                marks.append(mark)

    result.typical_mm = core.typical_height(
        [core.main_height(m.slab_values(), step) for m in marks], step)

    for index, mark in enumerate(marks):
        if progress is not None:
            progress(index, len(marks))
        if not mark.probes:
            result.no_slab.append(mark.name)
            continue
        text = core.room_label(
            mark.slab_values(), mark.ceiling_values(), result.typical_mm, step,
            settings.get("slab_text_format") or u"{h}",
            settings.get("ceiling_text_format") or u"ПП {h}",
            settings.get("delta_text_format") or u"Δ {d}",
        )
        if not text:
            continue
        try:
            # абзацы текста Revit разделяет «\r»
            TextNote.Create(doc, view.Id, mark.anchor, text.replace(u"\n", u"\r"), note_type.Id)
            result.rooms += 1
        except Exception as ex:
            result.errors.append(u"{}: подпись — {}".format(mark.name, ex))
        main = core.main_height(mark.slab_values(), step)
        if result.typical_mm is not None and main is not None and main != result.typical_mm:
            result.changed.append((mark.name, main))
        if core.has_ceiling(mark.ceiling_values()):
            if fill_type is None:
                result.errors.append(u"{}: в проекте нет типа области заливки".format(mark.name))
                continue
            region, error = _filled_region(doc, view, fill_type.Id, mark.room,
                                           mark.source.transform, level_z)
            if region is None:
                result.errors.append(u"{}: область заливки — {}".format(mark.name, error))
                continue
            param = region.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if _writable(param):
                param.Set(u"{} {}".format(REGION_TAG, mark.name))
            result.ceiling_rooms += 1
    try:
        result.step_stats = draw_steps(doc, view, settings, probe, step_style)
        result.steps = result.step_stats.drawn
        result.errors.extend(result.step_stats.errors)
    except Exception as ex:
        result.errors.append(u"перепады плиты — {}".format(ex))
    if probe.error is not None:
        result.errors.append(u"луч к перекрытию: {}".format(probe.error))
    return result
