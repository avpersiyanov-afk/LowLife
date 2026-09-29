# -*- coding: utf-8 -*-
"""
Помещения и пространства в снимке модели (json_snapshot): раздел "rooms" и
привязка элементов к ним ("room" / "space" в записи элемента).

Откуда берутся: помещения (Rooms) и пространства (MEP Spaces) текущего
документа и всех загруженных связей — архитектурные помещения обычно
лежат в связи АР. Координаты связи переводятся в систему координат
проекта (GetTotalTransform), так что контуры помещений и точки элементов
в одном файле сравнимы напрямую.

Раздел "rooms" — только для анализа (площади, контуры, параметры
помещения по списку из настроек), обратно не загружается. Пространства
текущего документа при желании можно выгрузить и как обычные элементы
(категория «Пространства») — тогда их записываемые параметры правятся
через "params", как у любого элемента.

Поиск помещения элемента — как у RoomInfo (lowlife.room_info): точка
элемента внутри помещения (плюс проба на 300 мм выше — для устройств,
стоящих ровно на отметке пола), иначе ближайшее помещение, чей контур не
дальше ROOM_TOLERANCE_MM (оборудование, утопленное в стену).
"""

from collections import OrderedDict

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, FilteredElementCollector,
    RevitLinkInstance, SpatialElementBoundaryOptions, Transform, XYZ,
)

from lowlife.json_snapshot_common import MM_IN_FOOT, safe_name
from lowlife.params import param_to_text
from lowlife.room_info import (
    ROOM_TOLERANCE_MM, _distance_to_room_boundary, get_point as element_point,
)

HOST_SOURCE = u"текущая модель"

_SQFT_TO_M2 = 0.09290304
_CUFT_TO_M3 = 0.028316846592
_LIFT_FT = 300.0 / MM_IN_FOOT
_TOL_FT = ROOM_TOLERANCE_MM / MM_IN_FOOT
_LEVEL_TOL_FT = 10.0 / MM_IN_FOOT


def _mm(ft):
    u"""Футы -> целые мм (int: round в IronPython 2 даёт float — «1234.0»)."""
    return int(round(ft * MM_IN_FOOT))


class _Entry(object):
    u"""Одно помещение/пространство: элемент, вид, источник, bbox (в
    координатах своего документа, с допуском) — для быстрого отсева."""

    def __init__(self, el, kind, source, bb):
        self.el = el
        self.kind = kind
        self.source = source
        self.min = (bb.Min.X - _TOL_FT, bb.Min.Y - _TOL_FT, bb.Min.Z - _TOL_FT)
        self.max = (bb.Max.X + _TOL_FT, bb.Max.Y + _TOL_FT, bb.Max.Z + _LIFT_FT + _TOL_FT)

    def near(self, p):
        return (self.min[0] <= p.X <= self.max[0]
                and self.min[1] <= p.Y <= self.max[1]
                and self.min[2] <= p.Z <= self.max[2])

    def contains(self, p):
        try:
            if self.kind == u"space":
                return self.el.IsPointInSpace(p)
            return self.el.IsPointInRoom(p)
        except Exception:
            return False


class _Source(object):
    def __init__(self, label, transform):
        self.label = label
        self.transform = transform
        self.inverse = transform.Inverse
        self.entries = []


def _placed(el):
    try:
        return el.Location is not None and el.Area > 0
    except Exception:
        return False


class RoomIndex(object):
    u"""Все размещённые помещения и пространства: текущий документ + связи."""

    def __init__(self, doc):
        self.sources = []
        self._add(doc, HOST_SOURCE, Transform.Identity)
        for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
            try:
                ldoc = link.GetLinkDocument()
            except Exception:
                ldoc = None
            if ldoc is None:
                continue
            self._add(ldoc, safe_name(link), link.GetTotalTransform())

    def _add(self, sdoc, label, transform):
        src = _Source(label, transform)
        for bic, kind in ((BuiltInCategory.OST_Rooms, u"room"),
                          (BuiltInCategory.OST_MEPSpaces, u"space")):
            for el in (FilteredElementCollector(sdoc).OfCategory(bic)
                       .WhereElementIsNotElementType()):
                if not _placed(el):
                    continue
                try:
                    bb = el.get_BoundingBox(None)
                except Exception:
                    bb = None
                if bb is not None:
                    src.entries.append(_Entry(el, kind, src, bb))
        if src.entries:
            self.sources.append(src)

    def entries(self):
        for src in self.sources:
            for e in src.entries:
                yield e

    def find(self, host_point, kind):
        u"""Помещение (kind="room") или пространство ("space") точки или None."""
        if host_point is None:
            return None
        lift = XYZ(0, 0, _LIFT_FT)
        local = [(src, src.inverse.OfPoint(host_point)) for src in self.sources]
        for src, p in local:
            for e in src.entries:
                if e.kind != kind or not e.near(p):
                    continue
                if e.contains(p) or e.contains(p + lift):
                    return e
        best, best_d = None, None
        for src, p in local:
            for e in src.entries:
                if e.kind != kind or not e.near(p):
                    continue
                d = _distance_to_room_boundary(e.el, p)
                if d is None or d > _TOL_FT:
                    continue
                if best_d is None or d < best_d:
                    best, best_d = e, d
        return best


