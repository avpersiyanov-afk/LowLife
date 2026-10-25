# -*- coding: utf-8 -*-
u"""
Кнопка «Боксы на лотки» (Tools.panel/TrayOpeningBoxes) — Revit-часть.
Чистая геометрия (размеры, поворот) — tray_boxes_core.py, настройки —
tray_boxes_settings.py.

Для каждого выбранного кабельного лотка ищутся места, где его ось проходит
сквозь стены и перекрытия (модели и загруженных связей): ось лотка
пересекается с телами элементов (Solid.IntersectWithCurve). В середину
каждого пересечения ставится экземпляр семейства бокса (в имени семейства —
«бокс», в имени типа — «временный», по настройкам), повёрнутый по стене /
по лотку, с размерами сечения лотка плюс запас (по умолчанию 50 мм) и
глубиной по толщине стены/перекрытия.

В «Комментарии» нового бокса пишется имя пользователя Revit, дата и время
создания («ivanov 05.03.2026 09:07»).

Размеры пишутся в параметры экземпляра; если параметр — параметр типа,
создаётся (или берётся уже созданный) типоразмер «<тип> ШxГxВ».

Повторный запуск не плодит дубли: если на пересечении уже стоит бокс
(любое семейство со словами box_family_words — точка вставки рядом или
габарит накрывает середину пересечения), новый не ставится, а стоящий не
меняется — пересечение попадает в отчёт как «бокс уже есть».

Семейство бокса — без основы (на уровне) или на рабочей плоскости; на
основе грани/стены не поддерживается. Вызывать внутри открытой транзакции.
"""

import math
from lowlife.i18n import tr
from datetime import datetime

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, BoundingBoxIntersectsFilter, ElementMulticategoryFilter,
    ElementTransformUtils, Family, FamilyInstance, FamilyPlacementType,
    FilteredElementCollector, FilteredWorksetCollector, GeometryInstance, Level, Line, LocationCurve, LocationPoint,
    Options, Outline, RevitLinkInstance, Solid, SolidCurveIntersectionOptions, StorageType,
    ViewDetailLevel, WorksetKind, XYZ,
)
from Autodesk.Revit.DB.Structure import StructuralType
from System.Collections.Generic import List

from lowlife import tray_boxes_core as core
from lowlife import tray_boxes_settings as cfg
from lowlife.scs import safe_element_name

FT_TO_MM = 304.8

# Уже стоящий бокс считается тем же, если его точка вставки ближе этого.
SAME_BOX_MM = 30.0

# Пересечения оси с телом короче этого — касание, а не проход насквозь.
MIN_CROSSING_MM = 1.0


def mm(value_ft):
    return value_ft * FT_TO_MM


def ft(value_mm):
    return float(value_mm) / FT_TO_MM


def _t(p):
    return (p.X, p.Y, p.Z)


def _xyz(t):
    return XYZ(t[0], t[1], t[2])


def _id_int(eid):
    try:
        return eid.Value  # Revit 2024+
    except Exception:
        return eid.IntegerValue


# ------------------------------------------------------------
# Семейство бокса
# ------------------------------------------------------------

def find_box_types(doc, settings):
    u"""Загруженные типы бокса: семейство — по словам box_family_words,
    тип — по box_type_words. [(подпись, FamilySymbol)] по подписи."""
    family_words = core.split_words(settings.get("box_family_words"))
    type_words = core.split_words(settings.get("box_type_words"))
    result = []
    for family in FilteredElementCollector(doc).OfClass(Family):
        family_name = safe_element_name(family) or u""
        if not core.name_has(family_name, family_words):
            continue
        for sid in family.GetFamilySymbolIds():
            symbol = doc.GetElement(sid)
            type_name = safe_element_name(symbol) or u""
            if symbol is not None and core.name_has(type_name, type_words):
                result.append((u"{} : {}".format(family_name, type_name), symbol))
    result.sort(key=lambda item: item[0].lower())
    return result


