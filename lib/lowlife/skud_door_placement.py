# -*- coding: utf-8 -*-
"""
Расстановка элементов точки доступа СКУД на двери выбранных помещений
(SKUD.panel/PlaceDoorAccessPoints). Revit-часть; чистая геометрия и
раскладка состава группы по местам — в skud_door_layout.py.

Сценарий:
  1. collect_rooms_with_doors — помещения активного вида и их двери.
     Помещения берутся из текущей модели (видимые на виде) и из
     загруженных связей (уровень связи совпадает с уровнем плана, точка
     помещения — внутри подрезки вида). Двери — из того же документа,
     что и помещение: дверь относится к помещению, если точка чуть в
     стороне от двери (вдоль её FacingOrientation) попадает в это
     помещение (Document.GetRoomAtPoint, последняя стадия документа).
     Сторона двери, смотрящая в помещение, — «внутри», противоположная —
     «снаружи».
  2. SymbolIndex — типоразмеры проекта по (семейство, тип): состав типа
     точки доступа хранится в настройках по именам.
  3. place_access_point — для одной двери: состав выбранного для
     помещения типа точки доступа (skud_door_layout.composition_items) —
     каждое место пересчитывается в точку(и) модели по реальной
     ширине/высоте двери и толщине стены (у замка/геркона с кол-вом 2 —
     вторая точка зеркально относительно оси двери), и там создаётся
     экземпляр заданного типоразмера.

Как создаётся экземпляр (по FamilyPlacementType семейства):
  - на основе стены (OneLevelBasedHosted) — на стену двери, если дверь в
    текущей модели (в стену связи такой элемент поставить нельзя — тогда
    пробуется обычная вставка по уровню);
  - на основе грани/рабочей плоскости (WorkPlaneBased) — на поверхность
    стены с нужной стороны (у связи — через ссылку на грань связи);
    отступ «от стены» у таких элементов не применяется (они лежат на грани);
  - остальные — по уровню текущей модели, затем поворот, чтобы лицевая
    сторона смотрела от стены к наблюдателю.
После создания элемент при необходимости сдвигается точно в расчётную
точку (MoveElement), так что высота выставляется независимо от того, как
Revit трактует Z точки вставки у конкретного семейства.

Повторный запуск не плодит дубли: если в пределах DEDUPE_RADIUS_MM от
расчётной точки уже стоит экземпляр того же семейства — место
пропускается.
"""

import math

from Autodesk.Revit.DB import (
    XYZ, Line, Transform, FilteredElementCollector, BuiltInCategory, BuiltInParameter,
    RevitLinkInstance, FamilyInstance, LocationPoint, ElementTransformUtils, Wall,
    HostObjectUtils, ShellLayerType, FamilyPlacementType, Family, ViewPlan, StorageType
)
from Autodesk.Revit.DB.Structure import StructuralType

from lowlife import skud_door_layout as layout
from lowlife.geometry import find_level_for_elevation
from lowlife.scs import safe_element_name
from lowlife.room_info import _room_param_value

MM_TO_FT = 1.0 / 304.8
FT_TO_MM = 304.8

# Насколько далеко от полотна двери берётся пробная точка при поиске
# помещения по обе стороны двери (к половине толщины стены).
ROOM_PROBE_MM = 300.0
# Высота пробной точки над низом двери — внутри объёма помещения.
ROOM_PROBE_HEIGHT_MM = 1000.0
# Допуск уровня связи относительно уровня плана.
LEVEL_TOLERANCE_MM = 500.0
DEDUPE_RADIUS_MM = 100.0

_DOOR_WIDTH_PARAMS = (BuiltInParameter.DOOR_WIDTH, BuiltInParameter.FAMILY_WIDTH_PARAM)
_DOOR_HEIGHT_PARAMS = (BuiltInParameter.DOOR_HEIGHT, BuiltInParameter.FAMILY_HEIGHT_PARAM)
_DOOR_WIDTH_NAMES = (u"Ширина", u"Width", u"Ширина проема", u"Ширина проёма")
_DOOR_HEIGHT_NAMES = (u"Высота", u"Height", u"Высота проема", u"Высота проёма")


# ------------------------------------------------------------
# Помещения и двери
# ------------------------------------------------------------

