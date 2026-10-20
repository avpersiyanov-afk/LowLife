# -*- coding: utf-8 -*-
u"""
Лючки в местах пересечения кабельных лотков с уровнями — Revit-часть кнопки
«Лючки на уровнях» (ToolsTraySection.panel/TrayHatches). Геометрия (точки
пересечения, размер косого сечения, повторы) — tray_hatch_core, настройки —
tray_hatch_settings.

Порядок: лотки (выделенные, иначе все лотки модели — не связи) → ось лотка
из LocationCurve, направления сечения: высота — CableTray.CurveNormal,
ширина — ось × высота (запасной вариант — BasisX/BasisY системы координат
коннектора) → пересечения оси с плоскостями «отметка уровня + смещение»
(Level.ProjectElevation — в координатах модели, как и геометрия, а не
Level.Elevation от базовой точки) → по точке лючок: новый экземпляр
NewFamilyInstance(точка, тип, уровень) или уже стоящий рядом на том же
уровне экземпляр того же семейства — у него обновляются размер и поворот.

Размеры пишутся в параметры экземпляра; если параметр — типа, берётся тип
того же семейства с таким размером или создаётся копией выбранного
(«<тип> 300×200»). Лючок кладётся в рабочий набор своего лотка.
"""

import math

from Autodesk.Revit.DB import (
    BuiltInParameter, Element, ElementId, ElementTransformUtils, FamilyInstance,
    FamilySymbol, FilteredElementCollector, Level, Line, LocationCurve, LocationPoint,
    StorageType, XYZ,
)
from Autodesk.Revit.DB.Electrical import CableTray
from Autodesk.Revit.DB.Structure import StructuralType

from lowlife import tray_hatch_core as core

MM_TO_FT = 1.0 / 304.8
FT_TO_MM = 304.8

_END_TOL = 1.0 * MM_TO_FT      # конец лотка «на уровне»
_DEDUPE_TOL = 50.0 * MM_TO_FT  # одна и та же точка с соседних участков
_MATCH_TOL = 100.0 * MM_TO_FT  # уже стоящий лючок «в этой точке»
_SIZE_TOL = 0.5 * MM_TO_FT     # размер типа «тот же»


class HatchError(Exception):
    u"""Остановить расстановку с понятным сообщением (транзакция откатывается)."""


def _name(el):
    try:
        return Element.Name.GetValue(el) or u""
    except Exception:
        try:
            return el.Name or u""
        except Exception:
            return u""


def _id_int(eid):
    try:
        return eid.Value  # Revit 2024+
    except Exception:
        return eid.IntegerValue


def symbol_label(symbol):
    return u"{} : {}".format(_name(symbol.Family), _name(symbol))


def find_hatch_symbols(doc, type_filter):
    u"""Загруженные типы семейств, в имени типа которых есть type_filter (без регистра)."""
    needle = type_filter.strip().lower()
    found = [s for s in FilteredElementCollector(doc).OfClass(FamilySymbol)
             if needle in _name(s).lower()]
    found.sort(key=symbol_label)
    return found


def collect_trays(doc, uidoc):
    u"""(лотки, взяты ли из выделения): выделенные лотки, иначе все в модели."""
    picked = []
    for eid in uidoc.Selection.GetElementIds():
        el = doc.GetElement(eid)
        if isinstance(el, CableTray):
            picked.append(el)
    if picked:
        return picked, True
    trays = [t for t in FilteredElementCollector(doc).OfClass(CableTray)
             if isinstance(t, CableTray)]
    return trays, False


def collect_levels(doc):
    return sorted(FilteredElementCollector(doc).OfClass(Level),
                  key=lambda lv: lv.ProjectElevation)


def _xyz(p):
    return (p.X, p.Y, p.Z)


def _end_connected(tray, point):
    u"""Присоединён ли к чему-нибудь коннектор лотка у этой точки."""
    try:
        for conn in tray.ConnectorManager.Connectors:
            if conn.Origin.DistanceTo(point) < _DEDUPE_TOL:
                return bool(conn.IsConnected)
    except Exception:
        pass
    return False


