# -*- coding: utf-8 -*-
"""
Расстановка оборудования СС1 (SS1.panel/SS1Easy, «СС1-8Mile»). Revit-часть;
чистая логика — ss1_easy_core.py, настройки — ss1_easy_settings.py.

Сценарий (run):
  1. Удаление старого: все экземпляры выбранных типоразмеров кросса и
     кабельного подвода, стоящие на отмеченных уровнях, удаляются — кнопка
     каждый раз расставляет оборудование заново.
  2. Кроссы: шахты СС — экземпляры «Обобщённой модели» заданного семейства,
     у типа (или экземпляра) которых отмечена заданная галочка — параметр
     Да/Нет «СС» (у шахт других систем отмечены «СБ», «СПЗ»…). На каждом
     отмеченном уровне, через который шахта проходит (по высоте её
     габарита, ss1_easy_core.shaft_spans_level), в центре шахты ставятся
     два кросса на заданных высотах от уровня, повёрнутые по шахте + 90°
     (лицом от шахты и ещё на 90° по часовой — чтобы УГО стояло прямо). В
     параметр «Помещение» пишется «Ниша СС».
  3. Кабельные подводы: в каждой загруженной связи (АР) — двери между
     целевым помещением («Прихожая») и одним из соседних («Коридор»,
     «Вестибюль»), по последней стадии связи. У двухуровневой квартиры
     (одно имя лота на разных уровнях) берётся только нижняя прихожая;
     помещения без имени лота не группируются — подвод ставится в каждое,
     с предупреждением. Подвод ставится на грань стены двери со стороны
     квартиры (сторона прихожей определяется GetRoomAtPoint по обе стороны
     двери) и поворачивается лицом в прихожую; на уровне модели,
     совпадающем по отметке с уровнем двери (с учётом сдвига связи по Z),
     если этот уровень отмечен; в «Помещение» пишется имя лота.
     Грань стены берётся из геометрии стены (HostObjectUtils.GetSideFaces,
     ss1_easy_core.face_distance): точка двери лежит на линии привязки
     стены, а та бывает и по грани — половина толщины от неё уводила
     подвод в стену или на сторону коридора.
  4. Цепи: по электрической цепи на каждый подвод от кросса №1 шахты СС
     того же уровня и той же секции (ближайшей из них; параметры секции
     помещения и шахты — в настройках, без них — ближайшая шахта уровня),
     тип цепи — из настроек (выпадающий список, по умолчанию Data).
  5. LOI: поставленным кроссам и подводам копируются параметры из «Форм»
     (корпус, секция, этаж…) — по настройкам кнопки «Заполнение LOI»
     (loi_settings/loi_fill), как если бы её запустили для этих элементов.
  6. Маркировка (адрес устройства) подвода по маске из настроек: у каждой
     буквы маски свой параметр («A=Этаж; B=Секция; C=Номер квартиры»,
     ss1_easy_core.parse_letter_params/format_address); значения — у самого
     подвода (после LOI), иначе — у прихожей в связи.

Высота: экземпляр создаётся NewFamilyInstance(точка, тип, уровень) с
Z точки = смещению от уровня (отметка уровня не прибавляется) — так
работало в исходном скрипте пользователя на его семействах.
"""

try:
    unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3
    unicode = str


import math
from lowlife.i18n import tr

from Autodesk.Revit.DB import (
    XYZ, Line, FilteredElementCollector, BuiltInCategory, BuiltInParameter,
    RevitLinkInstance, FamilyInstance, Family, LocationPoint, LocationCurve,
    ElementTransformUtils, ElementId, Level, StorageType, Wall, HostObjectUtils,
    ShellLayerType
)
from Autodesk.Revit.DB.Structure import StructuralType

from lowlife import ss1_easy_core as core
from lowlife.electrical_circuits import create_circuit
from lowlife.scs import safe_element_name

MM_TO_FT = 1.0 / 304.8
FT_TO_MM = 304.8

# Поворот кросса относительно шахты: лицом от шахты (180°) и ещё на 90° по
# часовой стрелке, чтобы УГО на плане стояло прямо — итого +90° к
# направлению шахты (против часовой — положительный угол).
CROSS_ROTATION = math.pi / 2.0

# Зондирование помещений по обе стороны двери: насколько отступить от грани
# стены и на какую высоту подняться над точкой двери.
ROOM_PROBE_MM = 300.0
ROOM_PROBE_HEIGHT_MM = 1000.0

# Проверка, что точка подвода действительно в прихожей: насколько отойти
# от грани стены внутрь.
ROOM_CHECK_MM = 50.0

# Тип цепи, если в настройках его ещё не выбирали.
DEFAULT_SYSTEM_TYPE = u"Data"


