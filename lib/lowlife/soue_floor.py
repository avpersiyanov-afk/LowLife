# -*- coding: utf-8 -*-
"""
Расстановка оповещателей СОУЭ (SOUE.panel/PlaceTypicalFloor, «СОУЭ -
расстановка типовой этаж»). Revit-часть; чистая логика — soue_floor_core.py,
настройки — soue_floor_settings.py, таблица помещений — soue_floor_rooms.py.
Сделано по образцу «СС1-8Mile» (ss1_easy.py) и берёт оттуда создание
экземпляров на уровне, поворот, удаление старого и чтение помещений.

Сценарий:
  1. gather (до транзакции): все помещения всех связей (и модели) на
     отмеченных уровнях делятся на роли (soue_floor_core.classify_rooms):
     квартира — одно помещение на лот из списка «Прихожая, …» (по
     приоритету, у двухуровневой — нижнее), остальные помещения лота
     квартиры не оснащаются; все прочие помещения, кроме исключённых в
     таблице помещений, — ROLE_ROOM. Уровень модели — по отметке уровня
     помещения с учётом сдвига связи по Z. Кнопка спрашивает шум для
     имён, у которых его нет (soue_floor_rooms.ask_missing_noise).
  2. run (в транзакции): удаление старых экземпляров выбранных типов на
     отмеченных уровнях; квартиры — один оповещатель на стену (или потолок);
     прочие помещения — луч вверх (CeilingProbe): подвесной потолок —
     потолочный тип в плоскость потолка, иначе — настенный на заданной
     высоте; количество и места — по акустическому расчёту
     (soue_floor_core.room_reach: SPL и мощность — из параметров типа
     оповещателя, шум — из таблицы помещений), plan_calculated.
"""

from Autodesk.Revit.DB import (
    XYZ, FilteredElementCollector, BuiltInCategory, BuiltInParameter, RevitLinkInstance,
    SpatialElementBoundaryOptions, Level, LocationPoint, StorageType
)

from lowlife import soue_floor_core as core
from lowlife import ss1_easy
from lowlife.scs import safe_element_name
from lowlife.ss1_easy_core import match_level
from lowlife.ss1_easy import (  # noqa: F401 — find_symbol нужен кнопке
    mm_to_ft, find_symbol, activate_symbol, create_on_level, align_facing,
    set_text_param, delete_old, get_levels
)

FT_TO_MM = 304.8

# Высота над уровнем помещения, на которой проверяется «точка в помещении».
ROOM_PROBE_HEIGHT_MM = 1000.0

# Ширина проёма, если её не удалось прочитать у двери/окна.
DEFAULT_OPENING_WIDTH_MM = 900.0

# Две точки одного помещения ближе этого — один оповещатель.
DEDUPE_MM = 500.0


# ------------------------------------------------------------
# Помещения связи
# ------------------------------------------------------------

def _room_placed(room):
    try:
        return room.Area > 1e-6 and room.Location is not None
    except Exception:
        return False


def _room_level_z(link_doc, room):
    """Отметка уровня помещения в координатах связи или None."""
    try:
        level = link_doc.GetElement(room.LevelId)
        if isinstance(level, Level):
            return level.ProjectElevation
    except Exception:
        pass
    try:
        location = room.Location
        if isinstance(location, LocationPoint):
            return location.Point.Z
    except Exception:
        pass
    return None


def _boundary_segments(room):
    """[(x1, y1, x2, y2)] границы помещения (дуги — ломаной)."""
    result = []
    try:
        loops = room.GetBoundarySegments(SpatialElementBoundaryOptions())
    except Exception:
        loops = None
    if not loops:
        return result
    for loop in loops:
        for segment in loop:
            try:
                points = list(segment.GetCurve().Tessellate())
            except Exception:
                continue
            for a, b in zip(points, points[1:]):
                result.append((a.X, a.Y, b.X, b.Y))
    return result


def _opening_width(element, bips):
    for obj in ss1_easy._instance_and_type(element):
        for bip in bips:
            try:
                param = obj.get_Parameter(bip)
                if param is not None and param.HasValue and param.AsDouble() > 1e-6:
                    return param.AsDouble()
            except Exception:
                pass
    return mm_to_ft(DEFAULT_OPENING_WIDTH_MM)