def find_box_worksets(doc, settings):
    u"""Пользовательские рабочие наборы, в имени которых есть слово из
    box_workset_words, по имени. Пустой список — модель без рабочих наборов
    или слова не заданы (тогда боксы — в активном рабочем наборе)."""
    words = core.split_words(settings.get("box_workset_words"))
    if not doc.IsWorkshared or not words:
        return []
    worksets = [w for w in FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset)
                if core.name_has(w.Name, words)]
    worksets.sort(key=lambda w: w.Name.lower())
    return worksets


def placement_supported(symbol):
    placement = symbol.Family.FamilyPlacementType
    return placement in (FamilyPlacementType.OneLevelBased,
                         FamilyPlacementType.WorkPlaneBased)


# ------------------------------------------------------------
# Пересечения лотка со стенами и перекрытиями
# ------------------------------------------------------------

class Crossing(object):
    u"""Отрезок оси лотка внутри стены/перекрытия (координаты модели)."""

    def __init__(self, kind, start, end, host, link, wall_dir=None):
        self.kind = kind
        self.start = start
        self.end = end
        self.host = host
        self.link = link
        self.wall_dir = wall_dir

    def center(self):
        return tuple((a + b) / 2.0 for a, b in zip(self.start, self.end))

    def length(self):
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(self.start, self.end)))

    def host_label(self):
        name = safe_element_name(self.host) or u""
        where = safe_element_name(self.link) if self.link is not None else tr(u"модель")
        return u"{} (Id {}, {})".format(name, _id_int(self.host.Id), where)


def _host_categories(settings):
    hosts = settings.get("box_hosts")
    cats = []
    if hosts in (cfg.HOSTS_ALL, cfg.HOSTS_WALLS):
        cats.append(BuiltInCategory.OST_Walls)
    if hosts in (cfg.HOSTS_ALL, cfg.HOSTS_FLOORS):
        cats.append(BuiltInCategory.OST_Floors)
    return cats


def _solids(element, options):
    result = []

    def walk(geometry):
        if geometry is None:
            return
        for obj in geometry:
            if isinstance(obj, Solid):
                if obj.Volume > 1e-9:
                    result.append(obj)
            elif isinstance(obj, GeometryInstance):
                walk(obj.GetInstanceGeometry())

    walk(element.get_Geometry(options))
    return result


def _outline(points):
    xs = [p.X for p in points]
    ys = [p.Y for p in points]
    zs = [p.Z for p in points]
    return Outline(XYZ(min(xs), min(ys), min(zs)), XYZ(max(xs), max(ys), max(zs)))


def _box_points(bbox):
    pts = []
    for x in (bbox.Min.X, bbox.Max.X):
        for y in (bbox.Min.Y, bbox.Max.Y):
            for z in (bbox.Min.Z, bbox.Max.Z):
                pts.append(bbox.Transform.OfPoint(XYZ(x, y, z)))
    return pts


def _wall_direction(wall, point):
    loc = wall.Location
    if not isinstance(loc, LocationCurve):
        return None
    curve = loc.Curve
    if isinstance(curve, Line):
        return curve.Direction
    try:
        projected = curve.Project(point)
        return curve.ComputeDerivatives(projected.Parameter, False).BasisX.Normalize()
    except Exception:
        return None


class _Source(object):
    u"""Документ, где искать стены/перекрытия: сама модель или связь."""

    def __init__(self, doc, link=None):
        self.doc = doc
        self.link = link
        self.transform = link.GetTotalTransform() if link is not None else None
        self.inverse = self.transform.Inverse if link is not None else None
        self._solids = {}

    def to_local(self, p):
        return self.inverse.OfPoint(p) if self.inverse is not None else p

    def to_model(self, p):
        return self.transform.OfPoint(p) if self.transform is not None else p

    def to_model_vector(self, v):
        return self.transform.OfVector(v) if self.transform is not None else v

    def solids(self, element, options):
        key = _id_int(element.Id)
        if key not in self._solids:
            self._solids[key] = _solids(element, options)
        return self._solids[key]