def mm_to_ft(value_mm):
    return float(value_mm) * MM_TO_FT


# ------------------------------------------------------------
# Типоразмеры, параметры
# ------------------------------------------------------------

def find_symbol(doc, family_name, type_name):
    """FamilySymbol по имени семейства и типа (без учёта регистра) или None."""
    want_family = core.normalize(family_name)
    want_type = core.normalize(type_name)
    for family in FilteredElementCollector(doc).OfClass(Family):
        if core.normalize(safe_element_name(family)) != want_family:
            continue
        for symbol_id in family.GetFamilySymbolIds():
            symbol = doc.GetElement(symbol_id)
            if symbol is not None and core.normalize(safe_element_name(symbol)) == want_type:
                return symbol
    return None


def activate_symbol(doc, symbol):
    try:
        if not symbol.IsActive:
            symbol.Activate()
            doc.Regenerate()
    except Exception:
        pass


def _param_checked(param):
    """Галочка (Да/Нет) отмечена: целочисленное значение 1."""
    try:
        return param.StorageType == StorageType.Integer and param.AsInteger() == 1
    except Exception:
        return False


def _instance_and_type(element):
    result = [element]
    try:
        symbol = element.Symbol
        if symbol is not None:
            result.append(symbol)
    except Exception:
        pass
    return result


def _flag_checked(element, param_name):
    """Галочка param_name отмечена у типа или у экземпляра element."""
    if not param_name:
        return False
    for obj in reversed(_instance_and_type(element)):  # сначала тип
        try:
            param = obj.LookupParameter(param_name)
        except Exception:
            param = None
        if param is not None and param.HasValue and _param_checked(param):
            return True
    return False


def text_value(element, param_name):
    """Значение параметра экземпляра, иначе типа — текстом; пусто — u""."""
    if not param_name:
        return u""
    for obj in _instance_and_type(element):
        try:
            param = obj.LookupParameter(param_name)
            if param is None or not param.HasValue:
                continue
            if param.StorageType == StorageType.String:
                value = param.AsString()
            else:
                value = param.AsValueString()
            if value and value.strip():
                return value.strip()
        except Exception:
            pass
    return u""


def set_text_param(element, param_name, value):
    """Пишет строку в параметр экземпляра. True — записано."""
    if not param_name:
        return False
    try:
        param = element.LookupParameter(param_name)
        if param is None or param.IsReadOnly or param.StorageType != StorageType.String:
            return False
        param.Set(u"" if value is None else unicode(value))  # noqa: F821
        return True
    except Exception:
        return False


def _family_name(element):
    try:
        symbol = element.Symbol
        if symbol is not None and symbol.Family is not None:
            return safe_element_name(symbol.Family)
    except Exception:
        pass
    return None


def _instance_level_id(element):
    try:
        level_id = element.LevelId
        if level_id is not None and level_id != ElementId.InvalidElementId:
            return level_id
    except Exception:
        pass
    for bip in (BuiltInParameter.FAMILY_LEVEL_PARAM, BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM):
        try:
            param = element.get_Parameter(bip)
            if param is not None:
                level_id = param.AsElementId()
                if level_id is not None and level_id != ElementId.InvalidElementId:
                    return level_id
        except Exception:
            pass
    return None


# ------------------------------------------------------------
# Уровни и создание экземпляров
# ------------------------------------------------------------

def get_levels(doc):
    levels = list(FilteredElementCollector(doc).OfClass(Level).WhereElementIsNotElementType())
    levels.sort(key=lambda lv: lv.ProjectElevation)
    return levels


def set_instance_level(instance, level):
    """Назначает экземпляру уровень через параметр «Уровень». True — назначен."""
    for bip in (BuiltInParameter.FAMILY_LEVEL_PARAM, BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM):
        try:
            param = instance.get_Parameter(bip)
            if param is not None and not param.IsReadOnly:
                param.Set(level.Id)
                return True
        except Exception:
            pass
    return False


def create_on_level(doc, x, y, offset_mm, symbol, level):
    """
    Экземпляр на уровне со смещением offset_mm. В Z точки передаётся только
    смещение (отметка уровня не прибавляется) — как в исходном скрипте.
    """
    point = XYZ(x, y, mm_to_ft(offset_mm))
    try:
        instance = doc.Create.NewFamilyInstance(point, symbol, level, StructuralType.NonStructural)
        doc.Regenerate()
        set_instance_level(instance, level)
        return instance
    except Exception:
        pass

    instance = doc.Create.NewFamilyInstance(point, symbol, StructuralType.NonStructural)
    doc.Regenerate()
    if not set_instance_level(instance, level):
        raise Exception(tr(u"не удалось назначить уровень экземпляру Id {}").format(
            instance.Id.IntegerValue))
    doc.Regenerate()
    return instance


