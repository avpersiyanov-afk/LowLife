# -*- coding: utf-8 -*-
"""
Кнопка «Доступ к извещателям» (SPS.panel/DetectorAccess). Revit-часть;
чистая логика — detector_access_core.py, настройки —
detector_access_settings.py.

Что делает:
  1. assess — для каждого пожарного извещателя (отбор как в «Извещателях на
     перекрытие»): лучами вверх/вниз (slab_marks.SlabProbe — перекрытия,
     потолки, с элементами связей) — есть ли под ним пол этажа, на чём он
     (перекрытие, подвесной потолок или над потолком), высота от пола; затем
     — не заходят ли инженерные сети модели и связей (воздуховоды, трубы,
     лотки, короба, оборудование + категории из настроек) в цилиндр «зоны
     доступа» от пола до извещателя. Недоступному ищется ближайшее место
     (кольцами вокруг), где зона свободна, есть пол, та же поверхность
     установки на той же высоте и (если извещатель в помещении) то же
     помещение с отступом от стен.
  2. draw — на плане: зона доступа кругом (зелёный — доступен, красный — нет)
     с подписью причины, у недоступного — круг нового места, стрелка переноса
     и подпись расстояния. Повторный запуск заменяет графику прошлого запуска.

Вызывать внутри одной открытой транзакции (служебный 3D-вид SlabProbe
создаётся в ней при первом запуске и остаётся в модели — probe.close()).
"""

import math

from Autodesk.Revit.DB import (
    XYZ, Line, Arc, ElementId, FilteredElementCollector, BuiltInCategory, BuiltInParameter,
    LocationCurve, MEPCurve, Outline, BoundingBoxIntersectsFilter, ElementMulticategoryFilter,
    TextNote, CurveElement, Category, SpatialElementBoundaryOptions
)

from lowlife import detector_access_core as core
from lowlife import slab_marks
from lowlife.slab_marks import ft, mm
from lowlife.scs import safe_element_name
from lowlife.soue_floor import room_sources, room_name

# Тип текста подписей (создаётся копией типа текста по умолчанию). По нему
# повторный запуск находит и удаляет подписи прошлого запуска на виде.
TEXT_TYPE_NAME = u"LowLife — доступ к ПИ"

# Стили линий (подкатегории «Линии»): имя, цвет, толщина. По ним повторный
# запуск находит и удаляет графику прошлого запуска на виде.
ZONE_STYLE = (u"LowLife — зона доступа ПИ", (0, 160, 0), 3)
BLOCKED_STYLE = (u"LowLife — нет доступа к ПИ", (255, 0, 0), 5)
MOVE_STYLE = (u"LowLife — перенос ПИ", (240, 140, 40), 3)
STYLES = (ZONE_STYLE, BLOCKED_STYLE, MOVE_STYLE)

# Препятствия всегда: инженерные сети и оборудование (в модели и связях).
# Изоляция отдельной категорией не берётся — её толщина добавляется к ширине
# трубы/воздуховода (иначе габарит наклонной изоляции — весь её прямоугольник).
OBSTACLE_CATEGORIES = (
    "OST_DuctCurves", "OST_DuctFitting", "OST_DuctAccessory", "OST_FlexDuctCurves",
    "OST_PipeCurves", "OST_PipeFitting", "OST_PipeAccessory", "OST_FlexPipeCurves",
    "OST_CableTray", "OST_CableTrayFitting", "OST_Conduit", "OST_ConduitFitting",
    "OST_MechanicalEquipment", "OST_ElectricalEquipment",
)

# Ширина/диаметр прямых участков сетей (что найдётся — наибольшее) и изоляция.
_WIDTH_PARAMS = (
    "RBS_CURVE_WIDTH_PARAM", "RBS_CURVE_DIAMETER_PARAM", "RBS_PIPE_OUTER_DIAMETER",
    "RBS_CABLETRAY_WIDTH_PARAM", "RBS_CONDUIT_OUTER_DIAM_PARAM",
)
_INSULATION_PARAM = "RBS_REFERENCE_INSULATION_THICKNESS"

# Уровень помещения связи совпадает с уровнем извещателя с этим допуском.
LEVEL_TOLERANCE_MM = 300.0

# Помещение проверяется на этой высоте над его уровнем (IsPointInRoom).
ROOM_TEST_HEIGHT_MM = 1000.0

# Подписи на плане — на столько дальше круга зоны.
LABEL_GAP_MM = 150.0
ARROW_HEAD_MM = 200.0


# ------------------------------------------------------------
# Препятствия
# ------------------------------------------------------------