def sources(doc, settings):
    u"""Где искать стены/перекрытия — по настройке «Модель»: эта модель,
    она же со всеми связями или все экземпляры одной связи (по имени файла)."""
    chosen = settings.get("box_source_model") or cfg.SOURCE_ALL
    result = [_Source(doc)] if chosen in (cfg.SOURCE_HOST, cfg.SOURCE_ALL) else []
    if chosen == cfg.SOURCE_HOST:
        return result
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        link_doc = link.GetLinkDocument()
        if link_doc is None:
            continue
        if chosen == cfg.SOURCE_ALL or link_doc.Title == chosen:
            result.append(_Source(link_doc, link))
    return result


def tray_crossings(tray, srcs, categories, options):
    u"""Пересечения оси лотка со стенами/перекрытиями всех источников."""
    loc = tray.Location
    if not isinstance(loc, LocationCurve) or not isinstance(loc.Curve, Line):
        return []
    axis = loc.Curve
    start = axis.GetEndPoint(0)
    direction = axis.Direction
    bbox = tray.get_BoundingBox(None)
    if bbox is None:
        return []
    corners = _box_points(bbox)
    cat_filter = ElementMulticategoryFilter(List[BuiltInCategory](categories))
    min_len = ft(MIN_CROSSING_MM)

    result = []
    for src in srcs:
        local_axis = axis.CreateTransformed(src.inverse) if src.inverse is not None else axis
        outline = _outline([src.to_local(p) for p in corners])
        hosts = (FilteredElementCollector(src.doc)
                 .WherePasses(cat_filter)
                 .WherePasses(BoundingBoxIntersectsFilter(outline))
                 .WhereElementIsNotElementType())
        for host in hosts:
            spans = []
            for solid in src.solids(host, options):
                try:
                    hit = solid.IntersectWithCurve(local_axis, SolidCurveIntersectionOptions())
                except Exception:
                    continue
                for i in range(hit.SegmentCount):
                    seg = hit.GetCurveSegment(i)
                    a = src.to_model(seg.GetEndPoint(0))
                    b = src.to_model(seg.GetEndPoint(1))
                    spans.append((a.Subtract(start).DotProduct(direction),
                                  b.Subtract(start).DotProduct(direction)))
            is_wall = _id_int(host.Category.Id) == int(BuiltInCategory.OST_Walls)
            for a, b in core.merge_intervals(spans, ft(1.0)):
                if b - a < min_len:
                    continue
                pa = start.Add(direction.Multiply(a))
                pb = start.Add(direction.Multiply(b))
                wall_dir = None
                if is_wall:
                    mid_local = src.to_local(pa.Add(pb).Divide(2.0))
                    local_dir = _wall_direction(host, mid_local)
                    if local_dir is None:
                        continue
                    wall_dir = _t(src.to_model_vector(local_dir))
                result.append(Crossing(core.WALL if is_wall else core.FLOOR,
                                       _t(pa), _t(pb), host, src.link, wall_dir))
    return result


def tray_width_direction(tray):
    u"""Направление ширины сечения лотка (BasisX системы координат
    соединителя), иначе — горизонталь поперёк оси."""
    try:
        for connector in tray.ConnectorManager.Connectors:
            return _t(connector.CoordinateSystem.BasisX)
    except Exception:
        pass
    d = tray.Location.Curve.Direction
    return (-d.Y, d.X, 0.0)