def rotate_instance(doc, instance, angle):
    """Поворот вокруг вертикальной оси через точку вставки экземпляра."""
    if abs(angle) < 1e-9:
        return
    location = instance.Location
    if not isinstance(location, LocationPoint):
        return
    point = location.Point
    axis = Line.CreateBound(point, XYZ(point.X, point.Y, point.Z + 10.0))
    ElementTransformUtils.RotateElement(doc, instance.Id, axis, angle)


# ------------------------------------------------------------
# Удаление старого
# ------------------------------------------------------------

def delete_old(doc, symbols, level_ids):
    """
    Удаляет все экземпляры типоразмеров symbols, стоящие на уровнях
    level_ids (множество IntegerValue). Возвращает {symbol_id: число}.
    """
    from System.Collections.Generic import List

    type_ids = set(s.Id.IntegerValue for s in symbols)
    counts = dict((s.Id.IntegerValue, 0) for s in symbols)
    to_delete = List[ElementId]()
    for instance in FilteredElementCollector(doc).OfClass(FamilyInstance):
        try:
            type_id = instance.GetTypeId().IntegerValue
        except Exception:
            continue
        if type_id not in type_ids:
            continue
        level_id = _instance_level_id(instance)
        if level_id is None or level_id.IntegerValue not in level_ids:
            continue
        to_delete.Add(instance.Id)
        counts[type_id] += 1
    if to_delete.Count:
        doc.Delete(to_delete)
    return counts


# ------------------------------------------------------------
# Шахты и кроссы
# ------------------------------------------------------------

def is_ss_shaft(element, settings):
    """
    Шахта СС: у типа (или экземпляра) отмечена галочка shaft_param («СС»;
    у шахт других систем отмечены «СБ», «СПЗ»…).
    """
    return _flag_checked(element, (settings.get("shaft_param") or u"").strip())


def facing_angle(element):
    for attr in ("FacingOrientation", "HandOrientation"):
        try:
            vector = getattr(element, attr)
            if vector is not None and (abs(vector.X) > 1e-9 or abs(vector.Y) > 1e-9):
                return math.atan2(vector.Y, vector.X)
        except Exception:
            pass
    return 0.0


def collect_ss_shafts(doc, settings):
    """[(шахта, центр XYZ, низ Z, верх Z, секция)] шахт СС текущей модели."""
    family_name = core.normalize(settings.get("shaft_family_name"))
    section_param = (settings.get("shaft_section_param") or u"").strip()
    result = []
    collector = (FilteredElementCollector(doc)
                 .OfCategory(BuiltInCategory.OST_GenericModel)
                 .WhereElementIsNotElementType())
    for element in collector:
        if core.normalize(_family_name(element)) != family_name:
            continue
        if not is_ss_shaft(element, settings):
            continue
        bbox = element.get_BoundingBox(None)
        if bbox is None:
            continue
        center = XYZ((bbox.Min.X + bbox.Max.X) / 2.0,
                     (bbox.Min.Y + bbox.Max.Y) / 2.0,
                     (bbox.Min.Z + bbox.Max.Z) / 2.0)
        result.append((element, center, bbox.Min.Z, bbox.Max.Z,
                       text_value(element, section_param)))
    return result


class Result(object):
    def __init__(self):
        self.shafts = 0
        self.crosses = 0
        self.shaft_levels_skipped = 0
        self.doors = 0
        self.feeds = 0
        self.deleted_crosses = 0
        self.deleted_feeds = 0
        self.feeds_unoriented = 0
        self.circuits = 0
        self.circuits_failed = 0
        self.loi_filled = 0
        self.loi_skipped = None   # причина, если LOI не заполнялось вовсе
        self.addresses = 0
        self.diagnostics = []
        # Для цепей: {level_id: [(кросс №1, x, y, секция шахты)]} и
        # [(подвод, x, y, секция помещения, level_id, имя уровня,
        #   {буква маски: значение её параметра у прихожей})];
        # все поставленные кроссы — для LOI.
        self.panel_crosses = {}
        self.placed_feeds = []
        self.placed_crosses = []