def _section_dirs(tray, axis):
    u"""(направление ширины, направление высоты) сечения лотка."""
    try:
        normal = tray.CurveNormal
        width = axis.CrossProduct(normal)
        if width.GetLength() > 1e-9:
            return width.Normalize(), normal
    except Exception:
        pass
    for conn in tray.ConnectorManager.Connectors:
        cs = conn.CoordinateSystem
        return cs.BasisX, cs.BasisY
    return None, None


def tray_crossings(tray, plane_zs):
    u"""[(индекс плоскости, XYZ точки, (угол, ширина, длина) в футах)] для одного лотка."""
    loc = tray.Location
    if not isinstance(loc, LocationCurve):
        return []
    curve = loc.Curve
    p0, p1 = curve.GetEndPoint(0), curve.GetEndPoint(1)
    connected = (_end_connected(tray, p0), _end_connected(tray, p1))
    found = core.crossings(_xyz(p0), _xyz(p1), plane_zs, _END_TOL, connected)
    if not found:
        return []
    axis = (p1 - p0).Normalize()
    width_dir, height_dir = _section_dirs(tray, axis)
    if width_dir is None:
        return []
    size = core.footprint(_xyz(axis), _xyz(width_dir), _xyz(height_dir), tray.Width, tray.Height)
    if size is None:
        return []
    return [(index, XYZ(*p), size) for index, p in found]


# --- уже стоящие лючки -------------------------------------------------------

def _instance_level_id(inst):
    try:
        if inst.LevelId != ElementId.InvalidElementId:
            return inst.LevelId
    except Exception:
        pass
    for bip in (BuiltInParameter.FAMILY_LEVEL_PARAM, BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM):
        p = inst.get_Parameter(bip)
        if p is not None and p.AsElementId() != ElementId.InvalidElementId:
            return p.AsElementId()
    return ElementId.InvalidElementId


def existing_hatches(doc, family):
    u"""[(экземпляр, id уровня, XYZ)] — уже расставленные экземпляры семейства."""
    family_id = family.Id
    result = []
    for inst in FilteredElementCollector(doc).OfClass(FamilyInstance):
        try:
            if inst.Symbol.Family.Id != family_id:
                continue
        except Exception:
            continue
        loc = inst.Location
        if isinstance(loc, LocationPoint):
            result.append((inst, _instance_level_id(inst), loc.Point))
    return result


def _find_existing(existing, level_id, point):
    for inst, lvl_id, p in existing:
        if lvl_id == level_id and math.hypot(p.X - point.X, p.Y - point.Y) <= _MATCH_TOL:
            return inst
    return None


# --- размеры -----------------------------------------------------------------

def _writable(param):
    if param is None or param.IsReadOnly or param.StorageType != StorageType.Double:
        return None
    return param


def _type_value(symbol, name):
    p = symbol.LookupParameter(name)
    if p is None or p.StorageType != StorageType.Double:
        return None
    return p.AsDouble()


class SizeWriter(object):
    u"""Пишет размеры лючка в экземпляр или подбирает/создаёт тип с этим размером."""

    def __init__(self, doc, width_param, length_param):
        self.doc = doc
        self.width_param = width_param
        self.length_param = length_param
        self.created_types = []

    def apply(self, inst, width, length):
        need_type = {}
        for name, value in ((self.width_param, width), (self.length_param, length)):
            p = _writable(inst.LookupParameter(name))
            if p is not None:
                p.Set(value)
            else:
                need_type[name] = value
        if not need_type:
            return
        symbol = self._symbol_with(inst.Symbol, need_type, width, length)
        if symbol.Id != inst.Symbol.Id:
            inst.ChangeTypeId(symbol.Id)

    def _symbol_with(self, base, values, width, length):
        for name in values:
            p = base.LookupParameter(name)
            if p is None:
                raise HatchError(
                    u"У семейства «{}» нет параметра «{}» — ни у экземпляра, ни у типа. "
                    u"Проверьте имя в настройках (Shift+клик по кнопке).".format(
                        _name(base.Family), name))
            if p.IsReadOnly or p.StorageType != StorageType.Double:
                raise HatchError(
                    u"Параметр «{}» семейства «{}» не задаётся вручную (формула или "
                    u"не длина) — укажите в настройках другой параметр.".format(
                        name, _name(base.Family)))

        def fits(symbol):
            for name, value in values.items():
                current = _type_value(symbol, name)
                if current is None or abs(current - value) > _SIZE_TOL:
                    return False
            return True

        if fits(base):
            return base
        family = base.Family
        names = set()
        for sid in family.GetFamilySymbolIds():
            symbol = self.doc.GetElement(sid)
            names.add(_name(symbol))
            if fits(symbol):
                return symbol
        label = core.size_label(width * FT_TO_MM, length * FT_TO_MM)
        new_name = u"{} {}".format(_name(base), label)
        n = 2
        while new_name in names:
            new_name = u"{} {} ({})".format(_name(base), label, n)
            n += 1
        symbol = base.Duplicate(new_name)
        for name, value in values.items():
            symbol.LookupParameter(name).Set(value)
        try:
            if not symbol.IsActive:
                symbol.Activate()
        except Exception:
            pass
        self.created_types.append(new_name)
        return symbol