def box_for(tray, crossing, settings):
    u"""(Box, None) или (None, причина) — в футах."""
    d = _t(tray.Location.Curve.Direction)
    extra = ft(settings.get("size_extra_mm") or 0.0)
    depth_extra = ft(settings.get("depth_extra_mm") or 0.0)
    slope = settings.get("max_slope_deg") or 0.0
    if crossing.kind == core.WALL:
        return core.wall_box(crossing.center(), d, crossing.wall_dir, crossing.length(),
                             tray.Width, tray.Height, extra, depth_extra, slope,
                             settings.get("max_wall_angle_deg") or 0.0)
    return core.floor_box(crossing.center(), d, tray_width_direction(tray), crossing.length(),
                          tray.Width, tray.Height, extra, depth_extra, slope)


# ------------------------------------------------------------
# Расстановка
# ------------------------------------------------------------

class Result(object):
    def __init__(self):
        self.created = []   # (лоток, Crossing, бокс)
        self.existing = []  # (лоток, Crossing, уже стоящий бокс) — не тронуты
        self.skipped = []   # (лоток, Crossing, причина)
        self.failed = []    # (лоток, Crossing или None, текст ошибки)
        self.missing_params = set()
        self.new_types = []


def _levels(doc):
    levels = list(FilteredElementCollector(doc).OfClass(Level))
    levels.sort(key=lambda lv: lv.ProjectElevation)
    return levels


def _level_below(levels, z):
    below = [lv for lv in levels if lv.ProjectElevation <= z + 1e-6]
    if below:
        return below[-1]
    return levels[0] if levels else None


