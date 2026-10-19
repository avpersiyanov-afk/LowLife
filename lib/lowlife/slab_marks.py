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
     Повторный запуск заменяет подписи и области прошлого запуска на виде.

Вызывать внутри одной открытой транзакции (временный 3D-вид создаётся и
удаляется в ней же — SlabProbe.close()).
"""

from Autodesk.Revit.DB import (
    XYZ, Line, CurveLoop, ElementId, FilteredElementCollector, BuiltInCategory,
    BuiltInParameter, FamilyInstance, LocationPoint, Level, ViewPlan, TextNote, TextNoteType,
    FilledRegion, FilledRegionType, ElementTypeGroup, ElementTransformUtils,
    SpatialElementBoundaryOptions
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
    """

    _KINDS = {
        int(BuiltInCategory.OST_Floors): core.SLAB,
        int(BuiltInCategory.OST_Roofs): core.SLAB,
        int(BuiltInCategory.OST_Ceilings): core.CEILING,
    }

    def __init__(self, doc):
        self.doc = doc
        self.view = None
        self.intersector = None
        self.error = None

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
        self.doc.Regenerate()
        self.intersector = ReferenceIntersector(self.view)
        self.intersector.TargetType = FindReferenceTarget.Face
        self.intersector.FindReferencesInRevitLinks = True

    def _kind(self, reference):
        element = self.doc.GetElement(reference.ElementId)
        if reference.LinkedElementId != ElementId.InvalidElementId:
            try:
                element = element.GetLinkDocument().GetElement(reference.LinkedElementId)
            except Exception:
                return None
        try:
            return self._KINDS.get(element.Category.Id.IntegerValue)
        except Exception:
            return None

    def _hits(self, origin, direction):
        hits = []
        for context in self.intersector.Find(origin, direction):
            kind = self._kind(context.GetReference())
            if kind is not None:
                hits.append((mm(context.Proximity), kind))
        return hits

    def probe(self, x, y, origin_z, level_z):
        """core.Probe для точки (x, y) с началом лучей на высоте origin_z (футы) или None."""
        if self.error is not None:
            return None
        try:
            if self.intersector is None:
                self._open()
            origin = XYZ(x, y, origin_z)
            up = self._hits(origin, XYZ.BasisZ)
            down = self._hits(origin, XYZ.BasisZ.Negate())
        except Exception as ex:
            self.error = ex
            return None
        return core.probe(mm(origin_z), up, down, mm(level_z))

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
    """Поднять/опустить извещатели на низ перекрытия над ними. Возвращает MoveResult."""
    result = MoveResult()
    levels = plan_levels(doc)
    probe_ft = ft(settings.get("probe_height_mm") or 1500.0)
    offset_mm = settings.get("mount_offset_mm") or 0.0
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
        if found.ceiling_mm is not None:
            result.under_ceiling += 1
        delta_mm = core.move_delta(mm(point.Z), found.slab_z_mm, offset_mm)
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


def clear_view(doc, view, note_type):
    """Удалить с вида подписи и области заливки прошлого запуска. Возвращает число удалённых."""
    from System.Collections.Generic import List
    ids = List[ElementId]()
    for note in FilteredElementCollector(doc, view.Id).OfClass(TextNote):
        if note.GetTypeId() == note_type.Id:
            ids.Add(note.Id)
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


class ViewResult(object):
    def __init__(self, view):
        self.view = view
        self.rooms = 0
        self.ceiling_rooms = 0
        self.typical_mm = None
        self.changed = []      # (помещение, основная высота мм)
        self.no_slab = []      # имена помещений без перекрытия над ними
        self.errors = []


def annotate_view(doc, view, settings, probe, note_type, fill_type, progress=None):
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
    if probe.error is not None:
        result.errors.append(u"луч к перекрытию: {}".format(probe.error))
    return result