def collect_openings(link_doc, clearance_mm):
    """[(x, y, z, радиус)] дверей и окон связи — зоны, где не ставить на стену."""
    result = []
    groups = (
        (BuiltInCategory.OST_Doors, (BuiltInParameter.DOOR_WIDTH, BuiltInParameter.FAMILY_WIDTH_PARAM)),
        (BuiltInCategory.OST_Windows, (BuiltInParameter.WINDOW_WIDTH, BuiltInParameter.FAMILY_WIDTH_PARAM)),
    )
    clearance = mm_to_ft(clearance_mm)
    for category, bips in groups:
        collector = (FilteredElementCollector(link_doc)
                     .OfCategory(category)
                     .WhereElementIsNotElementType())
        for element in collector:
            point = ss1_easy._door_point(element)
            if point is None:
                continue
            radius = _opening_width(element, bips) / 2.0 + clearance
            result.append((point.X, point.Y, point.Z, radius))
    return result


def _room_openings(room, openings):
    """Проёмы на высоте помещения (по габариту помещения по Z, с запасом)."""
    try:
        bbox = room.get_BoundingBox(None)
    except Exception:
        bbox = None
    if bbox is None:
        return [(x, y, r) for x, y, _, r in openings]
    low = bbox.Min.Z - mm_to_ft(500.0)
    high = bbox.Max.Z
    pad = mm_to_ft(3000.0)
    return [(x, y, r) for x, y, z, r in openings
            if low <= z <= high
            and bbox.Min.X - pad <= x <= bbox.Max.X + pad
            and bbox.Min.Y - pad <= y <= bbox.Max.Y + pad]


def _point_in_room(room, x, y, z):
    try:
        return room.IsPointInRoom(XYZ(x, y, z))
    except Exception:
        return False


def room_points(room, level_z, step_ft):
    """
    Точки оповещателей внутри помещения (координаты связи): по одной на
    клетку габарита (core.grid_cells) — центр клетки или ближайший к нему
    узел сетки, попадающий в помещение.
    """
    bbox = room.get_BoundingBox(None)
    if bbox is None:
        return []
    probe_z = level_z + mm_to_ft(ROOM_PROBE_HEIGHT_MM)
    points = []
    for cell in core.grid_cells(bbox.Min.X, bbox.Min.Y, bbox.Max.X, bbox.Max.Y, step_ft):
        for x, y in core.cell_samples(cell):
            if _point_in_room(room, x, y, probe_z):
                points.append((x, y))
                break
    if not points:
        try:
            location = room.Location.Point
            points.append((location.X, location.Y))
        except Exception:
            pass
    return points


# ------------------------------------------------------------
# Целиком
# ------------------------------------------------------------

def find_symbols(doc, settings):
    """
    Выбранные типоразмеры: ({роль из SYMBOL_KEYS: тип}, [подписи не
    найденных в проекте]).
    """
    from lowlife.soue_floor_settings import SYMBOL_KEYS
    symbols = {}
    missing = []
    for role, family_key, type_key, label in SYMBOL_KEYS:
        family_name, type_name = settings.get(family_key), settings.get(type_key)
        if not family_name or not type_name:
            continue
        symbol = find_symbol(doc, family_name, type_name)
        if symbol is None:
            missing.append(u"{}: {} : {}".format(label, family_name, type_name))
        else:
            symbols[role] = symbol
    return symbols, missing


def _param_number(element, name):
    """Число из параметра name элемента (текст «1,5 Вт» тоже) или None."""
    if element is None or not name:
        return None
    try:
        param = element.LookupParameter(name)
    except Exception:
        param = None
    if param is None or not param.HasValue:
        return None
    for read in (lambda: param.AsString(), lambda: param.AsValueString()):
        try:
            value = core.parse_number(read())
            if value is not None:
                return value
        except Exception:
            pass
    try:
        return float(param.AsInteger() if param.StorageType == StorageType.Integer else param.AsDouble())
    except Exception:
        return None


