# -*- coding: utf-8 -*-
"""
Расстановка оповещателей СОУЭ на типовом этаже (SOUE.panel/PlaceTypicalFloor,
«СОУЭ — типовой этаж»). Revit-часть; чистая логика — soue_floor_core.py,
настройки — soue_floor_settings.py. Сделано по образцу «СС1-8Mile»
(ss1_easy.py) и берёт оттуда создание экземпляров на уровне, поворот,
удаление старого и чтение помещений.

Сценарий (run):
  1. Удаление старого: все экземпляры выбранных типов оповещателей на
     отмеченных уровнях удаляются — кнопка каждый раз расставляет заново.
  2. Помещения каждой загруженной связи (АР) делятся на роли
     (soue_floor_core.classify_rooms): квартира — одно помещение на лот из
     списка «Прихожая, …» (по приоритету, у двухуровневой — нижнее);
     коридоры МОП и лифтовые холлы — по своим спискам имён, кроме лежащих
     в лоте квартиры.
  3. Уровень модели — по отметке уровня помещения с учётом сдвига связи по
     Z (допуск из настроек); помещения неотмеченных уровней пропускаются.
  4. Точки: квартира — одна на помещение; МОП — по клетке габарита со
     стороной не больше шага (0 — одна). В клетке берётся точка внутри
     помещения (IsPointInRoom: центр клетки, иначе ближайший к нему узел
     сетки). На потолок — эта точка; на стену — ближайшая к ней точка
     границы помещения в стороне от дверей и окон связи
     (soue_floor_core.wall_point), экземпляр поворачивается лицом в
     помещение.
  5. Высота — смещение от уровня (как в «СС1-8Mile»), в параметр
     «Помещение» (если задан) — имя лота у квартир, имя помещения в МОП.
"""