class DoorSource(object):
    """Документ, откуда берутся помещения/двери: текущая модель или связь."""

    def __init__(self, doc, transform, link_instance, label):
        self.doc = doc
        self.transform = transform
        self.link_instance = link_instance
        self.label = label

    @property
    def is_link(self):
        return self.link_instance is not None


class DoorEntry(object):
    """Дверь помещения: сама дверь, её источник, знак стороны «внутри»
    (+1 — внутрь смотрит FacingOrientation двери, -1 — наоборот) и
    помещение с другой стороны (other_room; None — за дверью помещения
    нет, т.е. дверь наружу)."""

    def __init__(self, door, source, inner_sign, other_room=None):
        self.door = door
        self.source = source
        self.inner_sign = inner_sign
        self.other_room = other_room

    @property
    def unique_key(self):
        return u"{}|{}".format(self.source.label, self.door.UniqueId)

    @property
    def other_room_name(self):
        """Имя помещения за дверью (ROOM_NAME), None — за дверью помещения нет."""
        if self.other_room is None:
            return None
        return _room_text(self.other_room, BuiltInParameter.ROOM_NAME)

    def other_room_display(self, number_param):
        if self.other_room is None:
            return u"наружу (за дверью нет помещения)"
        return room_display_name(self.other_room, number_param)

    def label(self, number_param):
        """«Марка · Семейство : Тип → Коридор(1.01)» — для списка дверей помещения."""
        parts = []
        mark = u""
        try:
            p = self.door.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if p is not None and p.HasValue:
                mark = (p.AsString() or u"").strip()
        except:
            pass
        if mark:
            parts.append(mark)
        try:
            symbol = self.door.Symbol
            parts.append(u"{} : {}".format(safe_element_name(symbol.Family) or u"?",
                                           safe_element_name(symbol) or u"?"))
        except:
            pass
        return u"{}  →  {}".format(u" · ".join(parts) or u"Дверь", self.other_room_display(number_param))


def room_display_name(room, number_param):
    """«Имя(номер)»: номер — из параметра number_param помещения (пусто —
    штатный «Номер»); без номера — просто имя."""
    name = _room_text(room, BuiltInParameter.ROOM_NAME)
    if number_param:
        number = _room_param_value(room, number_param)
    else:
        number = _room_text(room, BuiltInParameter.ROOM_NUMBER)
    if not number:
        return name
    return u"{}({})".format(name, number)


class RoomEntry(object):
    def __init__(self, room, source):
        self.room = room
        self.source = source
        self.number = _room_text(room, BuiltInParameter.ROOM_NUMBER)
        self.name = _room_text(room, BuiltInParameter.ROOM_NAME)
        self.level_name = u""
        try:
            level = room.Level
            if level is not None:
                self.level_name = safe_element_name(level) or u""
        except:
            pass
        self.doors = []

    def display_name(self, number_param):
        return room_display_name(self.room, number_param)

    @property
    def key(self):
        """Ключ для запоминания выбранного типа точки доступа между запусками."""
        return u"{}|{}|{}".format(self.source.label, self.number, self.name)


def _room_text(room, bip):
    try:
        p = room.get_Parameter(bip)
        if p is not None and p.HasValue:
            return (p.AsString() or u"").strip()
    except:
        pass
    return u""


def _room_is_placed(room):
    try:
        return room.Location is not None and room.Area > 1e-6
    except:
        return False


def _door_sources(doc, view):
    sources = [DoorSource(doc, Transform.Identity, None, u"")]
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        linked_doc = link.GetLinkDocument()
        if linked_doc is None:
            continue
        try:
            if link.IsHidden(view):
                continue
        except:
            pass
        label = safe_element_name(link) or u"Связь"
        sources.append(DoorSource(linked_doc, link.GetTotalTransform(), link, label))
    return sources


def _point_in_crop(view, point):
    try:
        if not view.CropBoxActive:
            return True
        crop = view.CropBox
        local = crop.Transform.Inverse.OfPoint(point)
        return (crop.Min.X <= local.X <= crop.Max.X) and (crop.Min.Y <= local.Y <= crop.Max.Y)
    except:
        return True