def speaker_data(doc, symbol, settings):
    """
    (SPL дБ, мощность Вт, [предупреждения]) оповещателя: параметры из
    настроек у типа, иначе — у любого стоящего экземпляра этого типа,
    иначе — значения «если параметра нет» из настроек.
    """
    from Autodesk.Revit.DB import FamilyInstanceFilter
    instance = None
    try:
        instance = FilteredElementCollector(doc).WherePasses(
            FamilyInstanceFilter(doc, symbol.Id)).FirstElement()
    except Exception:
        pass
    label = u"{} : {}".format(safe_element_name(symbol.Family), safe_element_name(symbol))
    result = []
    warnings = []
    for key, fallback_key, what in (("spl_param_name", "fallback_spl_db", u"SPL"),
                                    ("power_param_name", "fallback_power_w", u"мощность")):
        name = (settings.get(key) or u"").strip()
        value = _param_number(symbol, name)
        if value is None:
            value = _param_number(instance, name)
        if value is None:
            value = float(settings.get(fallback_key) or 0.0)
            warnings.append(u"Оповещатель «{}»: нет параметра «{}» ({}) — взято {}.".format(
                label, name, what, value))
        result.append(value)
    return result[0], result[1], warnings


# ------------------------------------------------------------
# Потолок над помещением: подвесной или перекрытие
# ------------------------------------------------------------