def obstacle_categories(doc, extra_text):
    """
    Категории препятствий: ({Id категории (int): имя}, [не найденные имена из
    extra_text]). Имена extra_text сравниваются с именами категорий Revit без
    учёта регистра.
    """
    names = {}
    for bic_name in OBSTACLE_CATEGORIES:
        bic = getattr(BuiltInCategory, bic_name, None)
        if bic is None:
            continue
        try:
            category = Category.GetCategory(doc, bic)
        except Exception:
            category = None
        if category is not None:
            names[category.Id.IntegerValue] = category.Name
    unknown = []
    wanted = [w.strip() for w in (extra_text or u"").replace(u";", u",").split(u",") if w.strip()]
    if wanted:
        by_name = {}
        for category in doc.Settings.Categories:
            try:
                by_name[category.Name.lower()] = category
            except Exception:
                pass
        for word in wanted:
            category = by_name.get(word.lower())
            if category is None:
                unknown.append(word)
            else:
                names[category.Id.IntegerValue] = category.Name
    return names, unknown


def _param_mm(element, name):
    bip = getattr(BuiltInParameter, name, None)
    if bip is None:
        return None
    try:
        param = element.get_Parameter(bip)
        if param is not None and param.HasValue:
            value = param.AsDouble()
            return mm(value) if value > 0 else None
    except Exception:
        pass
    return None


def _half_width_mm(element):
    """Половина ширины прямого участка сети с изоляцией или None."""
    widths = [w for w in (_param_mm(element, name) for name in _WIDTH_PARAMS) if w]
    if not widths:
        return None
    return max(widths) / 2.0 + (_param_mm(element, _INSULATION_PARAM) or 0.0)


def _corners(bbox, transform):
    result = []
    for x in (bbox.Min.X, bbox.Max.X):
        for y in (bbox.Min.Y, bbox.Max.Y):
            for z in (bbox.Min.Z, bbox.Max.Z):
                result.append(transform.OfPoint(XYZ(x, y, z)))
    return result


def _obstacle(element, transform, names, source_label, source_key):
    """core.Obstacle элемента в координатах модели или None."""
    try:
        name = names.get(element.Category.Id.IntegerValue)
        bbox = element.get_BoundingBox(None)
    except Exception:
        return None
    if name is None or bbox is None:
        return None
    corners = _corners(bbox, transform)
    z0 = mm(min(c.Z for c in corners))
    z1 = mm(max(c.Z for c in corners))
    polygon = None
    if isinstance(element, MEPCurve):
        try:
            location = element.Location
            curve = location.Curve if isinstance(location, LocationCurve) else None
        except Exception:
            curve = None
        half = _half_width_mm(element) if isinstance(curve, Line) else None
        if half:
            a = transform.OfPoint(curve.GetEndPoint(0))
            b = transform.OfPoint(curve.GetEndPoint(1))
            # вертикальный стояк — по габариту (ширина/высота сечения в плане)
            if math.hypot(mm(b.X - a.X), mm(b.Y - a.Y)) > half:
                polygon = core.segment_rect(mm(a.X), mm(a.Y), mm(b.X), mm(b.Y), half)
    if polygon is None:
        polygon = core.convex_hull([(mm(c.X), mm(c.Y)) for c in corners])
    try:
        type_name = safe_element_name(element.Document.GetElement(element.GetTypeId())) or u""
    except Exception:
        type_name = u""
    label = u"{}: {}".format(name, type_name) if type_name else name
    if source_label:
        label += u" ({})".format(source_label)
    return core.Obstacle(name, polygon, z0, z1, label, (source_key, element.Id.IntegerValue))


def collect_obstacles(doc, names, low, high):
    """
    Препятствия категорий names ({Id: имя}) модели и связей, чьи габариты
    пересекают коробку low..high (XYZ, футы, координаты модели) —
    core.ObstacleIndex.
    """
    from System.Collections.Generic import List
    index = core.ObstacleIndex()
    if not names:
        return index
    category_ids = List[ElementId]()
    for category_id in sorted(names):
        category_ids.Add(ElementId(category_id))
    for source_key, (source_doc, transform) in sorted(slab_marks.model_sources(doc).items()):
        inverse = transform.Inverse
        points = [inverse.OfPoint(XYZ(x, y, z))
                  for x in (low.X, high.X) for y in (low.Y, high.Y) for z in (low.Z, high.Z)]
        outline = Outline(
            XYZ(min(p.X for p in points), min(p.Y for p in points), min(p.Z for p in points)),
            XYZ(max(p.X for p in points), max(p.Y for p in points), max(p.Z for p in points)))
        label = u"" if source_key == -1 else (source_doc.Title or u"связь")
        try:
            collector = (FilteredElementCollector(source_doc)
                         .WherePasses(ElementMulticategoryFilter(category_ids))
                         .WhereElementIsNotElementType()
                         .WherePasses(BoundingBoxIntersectsFilter(outline)))
            elements = list(collector)
        except Exception:
            continue
        for element in elements:
            obstacle = _obstacle(element, transform, names, label, source_key)
            if obstacle is not None:
                index.add(obstacle)
    return index