def place_crosses(doc, shafts, levels, settings, symbol, result):
    tol = mm_to_ft(settings.get("level_tolerance_mm") or 0.0)
    heights = [settings.get("cross_height_1_mm"), settings.get("cross_height_2_mm")]
    room_param = (settings.get("room_param_name") or u"").strip()
    niche_text = settings.get("niche_text") or u""
    seen = set()

    for level in levels:
        level_z = level.ProjectElevation
        for shaft, center, min_z, max_z, section in shafts:
            if not core.shaft_spans_level(min_z, max_z, level_z, tol):
                result.shaft_levels_skipped += 1
                continue
            key = core.dedupe_key(center.X, center.Y, level.Id.IntegerValue)
            if key in seen:
                result.diagnostics.append(
                    tr(u"Шахта Id {}: на уровне «{}» в той же точке уже есть шахта СС — "
                    u"кроссы не дублируются.").format(shaft.Id.IntegerValue, level.Name))
                continue
            seen.add(key)

            angle = facing_angle(shaft) + CROSS_ROTATION
            for number, height in enumerate(heights, 1):
                try:
                    instance = create_on_level(doc, center.X, center.Y, height, symbol, level)
                    rotate_instance(doc, instance, angle)
                    if room_param and not set_text_param(instance, room_param, niche_text):
                        result.diagnostics.append(
                            tr(u"Кросс Id {}: не удалось записать «{}».").format(
                                instance.Id.IntegerValue, room_param))
                    result.crosses += 1
                    result.placed_crosses.append(instance)
                    if number == 1:
                        result.panel_crosses.setdefault(level.Id.IntegerValue, []).append(
                            (instance, center.X, center.Y, section))
                except Exception as ex:
                    result.diagnostics.append(
                        tr(u"Шахта Id {}, уровень «{}»: ошибка установки кросса №{}: {}").format(
                            shaft.Id.IntegerValue, level.Name, number, ex))


# ------------------------------------------------------------
# Двери связей и кабельные подводы
# ------------------------------------------------------------

def _room_name(room):
    if room is None:
        return u""
    try:
        param = room.get_Parameter(BuiltInParameter.ROOM_NAME)
        if param is not None and param.AsString():
            return param.AsString().strip()
    except Exception:
        pass
    try:
        return (safe_element_name(room) or u"").strip()
    except Exception:
        return u""


def _room_text_param(room, param_name):
    try:
        param = room.LookupParameter(param_name)
        if param is not None:
            value = param.AsString()
            if value is None:
                value = param.AsValueString()
            if value:
                return value.strip()
    except Exception:
        pass
    return u""


def _room_elevation(link_doc, room):
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


def _door_rooms(door, phase):
    try:
        return door.get_FromRoom(phase), door.get_ToRoom(phase)
    except Exception:
        return None, None


def _door_point(door):
    try:
        location = door.Location
        if isinstance(location, LocationPoint):
            return location.Point
        if isinstance(location, LocationCurve):
            return location.Curve.Evaluate(0.5, True)
    except Exception:
        pass
    try:
        bbox = door.get_BoundingBox(None)
        if bbox is not None:
            return bbox.Min.Add(bbox.Max).Divide(2.0)
    except Exception:
        pass
    return None


def _door_level_z(door, link_doc, transform):
    """Отметка уровня двери в координатах модели (сдвиг связи по Z учтён)."""
    level_id = None
    try:
        param = door.get_Parameter(BuiltInParameter.FAMILY_LEVEL_PARAM)
        if param is not None:
            level_id = param.AsElementId()
    except Exception:
        pass
    if level_id is None or level_id == ElementId.InvalidElementId:
        try:
            level_id = door.LevelId
        except Exception:
            level_id = None
    if level_id is not None and level_id != ElementId.InvalidElementId:
        level = link_doc.GetElement(level_id)
        if isinstance(level, Level):
            return transform.OfPoint(XYZ(0, 0, level.ProjectElevation)).Z
    point = _door_point(door)
    if point is not None:
        return transform.OfPoint(point).Z
    return None


def _horizontal_unit(vector):
    try:
        length = math.hypot(vector.X, vector.Y)
    except Exception:
        return None
    if length < 1e-9:
        return None
    return XYZ(vector.X / length, vector.Y / length, 0)


def _wall_half_width(door):
    try:
        host = door.Host
        if isinstance(host, Wall):
            return host.Width / 2.0
    except Exception:
        pass
    return 0.0


def _side_face_offsets(door, origin, facing):
    """
    Смещения граней стены двери от точки двери вдоль facing (со знаком), в
    координатах документа двери. Пусто — граней не нашлось (не стена и т.п.).
    """
    offsets = []
    try:
        wall = door.Host
    except Exception:
        wall = None
    if not isinstance(wall, Wall):
        return offsets
    for shell in (ShellLayerType.Exterior, ShellLayerType.Interior):
        try:
            refs = HostObjectUtils.GetSideFaces(wall, shell)
        except Exception:
            continue
        for ref in refs:
            try:
                face = wall.GetGeometryObjectFromReference(ref)
                projected = face.Project(origin)
                if projected is None:
                    continue
                offsets.append(projected.XYZPoint.Subtract(origin).DotProduct(facing))
            except Exception:
                continue
    return offsets