class CeilingProbe(object):
    """
    Луч вверх (ReferenceIntersector по временному 3D-виду, с элементами
    связей): ближайший подвесной потолок (категория «Потолки») или
    перекрытие («Перекрытия», «Крыши»). Вид создаётся при первом запросе и
    удаляется close() в той же транзакции.
    """

    _KINDS = {
        int(BuiltInCategory.OST_Ceilings): core.CEILING_SUSPENDED,
        int(BuiltInCategory.OST_Floors): core.CEILING_SLAB,
        int(BuiltInCategory.OST_Roofs): core.CEILING_SLAB,
    }

    def __init__(self, doc):
        self.doc = doc
        self.view = None
        self.intersector = None
        self.error = None

    def _open(self):
        from Autodesk.Revit.DB import (
            View3D, ViewFamilyType, ViewFamily, ReferenceIntersector, FindReferenceTarget,
            ElementId
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

    def _element(self, reference):
        from Autodesk.Revit.DB import ElementId
        element = self.doc.GetElement(reference.ElementId)
        if reference.LinkedElementId != ElementId.InvalidElementId:
            try:
                element = element.GetLinkDocument().GetElement(reference.LinkedElementId)
            except Exception:
                return None
        return element

    def find(self, origin):
        """(вид, расстояние вверх от origin в футах) или (None, None)."""
        if self.error is not None:
            return None, None
        try:
            if self.intersector is None:
                self._open()
            hits = []
            for context in self.intersector.Find(origin, XYZ.BasisZ):
                element = self._element(context.GetReference())
                try:
                    category = element.Category.Id.IntegerValue
                except Exception:
                    continue
                hits.append((context.Proximity, self._KINDS.get(category)))
            return core.classify_ceiling(hits)
        except Exception as ex:
            self.error = ex
            return None, None

    def close(self):
        if self.view is not None:
            try:
                self.doc.Delete(self.view.Id)
            except Exception:
                pass
            self.view = None


# ------------------------------------------------------------
# Акустический расчёт МОП: расчётные точки и расстановка
# ------------------------------------------------------------

SAMPLE_STEP_MM = 500.0


def room_grid(room, level_z):
    """Расчётные точки помещения (узлы сетки внутри него) — core.SampleGrid или None."""
    bbox = room.get_BoundingBox(None)
    if bbox is None:
        return None
    width = bbox.Max.X - bbox.Min.X
    height = bbox.Max.Y - bbox.Min.Y
    step = core.sample_step(width, height, mm_to_ft(SAMPLE_STEP_MM))
    x0 = bbox.Min.X + step / 2.0
    y0 = bbox.Min.Y + step / 2.0
    probe_z = level_z + mm_to_ft(ROOM_PROBE_HEIGHT_MM)
    nodes = []
    count_x = int(width / step) + 1
    count_y = int(height / step) + 1
    for j in range(count_y):
        for i in range(count_x):
            if _point_in_room(room, x0 + i * step, y0 + j * step, probe_z):
                nodes.append((i, j))
    if not nodes:
        return None
    grid = core.SampleGrid(x0, y0, step, nodes)
    # Все узлы внутри — помещение прямоугольное, видимость проверять незачем.
    grid.full = len(nodes) == count_x * count_y
    return grid


def _inward_segments(room, level_z):
    """[(x1, y1, x2, y2, nx, ny)] — сегменты границы с нормалью внутрь помещения."""
    probe_z = level_z + mm_to_ft(ROOM_PROBE_HEIGHT_MM)
    reach = mm_to_ft(300.0)
    result = []
    for x1, y1, x2, y2 in _boundary_segments(room):
        length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if length < 1e-6:
            continue
        nx, ny = -(y2 - y1) / length, (x2 - x1) / length
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        if not _point_in_room(room, mx + nx * reach, my + ny * reach, probe_z):
            nx, ny = -nx, -ny
        result.append((x1, y1, x2, y2, nx, ny))
    return result


def plan_calculated(room, level_z, on_wall, reach_ft, openings, margin):
    """
    Места оповещателей по акустическому расчёту: жадное покрытие расчётных
    точек помещения (core.greedy_cover). Кандидаты — узлы сетки (потолок)
    или точки вдоль стен в стороне от проёмов (стена). Возвращает
    ([(x, y, нормаль или None)], не озвучено точек, всего точек).
    """
    grid = room_grid(room, level_z)
    if grid is None:
        return [], 0, 0
    samples = grid.points()
    if on_wall:
        candidates = core.wall_candidates(
            _inward_segments(room, level_z), openings, margin, grid.step * 2.0)
    else:
        candidates = [grid.point((i, j)) for i, j in grid.nodes
                      if len(grid.nodes) <= 250 or (i % 2 == 0 and j % 2 == 0)]
    sight = None if grid.full else grid
    sets = core.coverage(candidates, samples, reach_ft, sight, wall=on_wall)
    chosen, uncovered = core.greedy_cover(candidates, sets, samples)
    if not on_wall and uncovered == 0:
        # Прямоугольное помещение — регулярная сетка (шаг R·√2 / ряд), если
        # она озвучивает всё и выходит не больше оповещателей.
        xs = [x for x, _ in samples]
        ys = [y for _, y in samples]
        cells = [p for p in core.lattice(min(xs), min(ys), max(xs), max(ys), reach_ft)
                 if grid.inside(p[0], p[1])]
        cell_sets = core.coverage(cells, samples, reach_ft, sight)
        covered = set()
        for item in cell_sets:
            covered |= item
        if cells and len(covered) == len(samples) and len(cells) <= len(chosen):
            candidates, chosen = cells, list(range(len(cells)))
    placements = []
    for index in chosen:
        cand = candidates[index]
        normal = XYZ(cand[2], cand[3], 0) if on_wall else None
        placements.append((cand[0], cand[1], normal))
    return placements, uncovered, len(samples)


class RoomTask(object):
    """Помещение, которое оснащается: где оно, чем и на каком уровне модели."""

    def __init__(self, source, room, name, lot, level_z, level, role, no_lot=False):
        self.source = source
        self.room = room
        self.name = name
        self.lot = lot
        self.level_z = level_z
        self.level = level
        self.role = role
        self.no_lot = no_lot

    @property
    def key(self):
        return core.normalize(self.name)


class ReportRow(object):
    """Строка отчёта по расчёту помещения."""

    def __init__(self, task, category, noise, mount, height_mm, reach_m, count, uncovered, samples):
        self.link = task.source.label
        self.name = task.name
        self.room_id = task.room.Id.IntegerValue
        self.level = task.level.Name
        self.category = category
        self.noise = noise
        self.mount = mount
        self.height_mm = height_mm
        self.reach_m = reach_m
        self.count = count
        self.uncovered = uncovered
        self.samples = samples


class RoomSource(object):
    """Документ с помещениями: связь (с её преобразованием) или сама модель."""

    def __init__(self, doc, transform, label, element_id=None):
        self.doc = doc
        self.transform = transform
        self.label = label
        self.element_id = element_id
        self._openings = None

    def rooms(self):
        collector = (FilteredElementCollector(self.doc)
                     .OfCategory(BuiltInCategory.OST_Rooms)
                     .WhereElementIsNotElementType())
        return [room for room in collector if _room_placed(room)]

    def openings(self, clearance_mm):
        if self._openings is None:
            self._openings = collect_openings(self.doc, clearance_mm)
        return self._openings


def room_sources(doc):
    """Загруженные связи и сама модель (если в ней есть помещения)."""
    from Autodesk.Revit.DB import Transform
    sources = []
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        try:
            link_doc = link.GetLinkDocument()
        except Exception:
            link_doc = None
        if link_doc is None:
            continue
        try:
            label = safe_element_name(link) or u"связь"
        except Exception:
            label = u"связь"
        sources.append(RoomSource(link_doc, link.GetTotalTransform(), label, link.Id.IntegerValue))
    host = RoomSource(doc, Transform.Identity, u"модель")
    if host.rooms():
        sources.append(host)
    return sources


def room_name(room):
    return ss1_easy._room_name(room)


def gather(doc, levels, settings, table):
    """
    Помещения к оснащению на отмеченных уровнях: ([RoomTask], [сообщения]).
    table — {ключ имени: core.RoomRow} (исключения).
    """
    lot_param = (settings.get("lot_param_name") or u"").strip()
    tol = mm_to_ft(settings.get("level_tolerance_mm") or 0.0)
    level_marks = [(level, level.ProjectElevation) for level in levels]
    excluded = set(key for key, row in table.items() if row.exclude)
    apartment_names = core.split_names(settings.get("apartment_room_names"))

    tasks = []
    messages = []
    for source in room_sources(doc):
        rooms = {}
        entries = []
        for room in source.rooms():
            key = room.Id.IntegerValue
            name = room_name(room)
            lot = ss1_easy._room_text_param(room, lot_param) if lot_param else u""
            level_z = _room_level_z(source.doc, room)
            rooms[key] = (room, name, lot, level_z)
            entries.append((key, name, lot, level_z))
        assigned, no_lot = core.classify_rooms(entries, apartment_names, excluded)
        for key in sorted(assigned):
            room, name, lot, level_z = rooms[key]
            if level_z is None:
                continue
            level = match_level(source.transform.OfPoint(XYZ(0, 0, level_z)).Z, level_marks, tol)
            if level is None:
                continue
            tasks.append(RoomTask(source, room, name, lot, level_z, level, assigned[key],
                                  key in no_lot))
            if key in no_lot:
                messages.append(
                    u"ВНИМАНИЕ. {}: у помещения «{}» Id {} не заполнено «{}» — оповещатель "
                    u"ставится как в отдельную квартиру.".format(source.label, name, key, lot_param))
    return tasks, messages


def missing_noise_rows(tasks, table):
    """
    [core.RoomRow] имён помещений ROLE_ROOM, которых нет в таблице или у
    которых нет уровня шума; у новых имён категория и «исключить»
    подобраны по имени.
    """
    counts = {}
    names = {}
    for task in tasks:
        if task.role != core.ROLE_ROOM:
            continue
        row = table.get(task.key)
        if row is not None and (row.exclude or row.effective_noise() is not None):
            continue
        counts[task.key] = counts.get(task.key, 0) + 1
        names.setdefault(task.key, task.name)
    rows = []
    for key in sorted(counts, key=lambda k: names[k].lower()):
        old = table.get(key)
        if old is not None:
            rows.append(core.RoomRow(names[key], counts[key], old.category, None, False))
        else:  # новое имя — подсказка по имени
            rows.append(core.RoomRow(names[key], counts[key], core.guess_category(names[key]) or u"",
                                     None, core.guess_exclude(names[key])))
    return rows


# ------------------------------------------------------------
# Целиком
# ------------------------------------------------------------

class Result(object):
    def __init__(self):
        self.deleted = 0
        self.rooms = dict((role, 0) for role in core.ROLES)
        self.placed = dict((role, 0) for role in core.ROLES)
        self.failed = dict((role, 0) for role in core.ROLES)
        self.skipped_no_noise = 0
        self.diagnostics = []
        self.report = []


def _place(doc, task, placements, symbol, height_mm, text, room_param, result):
    dedupe = mm_to_ft(DEDUPE_MM)
    done = []
    for x, y, normal in placements:
        if any((x - px) ** 2 + (y - py) ** 2 < dedupe ** 2 for px, py in done):
            continue
        done.append((x, y))
        transform = task.source.transform
        host = transform.OfPoint(XYZ(x, y, task.level_z))
        instance = create_on_level(doc, host.X, host.Y, height_mm, symbol, task.level)
        if normal is not None:
            align_facing(doc, instance, transform.OfVector(normal))
        if room_param and text and not set_text_param(instance, room_param, text):
            result.diagnostics.append(u"Оповещатель Id {}: не удалось записать «{}».".format(
                instance.Id.IntegerValue, room_param))
        result.placed[task.role] += 1
    return len(done)


def _place_apartment(task, settings, probe, result):
    on_wall = settings.get("apartment_mount") == core.MOUNT_WALL
    height_mm = float(settings.get("apartment_height_mm") or 0.0)
    room = task.room
    margin = mm_to_ft(settings.get("wall_margin_mm") or 0.0)
    if not on_wall:
        kind, ceiling_mm = _ceiling(probe, task)
        if kind is not None:
            height_mm = ceiling_mm
    points = room_points(room, task.level_z, 0.0)
    placements = []
    if on_wall:
        segments = _boundary_segments(room)
        near = _room_openings(room, task.source.openings(settings.get("opening_clearance_mm") or 0.0))
        for point in points:
            found = core.wall_point(segments, point, near, margin)
            if found is None:
                placements.append((point[0], point[1], None))
                continue
            x, y, nx, ny, free = found
            if not free:
                result.diagnostics.append(
                    u"{}: помещение «{}» Id {} — все стены у дверей/окон, оповещатель "
                    u"поставлен в ближайшую точку стены.".format(
                        task.source.label, task.name, room.Id.IntegerValue))
            placements.append((x, y, XYZ(nx, ny, 0)))
    else:
        placements = [(x, y, None) for x, y in points]
    return placements, height_mm


def _ceiling(probe, task):
    """(вид потолка, высота его плоскости над уровнем в мм) по лучу вверх из помещения."""
    try:
        point = task.room.Location.Point
    except Exception:
        return None, None
    origin = task.source.transform.OfPoint(
        XYZ(point.X, point.Y, task.level_z + mm_to_ft(ROOM_PROBE_HEIGHT_MM)))
    kind, distance = probe.find(origin)
    if kind is None:
        return None, None
    return kind, (origin.Z + distance - task.level.ProjectElevation) * FT_TO_MM


def _place_room(task, settings, symbols, speakers, table, probe, result):
    """Помещение объекта: потолочный при подвесном потолке, иначе настенный; по расчёту."""
    from lowlife.soue_floor_settings import SYMBOL_WALL, SYMBOL_CEILING
    row = table.get(task.key)
    noise = row.effective_noise() if row is not None else None
    if noise is None:
        result.skipped_no_noise += 1
        result.diagnostics.append(u"{}: помещение «{}» Id {} — не задан уровень шума, пропущено.".format(
            task.source.label, task.name, task.room.Id.IntegerValue))
        return None, None, None
    category = row.category if row is not None else u""

    role = SYMBOL_WALL
    height_mm = float(settings.get("room_wall_height_mm") or 0.0)
    mount_text = u"стена"
    if SYMBOL_CEILING in symbols:
        kind, ceiling_mm = _ceiling(probe, task)
        if kind == core.CEILING_SUSPENDED:
            role, height_mm, mount_text = SYMBOL_CEILING, ceiling_mm, u"подвесной потолок"
    if role not in symbols:
        result.failed[task.role] += 1
        result.diagnostics.append(u"{}: помещение «{}» Id {} — не выбран настенный тип.".format(
            task.source.label, task.name, task.room.Id.IntegerValue))
        return None, None, None
    spl, power, _ = speakers[role]
    on_wall = role == SYMBOL_WALL
    _, reach_m = core.room_reach(spl, power, noise, height_mm / 1000.0)
    if reach_m <= 0:
        result.failed[task.role] += 1
        result.diagnostics.append(
            u"{}: помещение «{}» Id {} — оповещатель (SPL {:.0f} дБ, {} Вт, h {:.0f} мм) не "
            u"даёт {:.0f} дБА на высоте 1,5 м; не поставлен.".format(
                task.source.label, task.name, task.room.Id.IntegerValue, float(spl), power,
                float(height_mm), float(noise + core.EXCESS_DB)))
        return None, None, None
    near = []
    if on_wall:
        near = _room_openings(task.room, task.source.openings(settings.get("opening_clearance_mm") or 0.0))
    margin = mm_to_ft(settings.get("wall_margin_mm") or 0.0)
    placements, uncovered, samples = plan_calculated(
        task.room, task.level_z, on_wall, mm_to_ft(reach_m * 1000.0), near, margin)
    result.report.append(ReportRow(task, category, noise, mount_text, height_mm, reach_m,
                                   len(placements), uncovered, samples))
    if uncovered:
        result.diagnostics.append(
            u"{}: помещение «{}» Id {} — {} из {} расчётных точек не озвучить "
            u"(нет подходящего места для оповещателя).".format(
                task.source.label, task.name, task.room.Id.IntegerValue, uncovered, samples))
    return placements, symbols[role], height_mm


def run(doc, levels, tasks, settings, symbols, table, progress=None):
    """
    levels — отмеченные уровни (на них удаляются старые экземпляры), tasks — из gather, symbols — из find_symbols, table — {ключ: RoomRow}.
    Всё внутри уже открытой транзакции. progress(i, n) — необязательный.
    Возвращает Result.
    """
    from lowlife.soue_floor_settings import SYMBOL_APARTMENT, SYMBOL_WALL
    result = Result()

    speakers = {}
    for role, symbol in symbols.items():
        speakers[role] = speaker_data(doc, symbol, settings)
        result.diagnostics.extend(speakers[role][2])

    unique = []
    for symbol in symbols.values():
        if all(symbol.Id != other.Id for other in unique):
            unique.append(symbol)
    for symbol in unique:
        activate_symbol(doc, symbol)
    level_ids = set(level.Id.IntegerValue for level in levels)
    result.deleted = sum(delete_old(doc, unique, level_ids).values())

    room_param = (settings.get("room_target_param") or u"").strip()
    probe = CeilingProbe(doc)
    try:
        for index, task in enumerate(tasks):
            if progress is not None:
                progress(index, len(tasks))
            if task.role == core.ROLE_APARTMENT and SYMBOL_APARTMENT not in symbols:
                continue
            if task.role == core.ROLE_ROOM and SYMBOL_WALL not in symbols:
                continue
            result.rooms[task.role] += 1
            try:
                if task.role == core.ROLE_APARTMENT:
                    symbol = symbols[SYMBOL_APARTMENT]
                    placements, height_mm = _place_apartment(task, settings, probe, result)
                    text = task.lot
                else:
                    placements, symbol, height_mm = _place_room(
                        task, settings, symbols, speakers, table, probe, result)
                    if placements is None:
                        continue
                    text = task.name
                if not placements:
                    result.failed[task.role] += 1
                    result.diagnostics.append(u"{}: помещение «{}» Id {} — не найдена точка.".format(
                        task.source.label, task.name, task.room.Id.IntegerValue))
                    continue
                _place(doc, task, placements, symbol, height_mm, text, room_param, result)
            except Exception as ex:
                result.failed[task.role] += 1
                result.diagnostics.append(u"{}: помещение «{}» Id {} — ошибка: {}".format(
                    task.source.label, task.name, task.room.Id.IntegerValue, ex))
    finally:
        probe.close()
    if probe.error is not None:
        result.diagnostics.append(
            u"Не удалось определить потолки (луч вверх): {} — везде настенные.".format(probe.error))
    return result


def ask_levels(doc, title):
    """Выбор уровней (по умолчанию отмечены все). None — отмена."""
    from pyrevit import forms

    levels = get_levels(doc)
    if not levels:
        forms.alert(u"В проекте нет ни одного уровня.", title=title)
        return None

    class LevelItem(forms.TemplateListItem):
        @property
        def name(self):
            level = self.item
            try:
                return u"{}   ({:.0f} мм)".format(level.Name, float(level.Elevation) * FT_TO_MM)
            except Exception:
                return level.Name

    picked = forms.SelectFromList.show(
        [LevelItem(level, checked=True) for level in levels],
        title=u"{}: уровни".format(title),
        button_name=u"Расставить",
        multiselect=True,
    )
    return picked or None