# ------------------------------------------------------------
# Помещения
# ------------------------------------------------------------

class _RoomEntry(object):
    def __init__(self, source, room, inverse, box, level_z, host_level_z):
        self.source = source
        self.room = room
        self.inverse = inverse
        self.box = box              # (x0, y0, x1, y1) в координатах документа помещения
        self.level_z = level_z      # отметка уровня помещения в его документе
        self.host_level_z = host_level_z
        self.name = room_name(room)
        self._segments = None

    def contains(self, x, y):
        """Точка модели (x, y) внутри помещения."""
        p = self.inverse.OfPoint(XYZ(x, y, 0.0))
        x0, y0, x1, y1 = self.box
        if not (x0 <= p.X <= x1 and y0 <= p.Y <= y1):
            return False
        try:
            return self.room.IsPointInRoom(XYZ(p.X, p.Y, self.level_z + ft(ROOM_TEST_HEIGHT_MM)))
        except Exception:
            return False

    def segments(self):
        """Границы помещения (стены, разделители) в плане модели: [(x1, y1, x2, y2)] в мм."""
        if self._segments is None:
            self._segments = []
            try:
                loops = self.room.GetBoundarySegments(SpatialElementBoundaryOptions())
            except Exception:
                loops = None
            transform = self.source.transform
            for loop in loops or []:
                for segment in loop:
                    try:
                        points = [transform.OfPoint(p) for p in segment.GetCurve().Tessellate()]
                    except Exception:
                        continue
                    for a, b in zip(points, points[1:]):
                        self._segments.append((mm(a.X), mm(a.Y), mm(b.X), mm(b.Y)))
        return self._segments

    def wall_distance(self, x_mm, y_mm):
        """Расстояние от точки (мм, координаты модели) до границы помещения или None."""
        return core.segments_distance(x_mm, y_mm, self.segments())


class RoomLocator(object):
    """Помещения связей и модели: в каком помещении точка (по уровню и контуру)."""

    def __init__(self, doc):
        self.entries = []
        for source in room_sources(doc):
            inverse = source.transform.Inverse
            for room in source.rooms():
                try:
                    bbox = room.get_BoundingBox(None)
                    level_z = source.doc.GetElement(room.LevelId).ProjectElevation
                except Exception:
                    continue
                if bbox is None:
                    continue
                host_z = source.transform.OfPoint(XYZ(0, 0, level_z)).Z
                box = (bbox.Min.X, bbox.Min.Y, bbox.Max.X, bbox.Max.Y)
                self.entries.append(_RoomEntry(source, room, inverse, box, level_z, host_z))

    def find(self, x, y, level_z):
        """Помещение (_RoomEntry) на уровне level_z (футы), в котором точка (x, y), или None."""
        tolerance = ft(LEVEL_TOLERANCE_MM)
        for entry in self.entries:
            if abs(entry.host_level_z - level_z) > tolerance:
                continue
            if entry.contains(x, y):
                return entry
        return None


# ------------------------------------------------------------
# Проверка извещателей
# ------------------------------------------------------------

class Check(object):
    """Результат проверки одного извещателя."""

    def __init__(self, detector, point, level_z):
        self.detector = detector
        self.point = point            # XYZ точки вставки (футы)
        self.level_z = level_z        # отметка уровня (футы)
        self.status = None
        self.reason = u""
        self.zone_blockers = []       # core.Obstacle в зоне доступа
        self.detector_blockers = []   # ... прямо под извещателем
        self.height_mm = None         # от пола до точки извещателя
        self.room = None              # имя помещения или None
        self.wall_mm = None           # расстояние до стены (границы помещения), мм
        self.spot = None              # (x, y) нового места, футы
        self.search_note = u""        # почему новое место не найдено

    @property
    def ok(self):
        return self.status == core.OK