# --- расстановка -------------------------------------------------------------

def _rotation(inst):
    try:
        x = inst.GetTransform().BasisX
        return math.atan2(x.Y, x.X)
    except Exception:
        return 0.0


def _rotate_to(doc, inst, point, angle):
    delta = core.rotation_delta(_rotation(inst), angle)
    if abs(delta) < 1e-6:
        return
    axis = Line.CreateBound(point, point + XYZ(0, 0, 1))
    ElementTransformUtils.RotateElement(doc, inst.Id, axis, delta)


def _set_offset(inst, offset):
    for bip in (BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM,
                BuiltInParameter.INSTANCE_ELEVATION_PARAM):
        p = inst.get_Parameter(bip)
        if p is not None and not p.IsReadOnly:
            p.Set(offset)
            return


def _set_workset(doc, inst, tray):
    if not doc.IsWorkshared:
        return
    try:
        p = inst.get_Parameter(BuiltInParameter.ELEM_PARTITION_PARAM)
        if p is not None and not p.IsReadOnly:
            p.Set(tray.WorksetId.IntegerValue)
    except Exception:
        pass


class Result(object):
    def __init__(self):
        self.placed = 0
        self.updated = 0
        self.trays_crossing = 0
        self.created_types = []


def place_hatches(doc, trays, levels, symbol, width_param, length_param, margin, offset):
    u"""
    Расставляет/обновляет лючки (внутри открытой транзакции). margin и
    offset — в футах. Возвращает Result; HatchError — остановиться.
    """
    if not symbol.IsActive:
        symbol.Activate()
        doc.Regenerate()

    plane_zs = [lv.ProjectElevation + offset for lv in levels]
    points = []
    for tray in trays:
        found = tray_crossings(tray, plane_zs)
        if found:
            points.extend((index, (p.X, p.Y, p.Z), size, tray) for index, p, size in found)
    trays_crossing = len(set(_id_int(item[3].Id) for item in points))
    points = core.dedupe(points, _DEDUPE_TOL)

    existing = existing_hatches(doc, symbol.Family)
    writer = SizeWriter(doc, width_param, length_param)
    result = Result()
    result.trays_crossing = trays_crossing
    for index, p, (angle, width, length), tray in points:
        level = levels[index]
        point = XYZ(*p)
        inst = _find_existing(existing, level.Id, point)
        if inst is None:
            try:
                inst = doc.Create.NewFamilyInstance(point, symbol, level, StructuralType.NonStructural)
            except Exception as err:
                raise HatchError(
                    u"Не удалось поставить «{}»: {}\n\nСемейство лючка должно быть на "
                    u"основе уровня или рабочей плоскости (не на грани и не на "
                    u"основе стены/перекрытия).".format(symbol_label(symbol), err))
            _set_offset(inst, offset)
            _set_workset(doc, inst, tray)
            existing.append((inst, level.Id, point))
            result.placed += 1
        else:
            result.updated += 1
        writer.apply(inst, width + margin, length + margin)
        _rotate_to(doc, inst, inst.Location.Point, angle)
    result.created_types = writer.created_types
    return result