def _room_id_at(link_doc, point, phase):
    try:
        room = link_doc.GetRoomAtPoint(point, phase)
    except Exception:
        room = None
    return room.Id.IntegerValue if room is not None else None


def apartment_side(door, link_doc, phase, target_room_id, inset_ft=0.0):
    """
    (точка подвода, нормаль в прихожую) — обе в координатах связи, — или
    None, если не удалось понять, с какой стороны двери прихожая.

    Сторона — зондированием: точка в стороне от грани стены (вдоль
    FacingOrientation двери и в обратную сторону) проверяется
    GetRoomAtPoint; где прихожая — туда и ставим. Точка подвода — на грани
    стены с этой стороны (core.face_distance по реальным граням стены, не по
    половине толщины) плюс inset_ft внутрь; ещё раз проверяется, что чуть
    дальше от неё — прихожая.
    """
    origin = _door_point(door)
    try:
        facing = _horizontal_unit(door.FacingOrientation)
    except Exception:
        facing = None
    if origin is None or facing is None:
        return None
    half = _wall_half_width(door)
    offsets = _side_face_offsets(door, origin, facing)
    lift = XYZ(0, 0, ROOM_PROBE_HEIGHT_MM * MM_TO_FT)
    for sign in (1, -1):
        normal = facing.Multiply(sign)
        face = core.face_distance(offsets, sign, half)
        probe = origin.Add(normal.Multiply(face + ROOM_PROBE_MM * MM_TO_FT)).Add(lift)
        if _room_id_at(link_doc, probe, phase) != target_room_id:
            continue
        point = origin.Add(normal.Multiply(face + inset_ft))
        check = point.Add(normal.Multiply(ROOM_CHECK_MM * MM_TO_FT)).Add(lift)
        if _room_id_at(link_doc, check, phase) != target_room_id:
            # грань определилась неверно — ставим на ту глубину, где точно прихожая
            point = origin.Add(normal.Multiply(face + ROOM_PROBE_MM * MM_TO_FT))
        return point, normal
    return None


def align_facing(doc, instance, normal):
    """Поворачивает экземпляр вокруг вертикали так, чтобы он смотрел по normal."""
    try:
        have = _horizontal_unit(instance.FacingOrientation)
    except Exception:
        have = None
    if have is None:
        return False
    angle = math.atan2(normal.Y, normal.X) - math.atan2(have.Y, have.X)
    rotate_instance(doc, instance, angle)
    return True


def _link_label(link_instance):
    try:
        return safe_element_name(link_instance) or tr(u"связь")
    except Exception:
        return tr(u"связь")