def _group_by_level(doc, detectors):
    """{отметка уровня (футы): [(извещатель, точка)]} и [(извещатель, причина)]."""
    levels = slab_marks.plan_levels(doc)
    groups = {}
    failed = []
    for detector in detectors:
        point = slab_marks._point(detector)
        _level, level_z = slab_marks.level_of(doc, detector, levels)
        if point is None or level_z is None:
            failed.append((detector, u"не определён уровень или точка вставки"))
            continue
        groups.setdefault(level_z, []).append((detector, point))
    return groups, failed


def assess(doc, detectors, settings, probe, progress=None):
    """
    Проверка доступа к извещателям: ([Check], [(извещатель, причина)],
    [не найденные категории из настроек]).
    """
    radius = settings.get("access_radius_mm") or 500.0
    top_gap = settings.get("top_gap_mm")
    top_gap = 150.0 if top_gap is None else top_gap
    max_height = settings.get("max_height_mm") or 0.0
    probe_ft = ft(settings.get("probe_height_mm") or 1500.0)
    search = settings.get("search_radius_mm") or 0.0
    step = settings.get("search_step_mm") or 100.0
    min_wall = settings.get("min_wall_distance_mm") or 0.0

    names, unknown = obstacle_categories(doc, settings.get("extra_obstacle_categories"))
    rooms = RoomLocator(doc)
    groups, failed = _group_by_level(doc, detectors)
    checks = []
    total = len(detectors)
    margin = ft(search + radius + 500.0)
    for level_z in sorted(groups):
        items = groups[level_z]
        low = XYZ(min(p.X for _d, p in items) - margin, min(p.Y for _d, p in items) - margin,
                  level_z - ft(1000.0))
        high = XYZ(max(p.X for _d, p in items) + margin, max(p.Y for _d, p in items) + margin,
                   max(p.Z for _d, p in items) + ft(500.0))
        index = collect_obstacles(doc, names, low, high)
        for detector, point in items:
            if progress is not None:
                progress(len(checks), total)
            checks.append(_check(detector, point, level_z, index, rooms, probe, probe_ft,
                                 radius, top_gap, max_height, search, step, min_wall))
    if probe.error is not None:
        failed.append((None, u"луч к перекрытию: {}".format(probe.error)))
    return checks, failed, unknown


def _check(detector, point, level_z, index, rooms, probe, probe_ft,
           radius, top_gap, max_height, search, step, min_wall):
    check = Check(detector, point, level_z)
    x, y, det_z = mm(point.X), mm(point.Y), mm(point.Z)
    room = rooms.find(point.X, point.Y, level_z)
    check.room = room.name if room is not None else None
    if room is not None:
        check.wall_mm = room.wall_distance(x, y)

    found = probe.probe(point.X, point.Y, level_z + probe_ft, level_z)
    if found is None:
        check.status = core.NO_SLAB
        check.reason = core.STATUS_TEXT[core.NO_SLAB]
        return check
    kind = core.mount_kind(det_z, found.ceiling_z_mm)
    floor_ok = core.has_floor(found.floor_found, found.floor_z_mm, mm(level_z))
    floor_z = found.floor_z_mm if floor_ok else mm(level_z)
    check.height_mm = det_z - floor_z
    z0, z1 = core.column_band(floor_z, det_z, top_gap)
    near = index.near(x, y, search + radius)
    check.zone_blockers = core.blockers(near, x, y, radius, z0, z1)
    check.detector_blockers = core.blockers(check.zone_blockers, x, y, core.DETECTOR_RADIUS_MM, z0, z1)
    check.status = core.classify(floor_ok, kind, check.height_mm, max_height, check.zone_blockers,
                                 check.wall_mm, min_wall)
    check.reason = core.reason_text(check.status, check.zone_blockers, check.detector_blockers,
                                    check.wall_mm, min_wall)
    if check.status not in core.MOVABLE:
        return check
    if search <= 0:
        return check

    surface_z = core.mount_z(kind, found.slab_z_mm, found.ceiling_z_mm)

    def allowed(cx, cy):
        if room is None or not min_wall:
            return True
        return not core.near_wall(room.wall_distance(cx, cy), min_wall)

    def accept(cx, cy):
        if room is not None and not room.contains(ft(cx), ft(cy)):
            return False
        candidate = probe.probe(ft(cx), ft(cy), level_z + probe_ft, level_z)
        if candidate is None:
            return False
        if not core.has_floor(candidate.floor_found, candidate.floor_z_mm, mm(level_z)):
            return False
        if abs(candidate.floor_z_mm - floor_z) > core.SAME_FLOOR_MM:
            return False
        return core.same_surface(kind, surface_z, candidate.slab_z_mm, candidate.ceiling_z_mm)

    spot = core.find_spot(x, y, near, radius, z0, z1, step, search, accept, allowed=allowed)
    if spot is None:
        check.search_note = u"свободного места в радиусе {} мм не найдено".format(int(search))
    else:
        check.spot = (ft(spot[0]), ft(spot[1]))
    return check