from Autodesk.Revit.DB import (
    XYZ, FilteredElementCollector, BuiltInCategory, BuiltInParameter, RevitLinkInstance,
    SpatialElementBoundaryOptions, Level, LocationPoint
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


class Result(object):
    def __init__(self):
        self.deleted = 0
        self.links = 0
        self.rooms = dict((role, 0) for role in core.ROLES)
        self.placed = dict((role, 0) for role in core.ROLES)
        self.failed = dict((role, 0) for role in core.ROLES)
        self.on_opening = 0
        self.diagnostics = []
        self.mop_rows = []


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

SLAB_SUFFIX = "_slab"


def find_symbols(doc, settings):
    """
    Типоразмеры настроенных ролей: ({роль: тип, роль + SLAB_SUFFIX: тип «на
    перекрытие»}, [подписи не найденных в проекте]).
    """
    from lowlife.soue_floor_settings import ROLE_KEYS, MOP_KEYS
    wanted = [(role, family_key, type_key, label)
              for role, family_key, type_key, _, _, label, _, _ in ROLE_KEYS]
    labels = dict((role, label) for role, _, _, label in wanted)
    wanted += [(role + SLAB_SUFFIX, family_key, type_key, labels[role] + u" (на перекрытие)")
               for role, family_key, type_key, _, _, _, _ in MOP_KEYS]
    symbols = {}
    missing = []
    for key, family_key, type_key, label in wanted:
        family_name, type_name = settings.get(family_key), settings.get(type_key)
        if not family_name or not type_name:
            continue
        symbol = find_symbol(doc, family_name, type_name)
        if symbol is None:
            missing.append(u"{}: {} : {}".format(label, family_name, type_name))
        else:
            symbols[key] = symbol
    return symbols, missing


class RoleSetup(object):
    """Что и как ставится в помещения одной роли."""

    def __init__(self, symbol, on_wall, height_mm, slab_symbol=None,
                 spl=None, power=None, slab_spl=None, slab_power=None):
        self.symbol = symbol
        self.on_wall = on_wall
        self.height_mm = height_mm
        self.slab_symbol = slab_symbol
        self.spl = spl
        self.power = power
        self.slab_spl = slab_spl
        self.slab_power = slab_power

    @property
    def calculated(self):
        return self.spl is not None


def _role_settings(settings, symbols):
    """{роль: RoleSetup} настроенных ролей."""
    from lowlife.soue_floor_settings import ROLE_KEYS, MOP_KEYS
    mop = dict((item[0], item[1:]) for item in MOP_KEYS)
    result = {}
    for role, _, _, mount_key, height_key, _, _, _ in ROLE_KEYS:
        symbol = symbols.get(role)
        if symbol is None:
            continue
        setup = RoleSetup(symbol, settings.get(mount_key) == core.MOUNT_WALL,
                          float(settings.get(height_key) or 0.0))
        if role in mop:
            _, _, spl, power, slab_spl, slab_power = mop[role]
            setup.slab_symbol = symbols.get(role + SLAB_SUFFIX)
            setup.spl = float(settings.get(spl) or 0.0)
            setup.power = float(settings.get(power) or 0.0)
            setup.slab_spl = float(settings.get(slab_spl) or 0.0)
            setup.slab_power = float(settings.get(slab_power) or 0.0)
        result[role] = setup
    return result


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


CEILING_TEXT = {
    core.CEILING_SUSPENDED: u"подвесной потолок",
    core.CEILING_SLAB: u"перекрытие",
    None: u"не найден",
}


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


class MopRow(object):
    """Строка отчёта по расчёту помещения МОП."""

    def __init__(self, link, role, name, room_id, ceiling, height_mm, reach_m, count,
                 uncovered, samples):
        self.link = link
        self.role = role
        self.name = name
        self.room_id = room_id
        self.ceiling = ceiling
        self.height_mm = height_mm
        self.reach_m = reach_m
        self.count = count
        self.uncovered = uncovered
        self.samples = samples


# ------------------------------------------------------------
# Целиком
# ------------------------------------------------------------

def _mount(setup, probe, transform, room, level_z, level, settings):
    """
    (тип, высота мм, SPL, мощность, вид потолка) для помещения. На потолок —
    высота по лучу вверх: подвесной потолок — его отметка, перекрытие — низ
    плиты (тип «на перекрытие», ниже на slab_drop_mm); ничего — высота из
    настроек.
    """
    if setup.on_wall:
        return setup.symbol, setup.height_mm, setup.spl, setup.power, None
    try:
        point = room.Location.Point
    except Exception:
        return setup.symbol, setup.height_mm, setup.spl, setup.power, None
    origin = transform.OfPoint(XYZ(point.X, point.Y, level_z + mm_to_ft(ROOM_PROBE_HEIGHT_MM)))
    kind, distance = probe.find(origin)
    if kind is None:
        return setup.symbol, setup.height_mm, setup.spl, setup.power, None
    height_mm = (origin.Z + distance - level.ProjectElevation) * FT_TO_MM
    if kind == core.CEILING_SLAB and setup.slab_symbol is not None:
        height_mm -= float(settings.get("slab_drop_mm") or 0.0)
        return setup.slab_symbol, height_mm, setup.slab_spl, setup.slab_power, kind
    return setup.symbol, height_mm, setup.spl, setup.power, kind


def place_in_link(doc, link_instance, levels, settings, roles, probe, result):
    link_doc = link_instance.GetLinkDocument()
    if link_doc is None:
        return
    result.links += 1
    try:
        label = safe_element_name(link_instance) or u"связь"
    except Exception:
        label = u"связь"
    transform = link_instance.GetTotalTransform()

    lot_param = (settings.get("lot_param_name") or u"").strip()
    room_param = (settings.get("room_target_param") or u"").strip()
    tol = mm_to_ft(settings.get("level_tolerance_mm") or 0.0)
    step = mm_to_ft(float(settings.get("mop_step_m") or 0.0) * 1000.0)
    margin = mm_to_ft(settings.get("wall_margin_mm") or 0.0)
    dedupe = mm_to_ft(DEDUPE_MM)
    level_marks = [(level, level.ProjectElevation) for level in levels]

    rooms = {}
    entries = []
    collector = (FilteredElementCollector(link_doc)
                 .OfCategory(BuiltInCategory.OST_Rooms)
                 .WhereElementIsNotElementType())
    for room in collector:
        if not _room_placed(room):
            continue
        key = room.Id.IntegerValue
        name = ss1_easy._room_name(room)
        lot = ss1_easy._room_text_param(room, lot_param) if lot_param else u""
        level_z = _room_level_z(link_doc, room)
        rooms[key] = (room, name, lot, level_z)
        entries.append((key, name, lot, level_z))

    assigned, no_lot = core.classify_rooms(
        entries,
        core.split_names(settings.get("apartment_room_names")),
        core.split_names(settings.get("corridor_room_names")),
        core.split_names(settings.get("lift_hall_room_names")))

    openings = None
    for key in sorted(assigned):
        role = assigned[key]
        if role not in roles:
            continue
        room, name, lot, level_z = rooms[key]
        if level_z is None:
            continue
        level = match_level(transform.OfPoint(XYZ(0, 0, level_z)).Z, level_marks, tol)
        if level is None:
            continue
        setup = roles[role]
        result.rooms[role] += 1
        if key in no_lot:
            result.diagnostics.append(
                u"ВНИМАНИЕ. {}: у помещения «{}» Id {} не заполнено «{}» — оповещатель "
                u"ставится как в отдельную квартиру.".format(label, name, key, lot_param))

        try:
            symbol, height_mm, spl, power, ceiling = _mount(
                setup, probe, transform, room, level_z, level, settings)
            if not setup.on_wall and ceiling is None:
                result.diagnostics.append(
                    u"{}: помещение «{}» Id {} — над ним не найден ни потолок, ни "
                    u"перекрытие; высота из настроек ({:.0f} мм).".format(
                        label, name, key, float(height_mm)))
            if openings is None and setup.on_wall:
                openings = collect_openings(link_doc, settings.get("opening_clearance_mm") or 0.0)
            near = _room_openings(room, openings) if setup.on_wall else []

            if setup.calculated and step <= 0:
                _, reach_m = core.acoustic_reach(
                    spl, power,
                    float(settings.get("mop_noise_dba") or 0.0),
                    float(settings.get("excess_db") or 0.0),
                    float(settings.get("dn_loss_db") or 0.0),
                    float(settings.get("obstacle_db") or 0.0),
                    height_mm / 1000.0,
                    float(settings.get("calc_height_mm") or 0.0) / 1000.0)
                if reach_m <= 0:
                    result.failed[role] += 1
                    result.diagnostics.append(
                        u"{}: помещение «{}» Id {} — оповещатель (SPL {:.0f} дБ, {} Вт, h {:.0f} мм) "
                        u"не даёт требуемого уровня на расчётной высоте; не поставлен.".format(
                            label, name, key, float(spl), power, float(height_mm)))
                    continue
                placements, uncovered, samples = plan_calculated(
                    room, level_z, setup.on_wall, mm_to_ft(reach_m * 1000.0), near, margin)
                result.mop_rows.append(MopRow(
                    label, role, name, key,
                    CEILING_TEXT[ceiling] if not setup.on_wall else u"стена",
                    height_mm, reach_m, len(placements), uncovered, samples))
                if uncovered:
                    result.diagnostics.append(
                        u"{}: помещение «{}» Id {} — {} из {} расчётных точек не озвучить "
                        u"(нет подходящего места для оповещателя).".format(
                            label, name, key, uncovered, samples))
            else:
                points = room_points(room, level_z, step if role != core.ROLE_APARTMENT else 0.0)
                placements = []
                if setup.on_wall:
                    segments = _boundary_segments(room)
                    for point in points:
                        found = core.wall_point(segments, point, near, margin)
                        if found is None:
                            placements.append((point[0], point[1], None))
                            continue
                        x, y, nx, ny, free = found
                        if not free:
                            result.on_opening += 1
                            result.diagnostics.append(
                                u"{}: помещение «{}» Id {} — все стены у дверей/окон, оповещатель "
                                u"поставлен в ближайшую точку стены.".format(label, name, key))
                        placements.append((x, y, XYZ(nx, ny, 0)))
                else:
                    placements = [(x, y, None) for x, y in points]

            if not placements:
                result.failed[role] += 1
                result.diagnostics.append(u"{}: помещение «{}» Id {} — не найдена точка.".format(
                    label, name, key))
                continue

            done = []
            for x, y, normal in placements:
                if any((x - px) ** 2 + (y - py) ** 2 < dedupe ** 2 for px, py in done):
                    continue
                done.append((x, y))
                host = transform.OfPoint(XYZ(x, y, level_z))
                instance = create_on_level(doc, host.X, host.Y, height_mm, symbol, level)
                if normal is not None:
                    align_facing(doc, instance, transform.OfVector(normal))
                text = lot if role == core.ROLE_APARTMENT else name
                if room_param and text and not set_text_param(instance, room_param, text):
                    result.diagnostics.append(u"Оповещатель Id {}: не удалось записать «{}».".format(
                        instance.Id.IntegerValue, room_param))
                result.placed[role] += 1
        except Exception as ex:
            result.failed[role] += 1
            result.diagnostics.append(u"{}: помещение «{}» Id {} — ошибка: {}".format(
                label, name, key, ex))


def run(doc, levels, settings, symbols):
    """
    symbols — из find_symbols. Всё внутри уже открытой транзакции.
    Возвращает Result.
    """
    result = Result()
    roles = _role_settings(settings, symbols)
    unique = []
    for symbol in symbols.values():
        if all(symbol.Id != other.Id for other in unique):
            unique.append(symbol)
    for symbol in unique:
        activate_symbol(doc, symbol)

    level_ids = set(level.Id.IntegerValue for level in levels)
    result.deleted = sum(delete_old(doc, unique, level_ids).values())

    links = list(FilteredElementCollector(doc).OfClass(RevitLinkInstance))
    if not links:
        result.diagnostics.append(u"В проекте нет ни одной связи — помещения брать неоткуда.")
        return result
    probe = CeilingProbe(doc)
    try:
        for link_instance in links:
            try:
                place_in_link(doc, link_instance, levels, settings, roles, probe, result)
            except Exception as ex:
                result.diagnostics.append(u"Связь Id {}: ошибка: {}".format(
                    link_instance.Id.IntegerValue, ex))
    finally:
        probe.close()
    if probe.error is not None:
        result.diagnostics.append(
            u"Не удалось определить потолки (луч вверх): {} — высота потолочных "
            u"оповещателей взята из настроек.".format(probe.error))
    return result


def ask_levels(doc, title):
    """Выбор уровней типового этажа (несколько). None — отмена."""
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
        [LevelItem(level) for level in levels],
        title=u"{}: уровни".format(title),
        button_name=u"Расставить",
        multiselect=True,
    )
    return picked or None