def _number(el):
    try:
        return el.Number or u""
    except Exception:
        return u""


def _name(el):
    try:
        p = el.get_Parameter(BuiltInParameter.ROOM_NAME)
        if p is not None and p.HasValue:
            return p.AsString() or u""
    except Exception:
        pass
    return safe_name(el)


def _level_elevation_ft(entry):
    u"""Отметка уровня помещения в координатах проекта (футы) или None."""
    try:
        level = entry.el.Level
        z = getattr(level, "ProjectElevation", None)
        if z is None:
            z = level.Elevation
        return entry.source.transform.OfPoint(XYZ(0, 0, z)).Z
    except Exception:
        return None


def link_info(entry):
    u"""Краткая ссылка на помещение для записи элемента."""
    return OrderedDict([
        ("uid", entry.el.UniqueId),
        ("number", _number(entry.el)),
        ("name", _name(entry.el)),
        ("source", entry.source.label),
    ])


def _boundary(entry):
    u"""Контуры в мм (координаты проекта): [[[x, y], ...], ...] — первый
    обычно внешний, остальные — вырезы (колонны, шахты)."""
    loops = []
    try:
        segs = entry.el.GetBoundarySegments(SpatialElementBoundaryOptions())
    except Exception:
        segs = None
    if not segs:
        return loops
    t = entry.source.transform
    for loop in segs:
        pts = []
        for seg in loop:
            try:
                tess = list(seg.GetCurve().Tessellate())
            except Exception:
                continue
            for q in tess[:-1]:
                h = t.OfPoint(q)
                pts.append([_mm(h.X), _mm(h.Y)])
        if pts:
            loops.append(pts)
    return loops


def room_record(entry, param_names):
    el = entry.el
    rec = OrderedDict()
    rec["uid"] = el.UniqueId
    rec["kind"] = entry.kind
    rec["source"] = entry.source.label
    rec["number"] = _number(el)
    rec["name"] = _name(el)
    try:
        rec["level"] = safe_name(el.Level)
    except Exception:
        pass
    z = _level_elevation_ft(entry)
    if z is not None:
        rec["level_elevation_mm"] = _mm(z)
    try:
        rec["area_m2"] = round(el.Area * _SQFT_TO_M2, 2)
    except Exception:
        pass
    try:
        vol = el.Volume
        if vol > 0:
            rec["volume_m3"] = round(vol * _CUFT_TO_M3, 2)
    except Exception:
        pass
    try:
        rec["height_mm"] = _mm(el.UnboundedHeight)
    except Exception:
        pass
    rec["boundary_mm"] = _boundary(entry)
    params = OrderedDict()
    for name in param_names or []:
        try:
            p = el.LookupParameter(name)
        except Exception:
            p = None
        if p is not None:
            params[name] = param_to_text(p)
    if params:
        rec["params"] = params
    return rec


def rooms_section(index, used_uids, level_elevations_ft, param_names):
    u"""
    Записи раздела "rooms": все помещения, к которым привязан хоть один
    выгружаемый элемент, плюс все помещения на тех же уровнях (по отметке —
    имена уровней в связи АР и в текущей модели могут не совпадать), чтобы
    были видны и пустые помещения. level_elevations_ft пусто — все помещения.
    """
    out = []
    for e in index.entries():
        if e.el.UniqueId not in used_uids and level_elevations_ft:
            z = _level_elevation_ft(e)
            if z is None or not any(abs(z - lz) <= _LEVEL_TOL_FT
                                    for lz in level_elevations_ft):
                continue
        out.append(room_record(e, param_names))
    out.sort(key=lambda r: (r.get("level_elevation_mm", 0), r["kind"], r["number"]))
    return out


def list_room_param_names(doc, per_source=50):
    u"""Имена параметров помещений/пространств (для окна настроек):
    [(имя, вид)] по первым per_source помещениям каждого источника."""
    names = {}
    index = RoomIndex(doc)
    for src in index.sources:
        for e in src.entries[:per_source]:
            try:
                for p in e.el.Parameters:
                    names.setdefault(p.Definition.Name, set()).add(e.kind)
            except Exception:
                pass
    return sorted(((n, u"/".join(sorted(k))) for n, k in names.items()),
                  key=lambda kv: kv[0].lower())