# ------------------------------------------------------------
# Графика на плане
# ------------------------------------------------------------

def styles(doc):
    """{имя стиля: GraphicsStyle или None} для ZONE/BLOCKED/MOVE."""
    return dict((name, slab_marks.line_style(doc, name, color, weight))
                for name, color, weight in STYLES)


def text_type(doc):
    return slab_marks.text_type(doc, TEXT_TYPE_NAME)


def clear_view(doc, view, note_type):
    """Удалить с вида подписи и линии прошлого запуска."""
    from System.Collections.Generic import List
    names = set(name for name, _color, _weight in STYLES)
    ids = List[ElementId]()
    for note in FilteredElementCollector(doc, view.Id).OfClass(TextNote):
        if note.GetTypeId() == note_type.Id:
            ids.Add(note.Id)
    for curve in FilteredElementCollector(doc, view.Id).OfClass(CurveElement):
        if slab_marks._line_style_name(curve) in names:
            ids.Add(curve.Id)
    if ids.Count:
        doc.Delete(ids)
    return ids.Count


def _curve(doc, view, curve, style):
    element = doc.Create.NewDetailCurve(view, curve)
    if style is not None:
        element.LineStyle = style
    return element


def _circle(doc, view, center, radius, style):
    for start in (0.0, math.pi):
        arc = Arc.Create(center, radius, start, start + math.pi, XYZ.BasisX, XYZ.BasisY)
        _curve(doc, view, arc, style)


def _arrow(doc, view, start, end, style):
    _curve(doc, view, Line.CreateBound(start, end), style)
    length = start.DistanceTo(end)
    head = min(ft(ARROW_HEAD_MM), length / 2.0)
    ux, uy = (start.X - end.X) / length, (start.Y - end.Y) / length
    for angle in (math.radians(25.0), -math.radians(25.0)):
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        tip = XYZ(end.X + (ux * cos_a - uy * sin_a) * head,
                  end.Y + (ux * sin_a + uy * cos_a) * head, end.Z)
        _curve(doc, view, Line.CreateBound(end, tip), style)


def _note(doc, view, point, text, note_type):
    TextNote.Create(doc, view.Id, point, text.replace(u"\n", u"\r"), note_type.Id)


class DrawResult(object):
    def __init__(self, view):
        self.view = view
        self.ok = 0
        self.problems = 0
        self.moves = 0
        self.errors = []


def draw(doc, view, checks, settings, note_type, line_styles):
    """
    Графика проверки на плане для извещателей уровня вида: круг зоны доступа
    (зелёный/красный), подпись причины, у недоступных — круг нового места,
    стрелка переноса и подпись. DrawResult.
    """
    result = DrawResult(view)
    clear_view(doc, view, note_type)
    view_z = view.GenLevel.ProjectElevation
    radius = ft(settings.get("access_radius_mm") or 500.0)
    gap = ft(LABEL_GAP_MM)
    zone_style = line_styles.get(ZONE_STYLE[0])
    blocked_style = line_styles.get(BLOCKED_STYLE[0])
    move_style = line_styles.get(MOVE_STYLE[0])
    for check in checks:
        if abs(check.level_z - view_z) > ft(LEVEL_TOLERANCE_MM):
            continue
        center = XYZ(check.point.X, check.point.Y, view_z)
        try:
            if check.ok:
                _circle(doc, view, center, radius, zone_style)
                result.ok += 1
                continue
            _circle(doc, view, center, radius, blocked_style)
            _note(doc, view, XYZ(center.X + radius + gap, center.Y + radius, view_z),
                  core.blocked_label(settings.get("blocked_text_format"), check.reason), note_type)
            result.problems += 1
            if check.spot is None:
                continue
            target = XYZ(check.spot[0], check.spot[1], view_z)
            _circle(doc, view, target, radius, zone_style)
            if center.DistanceTo(target) > ft(10.0):
                _arrow(doc, view, center, target, move_style)
            dx, dy = mm(target.X - center.X), mm(target.Y - center.Y)
            _note(doc, view, XYZ(target.X + radius + gap, target.Y, view_z),
                  core.move_label(settings.get("move_text_format"), dx, dy), note_type)
            result.moves += 1
        except Exception as ex:
            result.errors.append(u"{}: {}".format(check.detector.Id.IntegerValue, ex))
    return result