def _link_rooms_on_view(source, view):
    level = getattr(view, "GenLevel", None)
    if level is None:
        return []
    tolerance = LEVEL_TOLERANCE_MM * MM_TO_FT
    rooms = []
    collector = FilteredElementCollector(source.doc) \
        .OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType()
    for room in collector:
        if not _room_is_placed(room):
            continue
        try:
            point = source.transform.OfPoint(room.Location.Point)
        except:
            continue
        if abs(point.Z - level.Elevation) > tolerance:
            continue
        if not _point_in_crop(view, point):
            continue
        rooms.append(room)
    return rooms


def _host_rooms_on_view(doc, view):
    collector = FilteredElementCollector(doc, view.Id) \
        .OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType()
    return [room for room in collector if _room_is_placed(room)]


def _door_point(door):
    try:
        loc = door.Location
        if isinstance(loc, LocationPoint):
            return loc.Point
    except:
        pass
    return None


def _horizontal_unit(vector):
    length = math.hypot(vector.X, vector.Y)
    if length < 1e-9:
        return None
    return XYZ(vector.X / length, vector.Y / length, 0)


def _wall_half_width(door):
    try:
        host = door.Host
        if isinstance(host, Wall):
            return host.Width / 2.0
    except:
        pass
    return 0.0


def collect_rooms_with_doors(doc, view):
    """
    Помещения активного вида (текущая модель + видимые связи) с их
    дверями. Возвращает список RoomEntry, отсортированный по источнику и
    номеру; помещения без дверей тоже входят (с пустым .doors).
    """
    entries = []

    for source in _door_sources(doc, view):
        if source.is_link:
            rooms = _link_rooms_on_view(source, view)
        else:
            rooms = _host_rooms_on_view(doc, view)
        if not rooms:
            continue

        by_id = {}
        for room in rooms:
            entry = RoomEntry(room, source)
            by_id[room.Id.IntegerValue] = entry
            entries.append(entry)

        doors = FilteredElementCollector(source.doc) \
            .OfCategory(BuiltInCategory.OST_Doors).WhereElementIsNotElementType()
        for door in doors:
            if not isinstance(door, FamilyInstance):
                continue
            origin = _door_point(door)
            facing = _horizontal_unit(door.FacingOrientation) if origin is not None else None
            if facing is None:
                continue
            reach = _wall_half_width(door) + ROOM_PROBE_MM * MM_TO_FT
            lift = XYZ(0, 0, ROOM_PROBE_HEIGHT_MM * MM_TO_FT)
            side_rooms = {}
            for sign in (1, -1):
                probe = origin + facing * (reach * sign) + lift
                try:
                    side_rooms[sign] = source.doc.GetRoomAtPoint(probe)
                except:
                    side_rooms[sign] = None
            for sign in (1, -1):
                room = side_rooms[sign]
                if room is None:
                    continue
                entry = by_id.get(room.Id.IntegerValue)
                if entry is None:
                    continue
                other = side_rooms[-sign]
                if other is not None and other.Id == room.Id:
                    continue  # обе стороны в одном помещении — дверь внутри помещения
                entry.doors.append(DoorEntry(door, source, sign, other))

    def sort_key(entry):
        return (entry.source.label, _natural(entry.number), entry.name)

    return sorted(entries, key=sort_key)


def _natural(text):
    import re
    parts = re.split(r"(\d+)", text or u"")
    return [int(p) if p.isdigit() else p.lower() for p in parts]


# ------------------------------------------------------------
# Типоразмеры
# ------------------------------------------------------------

class SymbolIndex(object):
    """Типоразмеры проекта по (семейство, тип) — имена без учёта регистра."""

    def __init__(self, doc):
        self._symbols = {}
        for family in FilteredElementCollector(doc).OfClass(Family):
            family_name = layout.normalize_family_name(safe_element_name(family))
            for symbol_id in family.GetFamilySymbolIds():
                symbol = doc.GetElement(symbol_id)
                type_name = safe_element_name(symbol) if symbol is not None else None
                if type_name:
                    self._symbols[(family_name, layout.normalize_family_name(type_name))] = symbol

    def get(self, family_name, type_name):
        return self._symbols.get((layout.normalize_family_name(family_name),
                                  layout.normalize_family_name(type_name)))


# ------------------------------------------------------------
# Геометрия двери и расстановка
# ------------------------------------------------------------

