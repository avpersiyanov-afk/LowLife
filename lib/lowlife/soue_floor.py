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

def _role_settings(settings, symbols):
    """{роль: (тип, на стену?, высота мм)} настроенных ролей."""
    from lowlife.soue_floor_settings import ROLE_KEYS
    result = {}
    for role, _, _, mount_key, height_key, _, _, _ in ROLE_KEYS:
        symbol = symbols.get(role)
        if symbol is None:
            continue
        result[role] = (symbol, settings.get(mount_key) == core.MOUNT_WALL,
                        float(settings.get(height_key) or 0.0))
    return result


def place_in_link(doc, link_instance, levels, settings, roles, result):
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
        symbol, on_wall, height_mm = roles[role]
        result.rooms[role] += 1
        if key in no_lot:
            result.diagnostics.append(
                u"ВНИМАНИЕ. {}: у помещения «{}» Id {} не заполнено «{}» — оповещатель "
                u"ставится как в отдельную квартиру.".format(label, name, key, lot_param))

        try:
            points = room_points(room, level_z, step if role != core.ROLE_APARTMENT else 0.0)
            if not points:
                result.failed[role] += 1
                result.diagnostics.append(u"{}: помещение «{}» Id {} — не найдена точка.".format(
                    label, name, key))
                continue

            placements = []
            if on_wall:
                if openings is None:
                    openings = collect_openings(link_doc, settings.get("opening_clearance_mm") or 0.0)
                segments = _boundary_segments(room)
                near = _room_openings(room, openings)
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
    symbols — {роль: FamilySymbol} настроенных ролей. Всё внутри уже
    открытой транзакции. Возвращает Result.
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
    for link_instance in links:
        try:
            place_in_link(doc, link_instance, levels, settings, roles, result)
        except Exception as ex:
            result.diagnostics.append(u"Связь Id {}: ошибка: {}".format(
                link_instance.Id.IntegerValue, ex))
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