def place_feeds(doc, levels, settings, symbol, offset_mm, result):
    target_name = settings.get("target_room_name") or u""
    neighbors = core.split_names(settings.get("neighbor_room_names"))
    lot_param = (settings.get("lot_param_name") or u"").strip()
    room_param = (settings.get("room_param_name") or u"").strip()
    section_param = (settings.get("room_section_param") or u"").strip()
    address_params, _ = core.parse_letter_params(settings.get("address_letters"))
    inset_ft = mm_to_ft(settings.get("feed_wall_inset_mm") or 0.0)
    tol = mm_to_ft(settings.get("level_tolerance_mm") or 0.0)
    level_marks = [(level, level.ProjectElevation) for level in levels]

    links = list(FilteredElementCollector(doc).OfClass(RevitLinkInstance))
    if not links:
        result.diagnostics.append(tr(u"В проекте нет ни одной связи — кабельные подводы не ставятся."))
        return

    for link_instance in links:
        try:
            link_doc = link_instance.GetLinkDocument()
        except Exception:
            link_doc = None
        if link_doc is None:
            continue
        label = _link_label(link_instance)
        transform = link_instance.GetTotalTransform()

        phases = link_doc.Phases
        if phases is None or phases.Size == 0:
            continue
        phase = phases.get_Item(phases.Size - 1)

        # Целевые помещения связи: у дуплекса — только нижнее.
        rooms = []
        room_lots = {}
        room_sections = {}
        room_address = {}
        room_collector = (FilteredElementCollector(link_doc)
                          .OfCategory(BuiltInCategory.OST_Rooms)
                          .WhereElementIsNotElementType())
        for room in room_collector:
            if core.normalize(_room_name(room)) != core.normalize(target_name):
                continue
            lot = _room_text_param(room, lot_param)
            room_lots[room.Id.IntegerValue] = lot
            room_sections[room.Id.IntegerValue] = (
                _room_text_param(room, section_param) if section_param else u"")
            room_address[room.Id.IntegerValue] = dict(
                (letter, _room_text_param(room, name) if name else u"")
                for letter, name in address_params)
            rooms.append((room.Id.IntegerValue, lot, _room_elevation(link_doc, room)))
        keep, _ = core.lowest_room_per_lot(rooms)
        warned_rooms = set()

        door_collector = (FilteredElementCollector(link_doc)
                          .OfCategory(BuiltInCategory.OST_Doors)
                          .WhereElementIsNotElementType())
        for door in door_collector:
            try:
                from_room, to_room = _door_rooms(door, phase)
                side = core.door_target_side(
                    _room_name(from_room), _room_name(to_room), target_name, neighbors)
                if side is None:
                    continue
                room = from_room if side == "from" else to_room
                room_id = room.Id.IntegerValue
                if room_id not in keep:
                    continue

                level_z = _door_level_z(door, link_doc, transform)
                level = core.match_level(level_z, level_marks, tol) if level_z is not None else None
                if level is None:
                    continue

                result.doors += 1
                side_info = apartment_side(door, link_doc, phase, room_id, inset_ft)
                host_normal = None
                if side_info is not None:
                    point, normal = side_info
                    host_normal = transform.OfVector(normal)
                else:
                    point = _door_point(door)
                    if point is None:
                        result.diagnostics.append(
                            tr(u"{}: дверь Id {} — не удалось определить точку.").format(
                                label, door.Id.IntegerValue))
                        continue
                host_point = transform.OfPoint(point)

                lot = room_lots.get(room_id) or u""
                instance = create_on_level(doc, host_point.X, host_point.Y, offset_mm, symbol, level)
                result.feeds += 1
                if host_normal is None or not align_facing(doc, instance, host_normal):
                    result.feeds_unoriented += 1
                    result.diagnostics.append(
                        tr(u"{}: дверь Id {} — не удалось определить сторону квартиры, подвод "
                        u"Id {} поставлен по оси стены без поворота.").format(
                            label, door.Id.IntegerValue, instance.Id.IntegerValue))
                result.placed_feeds.append(
                    (instance, host_point.X, host_point.Y, room_sections.get(room_id) or u"",
                     level.Id.IntegerValue, level.Name, room_address.get(room_id) or {}))
                if not lot:
                    if room_id not in warned_rooms:
                        warned_rooms.add(room_id)
                        result.diagnostics.append(
                            tr(u"ВНИМАНИЕ. {}: у помещения «{}» Id {} не заполнено «{}» — "
                            u"подвод Id {} поставлен без имени лота.").format(
                                label, target_name, room_id, lot_param,
                                instance.Id.IntegerValue))
                elif room_param and not set_text_param(instance, room_param, lot):
                    result.diagnostics.append(
                        tr(u"Подвод Id {}: не удалось записать «{}».").format(
                            instance.Id.IntegerValue, room_param))
            except Exception as ex:
                result.diagnostics.append(tr(u"{}: дверь Id {} — ошибка: {}").format(
                    label, door.Id.IntegerValue, ex))


# ------------------------------------------------------------
# Электрические цепи кросс №1 → подвод
# ------------------------------------------------------------

def build_circuits(doc, settings, result):
    """
    По цепи на каждый подвод от кросса №1 шахты СС того же уровня: той же
    секции (ближайшей из них), если заданы оба параметра секции, иначе —
    ближайшей шахты уровня (core.pick_shaft).
    """
    by_section = bool((settings.get("room_section_param") or u"").strip()
                      and (settings.get("shaft_section_param") or u"").strip())

    for feed, x, y, section, level_id, level_name, _ in result.placed_feeds:
        crosses = result.panel_crosses.get(level_id, [])
        candidates = [(index, cx, cy, csec if by_section else u"")
                      for index, (_, cx, cy, csec) in enumerate(crosses)]
        index, reason = core.pick_shaft(x, y, section if by_section else u"", candidates)
        if reason == "no_room_section" and by_section:
            result.diagnostics.append(
                tr(u"Подвод Id {}: у помещения не заполнена секция — цепь от ближайшей "
                u"шахты уровня «{}».").format(feed.Id.IntegerValue, level_name))
        if index is None:
            result.circuits_failed += 1
            if reason == "no_section":
                why = tr(u"на уровне нет шахты СС секции «{}»").format(section)
            else:
                why = tr(u"на уровне нет кроссов")
            result.diagnostics.append(tr(u"Подвод Id {} (уровень «{}»): цепь не создана — {}.").format(
                feed.Id.IntegerValue, level_name, why))
            continue

        cross = crosses[index][0]
        system_type = settings.get("circuit_system_type") or DEFAULT_SYSTEM_TYPE
        try:
            circuit, error = create_circuit(doc, cross, [feed], system_type)
        except Exception as ex:
            circuit, error = None, ex
        if circuit is None:
            result.circuits_failed += 1
            result.diagnostics.append(tr(u"Подвод Id {} → кросс Id {}: цепь не создана: {}").format(
                feed.Id.IntegerValue, cross.Id.IntegerValue, error))
        else:
            result.circuits += 1