def _door_dimension(door, bips, names):
    candidates = [door]
    try:
        candidates.append(door.Symbol)
    except:
        pass
    for el in candidates:
        for bip in bips:
            try:
                p = el.get_Parameter(bip)
                if p is not None and p.HasValue and p.AsDouble() > 1e-6:
                    return p.AsDouble()
            except:
                pass
        for name in names:
            try:
                p = el.LookupParameter(name)
                if p is not None and p.HasValue and p.StorageType == StorageType.Double and p.AsDouble() > 1e-6:
                    return p.AsDouble()
            except:
                pass
    return None


def _side_faces(door):
    """[(signed_offset_ft, Reference)] граней стены двери в координатах
    документа двери; offset — расстояние от точки двери вдоль FacingOrientation."""
    faces = []
    try:
        wall = door.Host
    except:
        wall = None
    if not isinstance(wall, Wall):
        return faces
    origin = _door_point(door)
    facing = _horizontal_unit(door.FacingOrientation)
    for shell in (ShellLayerType.Exterior, ShellLayerType.Interior):
        try:
            refs = HostObjectUtils.GetSideFaces(wall, shell)
        except:
            continue
        for ref in refs:
            try:
                face = wall.GetGeometryObjectFromReference(ref)
                projected = face.Project(origin)
                if projected is None:
                    continue
                offset = (projected.XYZPoint - origin).DotProduct(facing)
                faces.append((offset, ref))
            except:
                continue
    return faces


class DoorFrame(object):
    """Геометрия одной двери в координатах текущей модели для расстановки."""

    def __init__(self, entry):
        door = entry.door
        transform = entry.source.transform
        local_origin = _door_point(door)
        local_facing = _horizontal_unit(door.FacingOrientation)

        self.ok = local_origin is not None and local_facing is not None
        if not self.ok:
            return

        self.entry = entry
        self.origin = transform.OfPoint(local_origin)
        facing = _horizontal_unit(transform.OfVector(local_facing))
        self.normals = {
            "inner": facing * entry.inner_sign,
            "outer": facing * (-entry.inner_sign),
        }

        width = _door_dimension(door, _DOOR_WIDTH_PARAMS, _DOOR_WIDTH_NAMES)
        height = _door_dimension(door, _DOOR_HEIGHT_PARAMS, _DOOR_HEIGHT_NAMES)
        self.width_mm = (width or 900.0 * MM_TO_FT) * FT_TO_MM
        self.height_mm = (height or 2100.0 * MM_TO_FT) * FT_TO_MM

        half = _wall_half_width(door)
        self.face_offsets = {"inner": half, "outer": half}
        self.face_refs = {"inner": None, "outer": None}
        for offset, ref in _side_faces(door):
            side_sign = 1 if offset >= 0 else -1
            side = "inner" if side_sign == entry.inner_sign else "outer"
            self.face_offsets[side] = abs(offset)
            self.face_refs[side] = ref

        try:
            host = door.Host
        except:
            host = None
        self.host_wall = host if (isinstance(host, Wall) and not entry.source.is_link) else None

    def target_points(self, key, slot):
        side, _role = layout.split_slot_key(key)
        return [self._to_model(side, local) for local in
                layout.slot_local_positions(key, slot, self.width_mm, self.height_mm)]

    def _to_model(self, side, local):
        normal = self.normals[side]
        x, y, z = layout.world_point(
            (self.origin.X, self.origin.Y, self.origin.Z),
            (normal.X, normal.Y, normal.Z),
            self.face_offsets[side], local, MM_TO_FT
        )
        return XYZ(x, y, z)

    def face_reference(self, side):
        ref = self.face_refs.get(side)
        if ref is None:
            return None
        if self.entry.source.is_link:
            try:
                return ref.CreateLinkReference(self.entry.source.link_instance)
            except:
                return None
        return ref

    def right_vector(self, side):
        n = self.normals[side]
        rx, ry, _rz = layout.viewer_right((n.X, n.Y, 0.0))
        return XYZ(rx, ry, 0)


def _placement_type(symbol):
    try:
        return symbol.Family.FamilyPlacementType
    except:
        return None