class BoxPlacer(object):
    def __init__(self, doc, symbol, settings, workset=None):
        self.doc = doc
        self.workset = workset
        self.comment = core.creation_comment(doc.Application.Username, datetime.now())
        self.symbol = symbol
        self.family = symbol.Family
        self.settings = settings
        self.levels = _levels(doc)
        self.at_bottom = settings.get("box_origin") == cfg.ORIGIN_BOTTOM
        self.params = [
            ("width", settings.get("box_width_param")),
            ("depth", settings.get("box_depth_param")),
            ("height", settings.get("box_height_param")),
        ]
        family_words = core.split_words(settings.get("box_family_words"))
        self.existing = []
        for inst in FilteredElementCollector(doc).OfClass(FamilyInstance):
            try:
                if (isinstance(inst.Location, LocationPoint) and
                        core.name_has(safe_element_name(inst.Symbol.Family), family_words)):
                    self.existing.append(inst)
            except Exception:
                pass
        self.result = Result()
        if not symbol.IsActive:
            symbol.Activate()
            doc.Regenerate()

    # --- поиск уже стоящего --------------------------------------------

    def _existing_at(self, origin, center):
        u"""Уже стоящий бокс: точка вставки ближе SAME_BOX_MM к нужной или
        габарит бокса накрывает середину пересечения."""
        tol = ft(SAME_BOX_MM)
        for inst in self.existing:
            if inst.Location.Point.DistanceTo(origin) <= tol:
                return inst
            bbox = inst.get_BoundingBox(None)
            if bbox is not None and all(
                    lo - tol <= v <= hi + tol for lo, v, hi in (
                        (bbox.Min.X, center.X, bbox.Max.X),
                        (bbox.Min.Y, center.Y, bbox.Max.Y),
                        (bbox.Min.Z, center.Z, bbox.Max.Z))):
                return inst
        return None

    # --- вставка --------------------------------------------------------

    def _create(self, origin, box):
        doc = self.doc
        level = _level_below(self.levels, origin.Z)
        x_dir = XYZ(box.x_dir[0], box.x_dir[1], 0.0)
        if self.family.FamilyPlacementType == FamilyPlacementType.WorkPlaneBased and level is not None:
            on_plane = XYZ(origin.X, origin.Y, level.ProjectElevation)
            inst = doc.Create.NewFamilyInstance(level.GetPlaneReference(), on_plane, x_dir, self.symbol)
        elif level is not None:
            inst = doc.Create.NewFamilyInstance(origin, self.symbol, level, StructuralType.NonStructural)
        else:
            inst = doc.Create.NewFamilyInstance(origin, self.symbol, StructuralType.NonStructural)
        doc.Regenerate()
        loc = inst.Location
        delta = box.angle() - loc.Rotation
        if abs(math.sin(delta)) > 1e-9 or math.cos(delta) < 0:
            axis = Line.CreateBound(loc.Point, loc.Point.Add(XYZ.BasisZ))
            ElementTransformUtils.RotateElement(doc, inst.Id, axis, delta)
            doc.Regenerate()
        shift = origin.Subtract(inst.Location.Point)
        if shift.GetLength() > 1e-9:
            ElementTransformUtils.MoveElement(doc, inst.Id, shift)
        if self.workset is not None:
            param = inst.get_Parameter(BuiltInParameter.ELEM_PARTITION_PARAM)
            if param is not None and not param.IsReadOnly:
                param.Set(self.workset.Id.IntegerValue)
        param = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if param is not None and not param.IsReadOnly:
            param.Set(self.comment)
        self.existing.append(inst)
        return inst

    # --- размеры --------------------------------------------------------

    def _sized_type(self, type_names, values):
        u"""Типоразмер с нужными значениями параметров типа (создаётся копией
        выбранного типа)."""
        base = safe_element_name(self.symbol) or u""
        name = core.sized_type_name(base, mm(values["width"]), mm(values["depth"]),
                                    mm(values["height"]))
        for sid in self.family.GetFamilySymbolIds():
            sym = self.doc.GetElement(sid)
            if (safe_element_name(sym) or u"") == name:
                return sym
        sym = self.symbol.Duplicate(name)
        for role, pname in type_names:
            p = sym.LookupParameter(pname)
            if p is not None and not p.IsReadOnly:
                p.Set(values[role])
        self.result.new_types.append(name)
        return sym

    def _apply_sizes(self, inst, box):
        values = {"width": box.width, "depth": box.depth, "height": box.height}
        type_names = []
        for role, pname in self.params:
            if not pname:
                continue
            p = inst.LookupParameter(pname)
            if p is not None and p.StorageType == StorageType.Double and not p.IsReadOnly:
                p.Set(values[role])
                continue
            tp = self.symbol.LookupParameter(pname)
            if tp is not None and tp.StorageType == StorageType.Double:
                type_names.append((role, pname))
            else:
                self.result.missing_params.add(pname)
        if type_names:
            sym = self._sized_type(type_names, values)
            if inst.Symbol.Id != sym.Id:
                if not sym.IsActive:
                    sym.Activate()
                inst.ChangeTypeId(sym.Id)

    # --- один лоток -----------------------------------------------------

    def place(self, tray, crossing):
        box, reason = box_for(tray, crossing, self.settings)
        if box is None:
            self.result.skipped.append((tray, crossing, reason))
            return
        origin = _xyz(box.origin(self.at_bottom))
        existing = self._existing_at(origin, _xyz(box.center))
        if existing is not None:
            self.result.existing.append((tray, crossing, existing))
            return
        try:
            inst = self._create(origin, box)
            self._apply_sizes(inst, box)
        except Exception as ex:
            self.result.failed.append((tray, crossing, u"{}".format(ex)))
            return
        self.result.created.append((tray, crossing, inst))


def run(doc, trays, symbol, settings, progress=None, workset=None):
    u"""Боксы на всех пересечениях лотков trays (новые — в рабочем наборе
    workset, None — в активном). Возвращает Result."""
    placer = BoxPlacer(doc, symbol, settings, workset)
    categories = _host_categories(settings)
    options = Options()
    options.ComputeReferences = False
    options.DetailLevel = ViewDetailLevel.Fine
    srcs = sources(doc, settings)
    for index, tray in enumerate(trays):
        if progress is not None:
            progress(index, len(trays))
        try:
            crossings = tray_crossings(tray, srcs, categories, options)
        except Exception as ex:
            placer.result.failed.append((tray, None, tr(u"поиск пересечений: {}").format(ex)))
            continue
        for crossing in crossings:
            placer.place(tray, crossing)
    return placer.result