# ------------------------------------------------------------
# LOI и адрес устройства
# ------------------------------------------------------------

def fill_loi(doc, elements, result):
    """
    Заполнение LOI для поставленных элементов — по настройкам кнопки
    «Заполнение LOI»: параметры (корпус, секция, этаж…) копируются из
    «Формы», внутри которой стоит элемент. Попал в несколько форм — берётся
    первая, с сообщением в отчёте; ни в одну — сообщение.
    """
    from lowlife import loi_fill, loi_settings

    loi = loi_settings.get_settings_silent()
    param_names = loi_settings.get_param_names(loi)
    if not param_names:
        result.loi_skipped = (tr(u"не заданы параметры в настройках кнопки «Заполнение LOI» "
                              u"(Shift+клик по ней)"))
        return
    if not elements:
        return
    forms_found = loi_fill.find_forms(doc, loi_fill.FORM_CATEGORY_NAME,
                                      locations=loi_settings.get_search_locations(loi))
    if not forms_found:
        result.loi_skipped = tr(u"не найдено ни одной «Формы» в моделях из настроек «Заполнение LOI»")
        return

    matches = loi_fill.classify_elements(forms_found, elements)
    for element in elements:
        match = matches.get(element.Id)
        if match is None:
            result.diagnostics.append(
                tr(u"LOI: элемент Id {} не попал ни в одну «Форму» — не заполнен.").format(
                    element.Id.IntegerValue))
            continue
        if len(match.forms) > 1:
            result.diagnostics.append(
                tr(u"LOI: элемент Id {} попал в {} «Формы» — взята первая.").format(
                    element.Id.IntegerValue, len(match.forms)))
        values = loi_fill.collect_form_values(match.forms[0].element, param_names)
        failed = [name for name, _, ok in loi_fill.apply_values(element, values) if not ok]
        if failed:
            result.diagnostics.append(tr(u"LOI: элемент Id {} — не записано: {}.").format(
                element.Id.IntegerValue, u", ".join(failed)))
        result.loi_filled += 1


def fill_addresses(doc, settings, result):
    """
    Маркировка (адрес устройства) подводов по маске (core.format_address):
    у каждой буквы маски — свой параметр (строка «буква = параметр» в
    настройках, core.parse_letter_params); значение — у самого подвода
    (после LOI), иначе — у прихожей в связи.
    """
    address_param = (settings.get("device_address_param") or u"").strip()
    if not address_param:
        return
    mask = settings.get("address_mask") or u""
    letters, errors = core.parse_letter_params(settings.get("address_letters"))
    if errors:
        result.diagnostics.append(tr(u"Маркировка: ошибки в «Параметрах букв маски»: {}.").format(
            u"; ".join(errors)))
    if not letters:
        result.diagnostics.append(
            tr(u"Маркировка не заполнена: не заданы параметры букв маски (Shift+клик → "
            u"«Помещения, параметры и высоты…», раздел ④)."))
        return
    for feed, _, _, _, _, _, room_values in result.placed_feeds:
        values = {}
        for letter, name in letters:
            values[letter] = text_value(feed, name) or room_values.get(letter) or u""
        address, missing = core.format_address(mask, values)
        if missing:
            result.diagnostics.append(
                tr(u"Маркировка подвода Id {}: нет значения {} — записано «{}».").format(
                    feed.Id.IntegerValue,
                    u", ".join(u"{} ({})".format(letter, dict(letters)[letter]) for letter in missing),
                    address))
        if set_text_param(feed, address_param, address):
            result.addresses += 1
        else:
            result.diagnostics.append(tr(u"Маркировка подвода Id {}: не удалось записать «{}».").format(
                feed.Id.IntegerValue, address_param))


# ------------------------------------------------------------
# Целиком
# ------------------------------------------------------------

def run(doc, levels, offset_mm, settings, cross_symbol, feed_symbol):
    """Всё внутри уже открытой транзакции. Возвращает Result."""
    result = Result()
    activate_symbol(doc, cross_symbol)
    activate_symbol(doc, feed_symbol)

    level_ids = set(level.Id.IntegerValue for level in levels)
    deleted = delete_old(doc, [cross_symbol, feed_symbol], level_ids)
    result.deleted_crosses = deleted.get(cross_symbol.Id.IntegerValue, 0)
    if feed_symbol.Id != cross_symbol.Id:
        result.deleted_feeds = deleted.get(feed_symbol.Id.IntegerValue, 0)

    shafts = collect_ss_shafts(doc, settings)
    result.shafts = len(shafts)
    place_crosses(doc, shafts, levels, settings, cross_symbol, result)
    place_feeds(doc, levels, settings, feed_symbol, offset_mm, result)
    doc.Regenerate()
    build_circuits(doc, settings, result)
    fill_loi(doc, result.placed_crosses + [feed[0] for feed in result.placed_feeds], result)
    fill_addresses(doc, settings, result)
    return result