def _align_facing(doc, inst, point, normal):
    """Поворачивает экземпляр вокруг вертикали, чтобы FacingOrientation смотрел по normal."""
    try:
        facing = _horizontal_unit(inst.FacingOrientation)
    except:
        facing = None
    if facing is None:
        return
    angle = math.atan2(facing.X * normal.Y - facing.Y * normal.X, facing.DotProduct(normal))
    if abs(angle) < 1e-4:
        return
    try:
        axis = Line.CreateBound(point, point + XYZ.BasisZ)
        ElementTransformUtils.RotateElement(doc, inst.Id, axis, angle)
    except:
        pass


def _move_to(doc, inst, point, keep_normal=None):
    """Сдвигает экземпляр в point. keep_normal — не двигать вдоль этой
    нормали (элемент на стене должен остаться на её поверхности)."""
    try:
        loc = inst.Location
        if not isinstance(loc, LocationPoint):
            return
        delta = point - loc.Point
        if keep_normal is not None:
            delta = delta - keep_normal * delta.DotProduct(keep_normal)
        if delta.GetLength() > 1e-4:
            ElementTransformUtils.MoveElement(doc, inst.Id, delta)
    except:
        pass


def create_slot_instance(doc, symbol, frame, side, point, level):
    """Создаёт экземпляр symbol на месте side двери frame. None — не удалось."""
    if not symbol.IsActive:
        symbol.Activate()

    normal = frame.normals[side]
    placement = _placement_type(symbol)

    if placement == FamilyPlacementType.WorkPlaneBased:
        ref = frame.face_reference(side)
        if ref is not None:
            face_point = point - normal * (normal.DotProduct(point - frame.origin) - frame.face_offsets[side])
            try:
                inst = doc.Create.NewFamilyInstance(ref, face_point, frame.right_vector(side), symbol)
                return inst
            except:
                pass

    if placement == FamilyPlacementType.OneLevelBasedHosted and frame.host_wall is not None:
        try:
            inst = doc.Create.NewFamilyInstance(point, symbol, frame.host_wall, level,
                                                StructuralType.NonStructural)
            if inst is not None:
                try:
                    if inst.FacingOrientation.DotProduct(normal) < 0 and inst.CanFlipFacing:
                        inst.flipFacing()
                except:
                    pass
                _move_to(doc, inst, point, keep_normal=normal)
                return inst
        except:
            pass

    inst = None
    if level is not None:
        try:
            inst = doc.Create.NewFamilyInstance(point, symbol, level, StructuralType.NonStructural)
        except:
            inst = None
    if inst is None:
        try:
            inst = doc.Create.NewFamilyInstance(point, symbol, StructuralType.NonStructural)
        except:
            return None
    _move_to(doc, inst, point)
    _align_facing(doc, inst, point, normal)
    return inst


class ExistingIndex(object):
    """Уже стоящие экземпляры по имени семейства — для защиты от дублей."""

    def __init__(self, doc):
        self._by_family = {}
        collector = FilteredElementCollector(doc).OfClass(FamilyInstance)
        for inst in collector:
            point = _door_point(inst)
            if point is None:
                continue
            try:
                name = layout.normalize_family_name(safe_element_name(inst.Symbol.Family))
            except:
                continue
            self._by_family.setdefault(name, []).append(point)

    def has_near(self, family_name, point, radius_ft):
        for other in self._by_family.get(layout.normalize_family_name(family_name), []):
            if other.DistanceTo(point) <= radius_ft:
                return True
        return False

    def add(self, family_name, point):
        self._by_family.setdefault(layout.normalize_family_name(family_name), []).append(point)


def place_access_point(doc, entry, items, symbols, sorted_levels, existing):
    """
    Ставит состав типа точки доступа на дверь entry. items — результат
    skud_door_layout.composition_items: [(key, slot, family, type_name)].
    symbols — SymbolIndex. Транзакцию открывает вызывающий. Возвращает
    dict со счётчиками и списками имён для отчёта.
    """
    result = {"created": 0, "duplicate": 0, "failed": 0, "missing_types": [], "failed_names": []}

    frame = DoorFrame(entry)
    if not frame.ok:
        result["failed"] = len(items)
        result["failed_names"] = [family for _k, _s, family, _t in items]
        return result

    radius_ft = DEDUPE_RADIUS_MM * MM_TO_FT
    level = find_level_for_elevation(frame.origin.Z + 1e-3, sorted_levels)

    for key, slot, family_name, type_name in items:
        symbol = symbols.get(family_name, type_name)
        if symbol is None:
            result["missing_types"].append(u"{} : {}".format(family_name, type_name))
            continue

        side, _role = layout.split_slot_key(key)
        for point in frame.target_points(key, slot):
            if existing.has_near(family_name, point, radius_ft):
                result["duplicate"] += 1
                continue

            inst = create_slot_instance(doc, symbol, frame, side, point, level)
            if inst is None:
                result["failed"] += 1
                result["failed_names"].append(family_name)
                continue

            existing.add(family_name, _door_point(inst) or point)
            result["created"] += 1

    return result