# ------------------------------------------------------------
# Окно запуска: уровни + смещение подвода
# ------------------------------------------------------------

def ask_levels_and_offset(doc, default_offset_mm):
    """
    Окно выбора уровней и смещения кабельного подвода. Возвращает
    (уровни, смещение_мм) или (None, None) при отмене.
    """
    import clr
    clr.AddReference("PresentationFramework")
    clr.AddReference("PresentationCore")
    clr.AddReference("WindowsBase")
    from System.Windows import (
        Window, Thickness, WindowStartupLocation, ResizeMode, HorizontalAlignment
    )
    from System.Windows.Controls import (
        StackPanel, TextBlock, TextBox, Button, ScrollViewer, CheckBox, Orientation,
        ScrollBarVisibility
    )
    from pyrevit import forms

    levels = get_levels(doc)
    if not levels:
        forms.alert(tr(u"В проекте нет ни одного уровня."), title=tr(u"СС1-8Mile"))
        return None, None

    window = Window()
    window.Title = tr(u"СС1-8Mile — кроссы и кабельные подводы")
    window.Width = 440
    window.Height = 625
    window.MinWidth = 400
    window.MinHeight = 485
    window.ResizeMode = ResizeMode.CanResize
    window.WindowStartupLocation = WindowStartupLocation.CenterScreen

    root = StackPanel()
    root.Margin = Thickness(14)
    window.Content = root

    header = TextBlock()
    header.Text = tr(u"Уровни для установки оборудования:")
    header.Margin = Thickness(0, 0, 0, 8)
    root.Children.Add(header)

    scroll = ScrollViewer()
    scroll.Height = 365
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    level_panel = StackPanel()
    scroll.Content = level_panel
    root.Children.Add(scroll)

    checks = []
    for level in levels:
        try:
            label = tr(u"{}   ({:.0f} мм)").format(level.Name, float(level.Elevation) * FT_TO_MM)
        except Exception:
            label = level.Name
        cb = CheckBox()
        cb.Content = label
        cb.IsChecked = True
        cb.Tag = level
        cb.Margin = Thickness(2, 3, 2, 3)
        level_panel.Children.Add(cb)
        checks.append(cb)

    select_row = StackPanel()
    select_row.Orientation = Orientation.Horizontal
    select_row.Margin = Thickness(0, 6, 0, 0)
    root.Children.Add(select_row)

    def add_select_button(text, checked):
        button = Button()
        button.Content = text
        button.Padding = Thickness(10, 2, 10, 2)
        button.Margin = Thickness(0, 0, 8, 0)

        def on_click(sender, args):
            for cb in checks:
                cb.IsChecked = checked

        button.Click += on_click
        select_row.Children.Add(button)

    add_select_button(tr(u"Отметить все"), True)
    add_select_button(tr(u"Снять все"), False)

    offset_label = TextBlock()
    offset_label.Text = tr(u"Смещение кабельного подвода от уровня, мм:")
    offset_label.Margin = Thickness(0, 12, 0, 4)
    root.Children.Add(offset_label)

    offset_box = TextBox()
    offset_box.Text = u"{:.0f}".format(float(default_offset_mm))
    offset_box.Margin = Thickness(0, 0, 0, 12)
    root.Children.Add(offset_box)

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    root.Children.Add(buttons)

    ok_button = Button()
    ok_button.Content = tr(u"Запустить")
    ok_button.Width = 100
    ok_button.Margin = Thickness(0, 0, 8, 0)
    buttons.Children.Add(ok_button)

    cancel_button = Button()
    cancel_button.Content = tr(u"Отмена")
    cancel_button.Width = 90
    buttons.Children.Add(cancel_button)

    state = {"result": None}

    def on_ok(sender, args):
        checked = [cb.Tag for cb in checks if cb.IsChecked]
        if not checked:
            forms.alert(tr(u"Отметьте хотя бы один уровень."), title=tr(u"СС1-8Mile"))
            return
        try:
            value = float(offset_box.Text.strip().replace(u",", u"."))
            if value < 0:
                raise ValueError()
        except Exception:
            forms.alert(tr(u"Введите неотрицательное число для смещения подвода."), title=tr(u"СС1-8Mile"))
            return
        state["result"] = (checked, value)
        window.Close()

    def on_cancel(sender, args):
        window.Close()

    ok_button.Click += on_ok
    cancel_button.Click += on_cancel
    window.ShowDialog()

    if state["result"] is None:
        return None, None
    return state["result"]