# ------------------------------------------------------------
# Какие двери оснащаются
# ------------------------------------------------------------

def door_auto_included(entry, keywords, include_outside):
    """Решение фильтра по помещению за дверью (без учёта ручной правки)."""
    return layout.door_passes_filter(entry.other_room_name, keywords, include_outside)


def door_included(entry, keywords, include_outside, overrides):
    """С учётом ручной правки overrides ({door.unique_key: bool})."""
    manual = overrides.get(entry.unique_key)
    if manual is not None:
        return bool(manual)
    return door_auto_included(entry, keywords, include_outside)


# ------------------------------------------------------------
# Подсветка оснащаемых дверей на плане («Показать на плане»)
# ------------------------------------------------------------

PREVIEW_INCLUDED_COLOR = (0, 160, 60)
PREVIEW_EXCLUDED_COLOR = (220, 40, 40)
PREVIEW_MARGIN_MM = 250.0


def _circle_curves(center, radius):
    from Autodesk.Revit.DB import Arc
    return [
        Arc.Create(center, radius, 0.0, math.pi, XYZ.BasisX, XYZ.BasisY),
        Arc.Create(center, radius, math.pi, 2.0 * math.pi, XYZ.BasisX, XYZ.BasisY),
    ]


def _view_plane_z(view):
    level = getattr(view, "GenLevel", None)
    if level is not None:
        return level.Elevation
    try:
        return view.Origin.Z
    except:
        return 0.0


def draw_door_markers(doc, view, marked):
    """
    Рисует на view круги вокруг дверей: marked — [(DoorEntry, included)].
    Зелёный толстый круг — дверь будет оснащена, красный — дверь
    помещения исключена фильтром/вручную. Транзакцию открывает
    вызывающий. Возвращает список id созданных линий (int) — чтобы
    удалить их при следующем запуске (remove_door_markers).
    """
    from Autodesk.Revit.DB import OverrideGraphicSettings, Color

    styles = {}
    for included, rgb in ((True, PREVIEW_INCLUDED_COLOR), (False, PREVIEW_EXCLUDED_COLOR)):
        ogs = OverrideGraphicSettings()
        ogs.SetProjectionLineColor(Color(rgb[0], rgb[1], rgb[2]))
        ogs.SetProjectionLineWeight(10 if included else 6)
        styles[included] = ogs

    z = _view_plane_z(view)
    created = []
    for entry, included in marked:
        frame = DoorFrame(entry)
        if not frame.ok:
            continue
        radius = (frame.width_mm / 2.0 + PREVIEW_MARGIN_MM) * MM_TO_FT
        center = XYZ(frame.origin.X, frame.origin.Y, z)
        for curve in _circle_curves(center, radius):
            try:
                detail = doc.Create.NewDetailCurve(view, curve)
            except:
                continue
            try:
                view.SetElementOverrides(detail.Id, styles[included])
            except:
                pass
            created.append(detail.Id.IntegerValue)
    return created


def remove_door_markers(doc, marker_ids):
    """Удаляет линии подсветки прошлого «Показать на плане» (только линии
    детализации — чужие элементы с теми же id не трогаются)."""
    from Autodesk.Revit.DB import ElementId, DetailCurve
    removed = 0
    for value in marker_ids or []:
        try:
            el = doc.GetElement(ElementId(int(value)))
        except:
            el = None
        if el is None or not isinstance(el, DetailCurve):
            continue
        try:
            doc.Delete(el.Id)
            removed += 1
        except:
            pass
    return removed


def is_plan_view(view):
    return isinstance(view, ViewPlan)
