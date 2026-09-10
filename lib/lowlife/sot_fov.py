# -*- coding: utf-8 -*-
"""
СОТ: построение зоны обзора видеокамеры на активном виде (плоская 2D-зона
из области заливки), с обрезкой по границе помещения из связанной модели.

Отдельная дисциплина СОТ — но это не структурная схема, поэтому логика и
настройки живут не в sot_settings.py/sot_schematic.py, а здесь, со своим
файлом настроек %APPDATA%\\pyRevit\\LowLifeCameraFov_settings.json (тот же
приём «своя дисциплина — свой файл», что у scs_settings/skud_settings/
room_info_settings).

Что строит кнопка «Зоны обзора» (SOT.panel):
  1. по каждой выбранной камере берёт горизонтальный угол обзора и
     дальность из параметров экземпляра (имена — в настройках);
  2. направление «взгляда» — FamilyInstance.FacingOrientation (уже
     учитывает поворот и отражения экземпляра; параметр поворота НЕ
     складывается отдельно — иначе двойной учёт), плюс необязательный
     фиксированный доворот из настроек;
  3. если заданы параметры высоты установки, наклона оптической оси вниз
     и вертикального угла обзора — зона считается как проекция конуса на
     плоскость расчёта: ближняя мёртвая зона + дальняя граница
       near = h / tan(tilt + vfov/2),  far = h / tan(tilt - vfov/2)
     (far бесконечен при tilt <= vfov/2 -> обрезается дальностью);
  4. если задан RevitLinkInstance с помещениями — зона обрезается по
     контуру помещения, в котором стоит камера: каждый луч сектора
     укорачивается до первого пересечения с границей Room (работает и с
     вогнутыми помещениями, и с «дырами» — колоннами/шахтами);
  5. рисуется одна FilledRegion на камеру; в «Комментарии» пишется метка
     «<tag>|<id камеры>» — при повторном запуске прежние зоны выбранных
     камер на этом виде удаляются и создаются заново (идемпотентность);
  6. необязательно — концентрические дуги зон DORI (EN 62676-4:
     идентификация/распознавание/наблюдение/обнаружение) по горизонтальному
     разрешению матрицы.

Транзакцию открывает скрипт кнопки, не этот модуль.
"""

import re
import math

from Autodesk.Revit.DB import (
    XYZ, Line, Arc, CurveLoop, Element, ElementId,
    FilteredElementCollector, RevitLinkInstance, BuiltInCategory,
    BuiltInParameter, StorageType, LocationPoint,
    FilledRegion, FilledRegionType, CurveElement,
    SpatialElementBoundaryOptions, SpatialElementBoundaryLocation,
    Color, GraphicsStyleType,
)

# Определение «это угловой параметр?» — модульный SpecTypeId (Revit 2021+),
# с откатом на устаревший enum ParameterType, если он ещё доступен. Оба —
# опциональны: при неудаче число трактуется по полю «Единицы углов».
try:
    from Autodesk.Revit.DB import SpecTypeId as _SpecTypeId
except Exception:
    _SpecTypeId = None

try:
    from Autodesk.Revit.DB import ParameterType as _ParameterType
except Exception:
    _ParameterType = None

from System.Collections.Generic import List

from lowlife.geometry import get_element_level

_FT_PER_MM = 1.0 / 304.8
_M_PER_FT = 0.3048


# ======================================================================
#  РАЗБОР ЗНАЧЕНИЙ НАСТРОЕК
# ======================================================================

def _as_bool(value, default=False):
    if value is None:
        return default
    s = unicode(value).strip().lower()
    if not s:
        return default
    return s in (u"да", u"1", u"true", u"yes", u"y", u"вкл", u"on", u"истина", u"+")


def _as_float(value, default=0.0):
    try:
        return float(unicode(value).strip().replace(u",", u"."))
    except Exception:
        return default


def _as_int(value, default=0):
    try:
        return int(round(_as_float(value, default)))
    except Exception:
        return default


def _param_radians(param, unit_mode):
    """
    Значение углового параметра в радианах. unit_mode: «авто» — по типу
    параметра (ParameterType.Angle -> уже радианы, иначе трактуем число
    как градусы); «градусы» / «радианы» — принудительно.
    """
    v = param.AsDouble()
    mode = (unit_mode or u"авто").strip().lower()

    if mode.startswith(u"град"):
        return math.radians(v)
    if mode.startswith(u"рад"):
        return v

    # авто: значение уже в радианах, если параметр углового типа
    try:
        if _SpecTypeId is not None and param.Definition.GetDataType() == _SpecTypeId.Angle:
            return v
    except Exception:
        pass
    try:
        if _ParameterType is not None and param.Definition.ParameterType == _ParameterType.Angle:
            return v
    except Exception:
        pass
    return math.radians(v)


def _opt_param_radians(el, name, unit_mode):
    """Угловой параметр по имени в радианах или None, если имя пустое / нет значения."""
    if not name or not name.strip():
        return None
    p = el.LookupParameter(name.strip())
    if p is None or not p.HasValue or p.StorageType != StorageType.Double:
        return None
    return _param_radians(p, unit_mode)


# --- угол обзора из оптики (фокусное расстояние + матрица) --------------

# Оптический формат матрицы -> (ширина, высота) активной области, мм.
# Значения номинальные (историческое «дюймовое» обозначение), при
# необходимости задайте размеры явно как «ШхВ» (например «5.37x4.04»).
_SENSOR_FORMATS = {
    u"1/4":   (3.60, 2.70),
    u"1/3.6": (4.00, 3.00),
    u"1/3.2": (4.54, 3.42),
    u"1/3":   (4.80, 3.60),
    u"1/2.9": (4.96, 3.72),
    u"1/2.8": (5.37, 4.04),
    u"1/2.7": (5.37, 4.04),
    u"1/2.5": (5.76, 4.29),
    u"1/2.3": (6.17, 4.55),
    u"1/2":   (6.40, 4.80),
    u"1/1.9": (6.74, 5.05),
    u"1/1.8": (7.18, 5.32),
    u"1/1.7": (7.60, 5.70),
    u"2/3":   (8.80, 6.60),
    u"1/1.2": (10.67, 8.00),
    u"1":     (12.80, 9.60),
}


def _parse_sensor(text):
    """
    «Формат матрицы» -> (ширина_мм, высота_мм). Принимает:
      «1/2.8», «1/3"», «2/3»  — по таблице оптических форматов;
      «5.37x4.04», «5,37*4,04» — явные размеры;
      «5.37» — только ширина (высота считается как 3/4 ширины).
    None, если распознать не удалось.
    """
    if not text:
        return None
    s = unicode(text).strip().strip(u'"').strip(u'”')
    s = s.replace(u",", u".").replace(u" ", u"").lower()
    if not s:
        return None
    if s in _SENSOR_FORMATS:
        return _SENSOR_FORMATS[s]
    for sep in (u"x", u"×", u"*"):
        if sep in s:
            a, _, b = s.partition(sep)
            try:
                return (float(a), float(b))
            except Exception:
                return None
    try:
        w = float(s)
        return (w, w * 3.0 / 4.0)
    except Exception:
        return None


def _length_param_mm(param):
    """Значение параметра длины в миллиметрах. Тип «Длина» -> из футов в мм;
    иначе значение берётся как есть (считаем, что уже в мм)."""
    v = param.AsDouble()
    try:
        if _SpecTypeId is not None and param.Definition.GetDataType() == _SpecTypeId.Length:
            return v * 304.8
    except Exception:
        pass
    try:
        if _ParameterType is not None and param.Definition.ParameterType == _ParameterType.Length:
            return v * 304.8
    except Exception:
        pass
    return v


def _optical_fov(fi, settings):
    """
    (hfov_rad, vfov_rad|None) из параметра фокусного расстояния и формата
    матрицы. None, если имя параметра не задано / параметра нет / формат
    матрицы не задан — тогда используется прямой параметр угла обзора.
    """
    fname = (settings.get("focal_length_param_name") or u"").strip()
    if not fname:
        return None
    p = fi.LookupParameter(fname)
    if p is None or not p.HasValue or p.StorageType != StorageType.Double:
        return None
    f_mm = _length_param_mm(p)
    if not f_mm or f_mm <= 0.01:
        return None

    sensor = _parse_sensor(settings.get("sensor_format"))
    if sensor is None:
        return None
    w_mm, h_mm = sensor

    hfov = 2.0 * math.atan(w_mm / (2.0 * f_mm))
    vfov = 2.0 * math.atan(h_mm / (2.0 * f_mm)) if (h_mm and h_mm > 0) else None
    return hfov, vfov


# ======================================================================
#  ГЕОМЕТРИЯ КАМЕРЫ
# ======================================================================

def _horiz(v):
    """Горизонтальная проекция вектора как XYZ, либо None, если она почти нулевая."""
    if v is None:
        return None
    try:
        h = XYZ(v.X, v.Y, 0.0)
    except Exception:
        return None
    return h if h.GetLength() > 1e-6 else None


def _look_direction(fi, offset_deg):
    """
    (горизонтальный единичный вектор «куда смотрит» камера, пояснение).
    Источники по очереди: FacingOrientation, BasisY / BasisX её Transform,
    HandOrientation. offset_deg — фиксированный доворот против часовой
    стрелки. Первый элемент None, если направление определить не удалось
    (тогда во втором — что перебрали, для диагностики).
    """
    tried = []

    src = None
    try:
        f = fi.FacingOrientation
        tried.append(u"Facing=({:.2f},{:.2f},{:.2f})".format(f.X, f.Y, f.Z))
        src = _horiz(f)
        if src is not None:
            note = u"FacingOrientation"
    except Exception as ex:
        tried.append(u"Facing!{}".format(ex))

    if src is None:
        try:
            t = fi.GetTransform()
            tried.append(u"BasisY=({:.2f},{:.2f},{:.2f})".format(
                t.BasisY.X, t.BasisY.Y, t.BasisY.Z))
            src = _horiz(t.BasisY)
            if src is not None:
                note = u"Transform.BasisY"
            if src is None:
                tried.append(u"BasisX=({:.2f},{:.2f},{:.2f})".format(
                    t.BasisX.X, t.BasisX.Y, t.BasisX.Z))
                src = _horiz(t.BasisX)
                if src is not None:
                    note = u"Transform.BasisX"
        except Exception as ex:
            tried.append(u"Transform!{}".format(ex))

    if src is None:
        try:
            hnd = fi.HandOrientation
            tried.append(u"Hand=({:.2f},{:.2f},{:.2f})".format(hnd.X, hnd.Y, hnd.Z))
            # «взгляд» перпендикулярен руке в плане: повернём на -90°
            hh = _horiz(hnd)
            if hh is not None:
                hh = hh.Normalize()
                src = XYZ(hh.Y, -hh.X, 0.0)
                note = u"HandOrientation⟂"
        except Exception as ex:
            tried.append(u"Hand!{}".format(ex))

    if src is None:
        return None, u" / ".join(tried)

    d = src.Normalize()
    if offset_deg:
        a = math.radians(offset_deg)
        ca, sa = math.cos(a), math.sin(a)
        d = XYZ(d.X * ca - d.Y * sa, d.X * sa + d.Y * ca, 0.0)

    return d, note


def _mounting_height_ft(doc, fi, view, height_param_name):
    """
    Высота установки камеры над её уровнем, футы. Сначала — из параметра
    height_param_name (если задан и положителен); иначе — отметка точки
    вставки минус отметка связанного уровня (или GenLevel вида). None,
    если высоту не определить или она неположительна.
    """
    name = (height_param_name or u"").strip()
    if name:
        p = fi.LookupParameter(name)
        if p is not None and p.HasValue and p.StorageType == StorageType.Double:
            h = p.AsDouble()
            if h > 0:
                return h

    try:
        pt = fi.Location.Point
    except Exception:
        return None

    base_z = None
    lvl = get_element_level(doc, fi)
    if lvl is not None:
        try:
            base_z = lvl.Elevation
        except Exception:
            base_z = None
    if base_z is None:
        gen = getattr(view, "GenLevel", None)
        if gen is not None:
            try:
                base_z = gen.Elevation
            except Exception:
                base_z = None
    if base_z is None:
        return None

    h = pt.Z - base_z
    return h if h > 0 else None


def _near_far_radius(h_ft, tilt_rad, vfov_rad, max_r):
    """
    (near_r, far_r) — радиусы ближней и дальней границы зоны на плоскости
    расчёта, футы. Если высоты/наклона/верт.угла нет — плоский сектор
    (0, max_r), как в исходном скрипте.
    """
    if (h_ft is None or h_ft <= 0.1
            or tilt_rad is None or vfov_rad is None or vfov_rad <= 1e-4):
        return 0.0, max_r

    half_v = vfov_rad / 2.0
    bottom = tilt_rad + half_v      # нижний луч кадра -> ближняя кромка
    top = tilt_rad - half_v         # верхний луч кадра -> дальняя кромка

    near = 0.0
    if bottom > 1e-3:
        near = h_ft / math.tan(bottom)

    far = max_r
    if top > 1e-3:
        far = min(max_r, h_ft / math.tan(top))

    near = max(0.0, min(near, max_r))
    if far <= near:
        far = max_r
    return near, far


# ======================================================================
#  ПОМЕЩЕНИЕ ИЗ СВЯЗИ  ->  КОНТУР В КООРДИНАТАХ ХОСТА
# ======================================================================

_ROOM_TOLERANCE_FT = 90.0 * _FT_PER_MM   # как в room_info.py: точка часто «в стене»
_ROOM_Z_PAD_FT = 1.0                     # запас по высоте при выборе этажа


def _boundary_options(mode):
    opt = SpatialElementBoundaryOptions()
    if mode and unicode(mode).strip().lower().startswith(u"центр"):
        opt.SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Center
    else:
        opt.SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Finish
    return opt


def _room_boundary_rings(room, opt, tf):
    """[[XYZ,...], ...] — контуры Room в координатах ХОСТА, Z=0. Первый —
    внешний, остальные — «дыры». None, если контур не получить."""
    try:
        loops = room.GetBoundarySegments(opt)
    except Exception:
        loops = None
    if not loops:
        return None

    rings = []
    for loop in loops:
        pts = []
        for seg in loop:
            crv = None
            try:
                crv = seg.GetCurve()
            except Exception:
                try:
                    crv = seg.Curve            # старое имя (Revit < 2016)
                except Exception:
                    crv = None
            if crv is None:
                continue
            try:
                tess = crv.CreateTransformed(tf).Tessellate()
            except Exception:
                continue
            for i in range(tess.Count - 1):
                q = tess[i]
                pts.append(XYZ(q.X, q.Y, 0.0))
        if len(pts) >= 3:
            rings.append(pts)
    return rings or None


def _point_in_ring(px, py, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i].X, ring[i].Y
        xj, yj = ring[j].X, ring[j].Y
        if ((yi > py) != (yj > py)) and \
           (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _dist_point_to_rings(px, py, rings):
    best = None
    for ring in rings:
        n = len(ring)
        for i in range(n):
            a = ring[i]
            b = ring[(i + 1) % n]
            ex, ey = b.X - a.X, b.Y - a.Y
            seg2 = ex * ex + ey * ey
            if seg2 < 1e-12:
                continue
            t = ((px - a.X) * ex + (py - a.Y) * ey) / seg2
            t = max(0.0, min(1.0, t))
            dx = px - (a.X + t * ex)
            dy = py - (a.Y + t * ey)
            d = math.sqrt(dx * dx + dy * dy)
            if best is None or d < best:
                best = d
    return best


def room_rings_for_point(doc, host_point, boundary_mode):
    """
    (контуры помещения в координатах ХОСТА [Z=0], пояснение).

    host_point — точка камеры С РЕАЛЬНОЙ ОТМЕТКОЙ (не сплющенная в Z=0).
    Помещение ищется во всех загруженных RevitLinkInstance двумерным
    тестом «точка внутри контура по XY» (это надёжнее Room.IsPointInRoom,
    который чувствителен к Z и отсекает камеру под потолком). Если по XY
    подошло несколько помещений (этажи друг над другом) — выбирается то,
    чей вертикальный габарит содержит Z камеры, иначе ближайшее по высоте.
    Если точка вне всех контуров — ближайшее в пределах 90 мм («камера
    сидит в стене»). Первый элемент None + пояснение, если не нашлось.
    """
    opt = _boundary_options(boundary_mode)
    opt_center = SpatialElementBoundaryOptions()
    opt_center.SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Center

    links = list(FilteredElementCollector(doc).OfClass(RevitLinkInstance))
    if not links:
        return None, u"в проекте нет связей (RevitLinkInstance)"

    loaded = 0
    total_rooms = 0
    xy_hits = []   # (area, rings, zmin, zmax, pz)
    near = []      # (dist_ft, rings)

    for li in links:
        ldoc = li.GetLinkDocument()
        if ldoc is None:
            continue
        loaded += 1
        try:
            tf = li.GetTotalTransform()
            p_link = tf.Inverse.OfPoint(host_point)
        except Exception:
            continue

        rooms = (FilteredElementCollector(ldoc)
                 .OfCategory(BuiltInCategory.OST_Rooms)
                 .WhereElementIsNotElementType()
                 .ToElements())

        for room in rooms:
            try:
                if room.Area <= 0:
                    continue
            except Exception:
                continue
            total_rooms += 1

            rings = _room_boundary_rings(room, opt, tf)
            if not rings:
                rings = _room_boundary_rings(room, opt_center, tf)
            if not rings:
                continue

            inside = (_point_in_ring(host_point.X, host_point.Y, rings[0])
                      and not any(_point_in_ring(host_point.X, host_point.Y, h)
                                  for h in rings[1:]))

            if inside:
                zmin = zmax = None
                try:
                    bb = room.get_BoundingBox(None)
                    if bb is not None:
                        zmin, zmax = bb.Min.Z, bb.Max.Z
                except Exception:
                    pass
                try:
                    area = room.Area
                except Exception:
                    area = 0.0
                xy_hits.append((area, rings, zmin, zmax, p_link.Z))
            else:
                d = _dist_point_to_rings(host_point.X, host_point.Y, rings)
                if d is not None and d <= _ROOM_TOLERANCE_FT:
                    near.append((d, rings))

    if loaded == 0:
        return None, u"связи есть, но не загружены (GetLinkDocument = None)"
    if total_rooms == 0:
        return None, u"в связях ({} шт.) нет размещённых помещений".format(loaded)

    if xy_hits:
        if len(xy_hits) == 1:
            return xy_hits[0][1], u"помещение (1 по XY)"

        def _contains_z(h):
            _, _, zmin, zmax, pz = h
            return zmin is not None and (zmin - _ROOM_Z_PAD_FT <= pz <= zmax + _ROOM_Z_PAD_FT)

        in_z = [h for h in xy_hits if _contains_z(h)]
        if in_z:
            in_z.sort(key=lambda h: h[0])   # меньшая площадь = более точное
            return in_z[0][1], u"помещение (из {} по XY — по высоте)".format(len(xy_hits))

        def _zdist(h):
            _, _, zmin, zmax, pz = h
            if zmin is None:
                return 1e9
            return abs(0.5 * (zmin + zmax) - pz)

        xy_hits.sort(key=_zdist)
        return xy_hits[0][1], u"помещение (из {} по XY — ближайшее по высоте)".format(len(xy_hits))

    if near:
        near.sort(key=lambda c: c[0])
        return near[0][1], u"вне контура, взято ближайшее ({:.0f} мм)".format(near[0][0] * 304.8)

    return None, u"проверено помещений: {}, точка вне всех контуров по XY".format(total_rooms)


# ======================================================================
#  ПОСТРОЕНИЕ КОНТУРА ЗОНЫ
# ======================================================================

def _clip_distance(ox, oy, ux, uy, max_d, rings):
    """Расстояние вдоль луча (ox,oy)+t*(ux,uy) до первого пересечения с
    любым отрезком контуров rings, но не больше max_d."""
    best = max_d
    for ring in rings:
        n = len(ring)
        for i in range(n):
            a = ring[i]
            b = ring[(i + 1) % n]
            ex, ey = b.X - a.X, b.Y - a.Y
            den = ux * ey - uy * ex
            if abs(den) < 1e-12:
                continue
            ax, ay = a.X - ox, a.Y - oy
            t = (ax * ey - ay * ex) / den
            u = (ax * uy - ay * ux) / den
            if 1e-6 < t < best and -1e-9 <= u <= 1.0 + 1e-9:
                best = t
    return best


def _zone_curveloop(center, base, half, near_r, far_r, rings, ray_count, z):
    """
    CurveLoop контура зоны обзора (звёздный многоугольник от центра либо
    кольцевой сектор при near_r > 0). Каждый радиальный луч обрезается по
    rings. None, если контур вырожден.
    """
    steps = max(8, int(ray_count))
    offs = [(-half + 2.0 * half * (float(i) / steps)) for i in range(steps + 1)]

    # добавочные лучи точно в вершины помещения — чёткие изломы на границе
    for ring in (rings or []):
        for p in ring:
            a = math.atan2(p.Y - center.Y, p.X - center.X)
            da = math.atan2(math.sin(a - base), math.cos(a - base))
            if -half - 1e-4 <= da <= half + 1e-4:
                offs.append(max(-half, da - 5e-5))
                offs.append(min(half, da + 5e-5))

    offs = sorted(set(round(o, 9) for o in offs))

    far_ray = []
    for o in offs:
        a = base + o
        ux, uy = math.cos(a), math.sin(a)
        r = far_r
        if rings:
            r = _clip_distance(center.X, center.Y, ux, uy, far_r, rings)
        far_ray.append((a, r))

    pts = []
    if near_r <= 0.05:
        pts.append(XYZ(center.X, center.Y, z))
        for a, r in far_ray:
            pts.append(XYZ(center.X + math.cos(a) * r, center.Y + math.sin(a) * r, z))
    else:
        for a, r in far_ray:
            rr = max(r, near_r + 0.02)
            pts.append(XYZ(center.X + math.cos(a) * rr, center.Y + math.sin(a) * rr, z))
        for a, r in reversed(far_ray):
            pts.append(XYZ(center.X + math.cos(a) * near_r, center.Y + math.sin(a) * near_r, z))

    clean = []
    for p in pts:
        if not clean or clean[-1].DistanceTo(p) > 1e-4:
            clean.append(p)
    if len(clean) >= 2 and clean[0].DistanceTo(clean[-1]) <= 1e-4:
        clean.pop()
    if len(clean) < 3:
        return None

    cl = CurveLoop()
    made = 0
    n = len(clean)
    for i in range(n):
        a = clean[i]
        b = clean[(i + 1) % n]
        if a.DistanceTo(b) < 1e-4:
            continue
        try:
            cl.Append(Line.CreateBound(a, b))
            made += 1
        except Exception:
            return None
    return cl if made >= 3 else None


# ======================================================================
#  ТИПЫ / СТИЛИ / ОЧИСТКА
# ======================================================================

def _pick_filled_region_type(doc, name):
    types = list(FilteredElementCollector(doc).OfClass(FilledRegionType))
    if not types:
        return None
    if name and name.strip():
        want = name.strip()
        for t in types:
            try:
                if Element.Name.GetValue(t) == want:
                    return t
            except Exception:
                continue
    return types[0]


def _get_or_create_line_style(doc, name):
    """Подкатегория категории «Линии» с этим именем (создаётся при
    отсутствии, цвет — фирменный синий). GraphicsStyle или None."""
    if not name or not name.strip():
        return None
    name = name.strip()
    try:
        cats = doc.Settings.Categories
        lines_cat = cats.get_Item(BuiltInCategory.OST_Lines)

        sub = None
        for s in lines_cat.SubCategories:
            if s.Name == name:
                sub = s
                break
        if sub is None:
            sub = cats.NewSubcategory(lines_cat, name)
        try:
            sub.LineColor = Color(27, 97, 180)
        except Exception:
            pass
        return sub.GetGraphicsStyle(GraphicsStyleType.Projection)
    except Exception:
        return None


def _apply_boundary_style(filled_region, gstyle):
    if gstyle is None:
        return
    try:
        filled_region.SetLineStyleId(gstyle.Id)
    except Exception:
        pass


def _delete_previous(doc, view, tag, cam_ids, dori_style_name):
    """Удалить с вида зоны выбранных камер, созданные прошлым запуском:
    FilledRegion по метке в «Комментариях», дуги DORI по имени стиля линии."""
    to_del = List[ElementId]()
    prefix = tag + u"|"

    for fr in FilteredElementCollector(doc, view.Id).OfClass(FilledRegion):
        p = fr.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        s = p.AsString() if (p is not None and p.HasValue) else None
        if not s or not s.startswith(prefix):
            continue
        try:
            cid = int(s.split(u"|")[1])
        except Exception:
            cid = None
        if cid is None or cid in cam_ids:
            to_del.Add(fr.Id)

    if dori_style_name:
        for dc in FilteredElementCollector(doc, view.Id).OfClass(CurveElement):
            try:
                gs = dc.LineStyle
                nm = Element.Name.GetValue(gs) if gs is not None else None
            except Exception:
                nm = None
            if nm and nm == dori_style_name:
                to_del.Add(dc.Id)

    if to_del.Count:
        try:
            doc.Delete(to_del)
        except Exception:
            pass


# ======================================================================
#  ЗОНЫ DORI  (EN 62676-4)
# ======================================================================

_DORI_LEVELS = (
    (u"Идентификация", 250.0),
    (u"Распознавание", 125.0),
    (u"Наблюдение", 63.0),
    (u"Обнаружение", 25.0),
)


def _draw_dori(doc, view, center, base, half, h_res_px, hfov_rad, max_r, z, gstyle):
    if h_res_px <= 0 or hfov_rad <= 1e-4:
        return
    tan_half = math.tan(hfov_rad / 2.0)
    if tan_half <= 1e-6:
        return

    sweep = 2.0 * half
    if sweep <= 1e-3 or sweep >= 2.0 * math.pi - 1e-3:
        return

    for _name, ppm in _DORI_LEVELS:
        d_ft = (h_res_px / (2.0 * ppm * tan_half)) / _M_PER_FT
        if not (0.1 < d_ft <= max_r):
            continue
        c = XYZ(center.X, center.Y, z)
        try:
            arc = Arc.Create(c, d_ft, base - half, base + half, XYZ.BasisX, XYZ.BasisY)
            dc = doc.Create.NewDetailCurve(view, arc)
            if gstyle is not None:
                try:
                    dc.LineStyle = gstyle
                except Exception:
                    pass
        except Exception:
            continue


# ======================================================================
#  ГЛАВНЫЙ ВХОД
# ======================================================================

def _one_camera(doc, cam, view, s, frt, line_style, dori_style,
                clip, ray_count, boundary_mode, target_off_ft, offset_deg,
                dead_zone_on, unit_mode, h_res, tag, z):
    if not isinstance(cam.Location, LocationPoint):
        return (cam, u"no_location", u"")

    dist_name = (s.get("distance_param_name") or u"").strip()
    dist_p = cam.LookupParameter(dist_name)
    if dist_p is None or not dist_p.HasValue:
        return (cam, u"no_distance_param", dist_name or u"(имя не задано)")

    # горизонтальный угол: сначала из оптики (фокусное + матрица),
    # иначе — из прямого параметра угла обзора
    optic_vfov = None
    optic = _optical_fov(cam, s)
    if optic is not None:
        hfov, optic_vfov = optic
    else:
        ang_name = (s.get("angle_param_name") or u"").strip()
        ang_p = cam.LookupParameter(ang_name) if ang_name else None
        if ang_p is None or not ang_p.HasValue:
            return (cam, u"no_angle_param", ang_name or u"(имя не задано)")
        hfov = _param_radians(ang_p, unit_mode)

    max_r = dist_p.AsDouble()
    if hfov <= 1e-4:
        return (cam, u"bad_geometry",
                u"угол обзора = {:.4f} рад ({:.1f}°) — параметр не заполнен "
                u"или не тот; проверьте «Единицы углов»".format(
                    hfov, math.degrees(hfov)))
    if max_r <= 0.02:
        return (cam, u"bad_geometry",
                u"дальность = {:.3f} фт ({:.0f} мм) — параметр «{}» пуст или "
                u"не типа «Длина»".format(max_r, max_r * 304.8, dist_name))
    hfov = min(hfov, 2.0 * math.pi - 1e-3)
    half = hfov / 2.0

    d, dir_note = _look_direction(cam, offset_deg)
    if d is None:
        return (cam, u"bad_geometry",
                u"не удалось определить направление камеры [{}]".format(dir_note))
    base = math.atan2(d.Y, d.X)

    # индивидуальный разворот камеры параметром внутри семейства
    rot = _opt_param_radians(cam, s.get("rotation_param_name"), unit_mode)
    if rot:
        base += rot
        dir_note = u"{} + поворот {:.1f}°".format(dir_note, math.degrees(rot))

    p = cam.Location.Point
    center = XYZ(p.X, p.Y, 0.0)

    tilt = _opt_param_radians(cam, s.get("tilt_param_name"), unit_mode)
    vfov = _opt_param_radians(cam, s.get("vfov_param_name"), unit_mode)
    if vfov is None:
        vfov = optic_vfov          # из оптики, если явного параметра нет
    h_ft = _mounting_height_ft(doc, cam, view, s.get("height_param_name"))
    if h_ft is not None:
        h_ft = h_ft - target_off_ft

    near_r, far_r = _near_far_radius(h_ft, tilt, vfov, max_r)
    if not dead_zone_on:
        near_r = 0.0

    status = u"ok"
    rings = None
    room_note = u""
    if clip:
        rings, room_note = room_rings_for_point(doc, p, boundary_mode)
        if rings is None:
            status = u"ok_no_room"

    cl = _zone_curveloop(center, base, half, near_r, far_r, rings, ray_count, z)
    if cl is None and rings is not None:
        # обрезка «съела» весь контур (камера на самой границе / выбрано
        # чужое помещение) — строим без обрезки, но помечаем
        cl = _zone_curveloop(center, base, half, near_r, far_r, None, ray_count, z)
        if cl is not None:
            status = u"ok_clip_failed"
    if cl is None:
        return (cam, u"bad_geometry",
                u"контур вырожден (near={:.2f} far={:.2f} фт, обрезка={})".format(
                    near_r, far_r, u"да" if rings is not None else u"нет"))

    try:
        fr = FilledRegion.Create(doc, frt.Id, view.Id, List[CurveLoop]([cl]))
    except Exception as ex:
        return (cam, u"create_failed", u"{}".format(ex))

    cp = fr.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if cp is not None and not cp.IsReadOnly:
        try:
            cp.Set(u"{}|{}".format(tag, cam.Id.IntegerValue))
        except Exception:
            pass

    _apply_boundary_style(fr, line_style)

    if dori_style is not None and h_res > 0:
        _draw_dori(doc, view, center, base, half, h_res, hfov, max_r, z, dori_style)

    if not clip:
        clip_note = u"без обрезки (выключена)"
    elif status == u"ok_no_room":
        clip_note = u"без обрезки — {}".format(room_note or u"помещение не найдено")
    elif status == u"ok_clip_failed":
        clip_note = u"без обрезки (обрезка дала пустой контур); {}".format(room_note)
    elif rings is not None:
        clip_note = u"обрезка: {} ({} сегм.)".format(
            room_note or u"помещение", sum(len(r) for r in rings))
    else:
        clip_note = u"без обрезки"

    az = math.degrees(base) % 360.0
    summary = (u"азимут {:.0f}°, угол {:.0f}°, R {:.1f}–{:.1f} м; напр.: {}; {}"
               .format(az, math.degrees(hfov),
                       near_r * _M_PER_FT, far_r * _M_PER_FT,
                       dir_note, clip_note))
    return (cam, status, summary)


def resolve_category_ids(doc, text):
    """
    Множество int-id категорий для фильтра выбора камер. Каждый токен
    (через запятую / точку с запятой / перевод строки) трактуется как имя
    BuiltInCategory (OST_SecurityDevices) либо как русское имя категории
    («Оборудование систем безопасности»). Нераспознанные молча
    пропускаются.
    """
    ids = set()
    for tok in re.split(u"[,;\n\r\t]+", text or u""):
        name = tok.strip()
        if not name:
            continue
        bic = getattr(BuiltInCategory, name, None)
        if bic is not None:
            try:
                ids.add(int(bic))
                continue
            except Exception:
                pass
        try:
            for c in doc.Settings.Categories:
                if c.Name and c.Name.strip().lower() == name.lower():
                    ids.add(c.Id.IntegerValue)
                    break
        except Exception:
            pass
    return ids


def build_fov_zones(doc, cameras, view, settings):
    """
    Построить/перестроить зоны обзора по списку камер на виде view.
    Возвращает список (camera, status, detail); status:
      "ok" / "ok_no_room" / "ok_clip_failed" / "no_location" /
      "no_angle_param" / "no_distance_param" / "bad_geometry" /
      "create_failed". detail — текст с числами/векторами для диагностики.
    Транзакция — на вызывающей стороне.
    """
    s = settings

    frt = _pick_filled_region_type(doc, s.get("fill_type_name"))
    if frt is None:
        return [(None, u"no_fill_type",
                 u"В проекте нет ни одного типа области заливки (FilledRegionType).")]

    line_style = _get_or_create_line_style(doc, s.get("line_subcategory") or u"СОТ_Зона обзора")

    dori_on = _as_bool(s.get("draw_dori"))
    base_sub = (s.get("line_subcategory") or u"СОТ_Зона обзора").strip()
    dori_style_name = base_sub + u" · DORI"
    dori_style = _get_or_create_line_style(doc, dori_style_name) if dori_on else None
    h_res = _as_float(s.get("camera_h_res_px"), 0.0) if dori_on else 0.0

    tag = (s.get("zone_tag") or u"CCTV_FOV").strip() or u"CCTV_FOV"
    clip = _as_bool(s.get("clip_to_rooms"), default=True)
    ray_count = _as_int(s.get("ray_count"), 96)
    boundary_mode = s.get("room_boundary") or u"отделка"
    target_off_ft = _as_float(s.get("target_level_offset_mm"), 0.0) * _FT_PER_MM
    offset_deg = _as_float(s.get("direction_offset_deg"), 0.0)
    dead_zone_on = _as_bool(s.get("draw_dead_zone"), default=True)
    unit_mode = s.get("angle_unit") or u"авто"

    cam_ids = set(c.Id.IntegerValue for c in cameras)
    _delete_previous(doc, view, tag, cam_ids, dori_style_name if dori_on else None)

    z = 0.0
    gen = getattr(view, "GenLevel", None)
    if gen is not None:
        try:
            z = gen.Elevation
        except Exception:
            z = 0.0

    results = []
    for cam in cameras:
        try:
            results.append(_one_camera(
                doc, cam, view, s, frt, line_style, dori_style,
                clip, ray_count, boundary_mode, target_off_ft, offset_deg,
                dead_zone_on, unit_mode, h_res, tag, z))
        except Exception as ex:
            results.append((cam, u"create_failed", u"{}".format(ex)))
    return results


# ======================================================================
#  НАСТРОЙКИ  (окно + хранение, по образцу room_info_settings.py)
# ======================================================================

import os
import io
import json

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from pyrevit import forms
from lowlife import settings_transfer

from System.Windows import (
    Window, WindowStartupLocation, Thickness,
    FontWeights, HorizontalAlignment, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, Orientation, DockPanel, Dock,
    ScrollViewer, ScrollBarVisibility
)
from System.Windows.Media import Brushes

SETTINGS_FILE_NAME = "LowLifeCameraFov_settings.json"

# (ключ, заголовок раздела, подпись поля, пояснение, значение по умолчанию, обязательное)
TEXT_FIELDS = [
    (
        "camera_categories",
        u"⓪ Что выбирать",
        u"Категории камер для фильтра выбора",
        u"Через запятую. Имя BuiltInCategory (OST_SecurityDevices, "
        u"OST_CommunicationDevices, OST_DataDevices, OST_ElectricalEquipment, "
        u"OST_GenericModel) и/или русское имя категории как в дереве "
        u"«Категории» («Оборудование систем безопасности»). Кнопка даст "
        u"выбрать только элементы этих категорий. Если после нажатия ничего "
        u"не выделяется — камера не в этой категории; посмотрите её "
        u"категорию в свойствах и впишите сюда.",
        u"OST_SecurityDevices", True
    ),
    (
        "angle_param_name",
        u"① Параметры камеры (в этой модели)",
        u"Параметр «горизонтальный угол обзора»",
        u"Имя параметра экземпляра камеры с углом обзора в плане. Тип "
        u"параметра — «Угол» (тогда значение читается в радианах) либо "
        u"«Число» (тогда см. «Единицы углов»). Можно не задавать, если "
        u"заполнены «Фокусное расстояние» + «Формат матрицы» ниже — тогда "
        u"угол считается из оптики и это поле игнорируется.",
        u"УГО_ПВ_Угол обзора", False
    ),
    (
        "focal_length_param_name",
        u"",
        u"Параметр «фокусное расстояние», мм",
        u"Имя параметра объектива. Если задан и найден (+ заполнен «Формат "
        u"матрицы») — горизонтальный угол считается как "
        u"θ = 2·arctg(ширина матрицы / (2·f)), а параметр угла обзора не "
        u"используется. Тип «Длина» → пересчёт из футов; «Число» → как есть, "
        u"в мм. Для варифокального объектива берётся текущее значение "
        u"параметра.",
        u"", False
    ),
    (
        "sensor_format",
        u"",
        u"Формат матрицы",
        u"Нужен вместе с фокусным расстоянием. Оптический формат — «1/2.8», "
        u"«1/3», «1/1.8», «2/3», «1» (по таблице); либо явные размеры "
        u"активной области «ШхВ» в мм — «5.37x4.04»; либо одна ширина «5.37» "
        u"(высота = 3/4). По высоте матрицы дополнительно вычисляется "
        u"вертикальный угол — если параметр вертикального угла не задан.",
        u"", False
    ),
    (
        "distance_param_name",
        u"",
        u"Параметр «дальность» (макс. радиус зоны)",
        u"Имя параметра экземпляра с максимальной дальностью обзора. Должен "
        u"быть параметром типа «Длина» (иначе значение уедет по единицам). "
        u"Задаёт дальнюю границу зоны, если она не ограничена расчётом по "
        u"наклону/вертикальному углу.",
        u"УГО_ПВ_Дистанция до объекта", True
    ),
    (
        "angle_unit",
        u"",
        u"Единицы всех угловых параметров",
        u"«авто» — по типу параметра (тип «Угол» → радианы, иначе число "
        u"трактуется как градусы). «градусы» / «радианы» — принудительно "
        u"для всех угловых полей (угол обзора, наклон, вертикальный угол).",
        u"авто", False
    ),
    (
        "height_param_name",
        u"",
        u"Параметр «высота установки» над уровнем",
        u"Имя параметра высоты монтажа камеры (тип «Длина»). Если пусто — "
        u"высота берётся как отметка точки вставки минус отметка уровня "
        u"камеры. Нужна для расчёта ближней мёртвой зоны и дальней границы.",
        u"", False
    ),
    (
        "tilt_param_name",
        u"",
        u"Параметр «наклон оптической оси вниз»",
        u"Имя углового параметра наклона оси камеры вниз от горизонта "
        u"(0 — камера смотрит горизонтально). Пусто — наклон не учитывается, "
        u"зона строится как плоский сектор.",
        u"", False
    ),
    (
        "vfov_param_name",
        u"",
        u"Параметр «вертикальный угол обзора»",
        u"Имя углового параметра вертикального поля зрения. Вместе с высотой "
        u"и наклоном даёт проекцию конуса на плоскость расчёта: "
        u"near = h / tg(наклон + вертикальный/2), "
        u"far = h / tg(наклон − вертикальный/2).",
        u"", False
    ),
    (
        "rotation_param_name",
        u"",
        u"Параметр «поворот камеры» (угол внутри семейства)",
        u"Имя углового параметра экземпляра, которым камера разворачивается "
        u"НЕ поворотом самого экземпляра, а внутри семейства (тогда "
        u"FacingOrientation не меняется, и без этого поля все зоны смотрят "
        u"в одну сторону). Его значение прибавляется к направлению "
        u"(против часовой стрелки). В исходном Dynamo-скрипте это был "
        u"«Вращение (поворот)». Пусто — если камера разворачивается "
        u"поворотом экземпляра в модели.",
        u"", False
    ),
    (
        "direction_offset_deg",
        u"",
        u"Доворот направления «взгляда», градусы",
        u"Фиксированная поправка направления (одинаковая для всех камер, "
        u"против часовой стрелки), если геометрия камеры в семействе "
        u"смотрит не «вперёд» относительно FacingOrientation. Обычно 0. "
        u"Индивидуальный разворот каждой камеры — это поле выше "
        u"«Параметр поворот камеры», а не это.",
        u"0", False
    ),
    (
        "target_level_offset_mm",
        u"② Плоскость расчёта и форма зоны",
        u"Высота плоскости расчёта над уровнем, мм",
        u"На какой высоте считать зону: 0 — пол; 1500 — плоскость лиц; "
        u"800 — рабочие поверхности. Влияет на ближнюю/дальнюю границу при "
        u"учёте высоты установки.",
        u"0", False
    ),
    (
        "draw_dead_zone",
        u"",
        u"Показывать ближнюю мёртвую зону (да/нет)",
        u"«да» — при заданных высоте/наклоне/вертикальном угле зона рисуется "
        u"кольцевым сектором (с вырезом под камерой). «нет» — всегда сплошной "
        u"сектор от точки камеры.",
        u"да", False
    ),
    (
        "ray_count",
        u"",
        u"Детализация дуги (число лучей на сектор)",
        u"Больше — глаже дуга и точнее обрезка по помещению, но тяжелее "
        u"область заливки. 64–128 обычно достаточно.",
        u"96", False
    ),
    (
        "clip_to_rooms",
        u"③ Обрезка по помещению из связи",
        u"Резать зону по границе помещения (да/нет)",
        u"«да» — зона обрезается по контуру Room из связанной модели, в "
        u"котором стоит камера (учитываются вогнутые помещения и «дыры» — "
        u"колонны/шахты). «нет» — зона строится без обрезки.",
        u"да", False
    ),
    (
        "room_boundary",
        u"",
        u"Граница помещения",
        u"«отделка» — по чистовой поверхности стен (Finish); «центр» — по "
        u"осям стен (Center).",
        u"отделка", False
    ),
    (
        "fill_type_name",
        u"④ Оформление",
        u"Тип области заливки (FilledRegion)",
        u"Имя типа штриховки для зоны. Пусто — берётся первый доступный тип "
        u"в проекте. Прозрачность/цвет настраиваются в самом типе.",
        u"", False
    ),
    (
        "line_subcategory",
        u"",
        u"Подкатегория линий контура",
        u"Имя подкатегории категории «Линии» для границы зоны (создаётся "
        u"автоматически). По ней же именуется стиль дуг DORI "
        u"(«… · DORI»).",
        u"СОТ_Зона обзора", False
    ),
    (
        "zone_tag",
        u"",
        u"Метка зоны в параметре «Комментарии»",
        u"Служебная строка, по которой кнопка находит и удаляет прежние зоны "
        u"этих камер при повторном запуске. Формат записи — «метка|Id камеры».",
        u"CCTV_FOV", True
    ),
    (
        "draw_dori",
        u"⑤ Зоны DORI (EN 62676-4, необязательно)",
        u"Рисовать дуги DORI (да/нет)",
        u"«да» — добавляет концентрические дуги на расстояниях "
        u"идентификации / распознавания / наблюдения / обнаружения "
        u"(250 / 125 / 63 / 25 пикс/м).",
        u"нет", False
    ),
    (
        "camera_h_res_px",
        u"",
        u"Горизонтальное разрешение матрицы, пикс",
        u"Нужно только для дуг DORI. Например 1920 (Full HD), 2560, 3840. "
        u"Расстояние: d = H / (2 · пикс/м · tg(гор.угол / 2)).",
        u"", False
    ),
]

PLAIN_LABELS = {key: label for key, _s, label, _h, _d, _r in TEXT_FIELDS}


def _settings_file_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(appdata, "pyRevit")
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except Exception:
            pass
    return os.path.join(folder, SETTINGS_FILE_NAME)


def _read_all():
    path = _settings_file_path()
    if not os.path.isfile(path):
        return {}
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            text = f.read()
        if not text.strip():
            return {}
        return json.loads(text)
    except Exception:
        return {}


def _write_all(data):
    path = _settings_file_path()
    try:
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(unicode(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)))
    except Exception:
        forms.alert(u"Не удалось сохранить настройки зон обзора в файл:\n{}".format(path))


def load_saved_values():
    saved = _read_all()
    return {key: saved.get(key, default)
            for key, _s, _label, _hint, default, _req in TEXT_FIELDS}


def save_values(values):
    data = _read_all()
    data.update(values)
    _write_all(data)


def require(settings, keys):
    """Останавливает скрипт через forms.alert(exitscript=True), если какие-то
    из перечисленных ключей не заполнены."""
    missing = [PLAIN_LABELS.get(k, k) for k in keys
               if not (settings.get(k) and unicode(settings.get(k)).strip())]
    if missing:
        forms.alert(
            u"Не заполнены обязательные настройки зон обзора:\n\n{}\n\n"
            u"Откройте настройки: Shift+клик по кнопке «Зоны обзора».".format(
                u"\n".join(missing)
            ),
            exitscript=True
        )


def show_settings_form(values):
    result = {"values": None}

    win = Window()
    win.Title = u"Настройки: Зоны обзора видеокамер (СОТ)"
    win.Width = 820
    win.Height = 720
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    root = StackPanel()
    root.Margin = Thickness(16)

    title = TextBlock()
    title.Text = u"Параметры расчёта зоны обзора"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    title.Margin = Thickness(0, 0, 0, 4)
    root.Children.Add(title)

    hint = TextBlock()
    hint.Text = (u"Сначала кнопка, потом выбор камер (фильтр — только «Охранная "
                 u"сигнализация»). Значения сохраняются между запусками.")
    hint.FontSize = 11
    hint.Foreground = Brushes.Gray
    hint.TextWrapping = TextWrapping.Wrap
    hint.Margin = Thickness(0, 0, 0, 10)
    root.Children.Add(hint)

    boxes = {}

    for key, section_title, label_text, hint_text, _default, required in TEXT_FIELDS:
        if section_title:
            section = TextBlock()
            section.Text = section_title
            section.FontWeight = FontWeights.Bold
            section.Margin = Thickness(0, 16, 0, 2)
            root.Children.Add(section)

        label = TextBlock()
        label.Text = label_text + (u" *" if required else u"")
        label.Margin = Thickness(0, 8, 0, 2)
        label.TextWrapping = TextWrapping.Wrap
        root.Children.Add(label)

        box = TextBox()
        box.Text = values.get(key, "")
        box.Padding = Thickness(4)
        root.Children.Add(box)
        boxes[key] = box

        h = TextBlock()
        h.Text = hint_text
        h.FontSize = 11
        h.Foreground = Brushes.Gray
        h.TextWrapping = TextWrapping.Wrap
        h.Margin = Thickness(0, 2, 0, 0)
        root.Children.Add(h)

    required_hint = TextBlock()
    required_hint.Text = u"* обязательные поля"
    required_hint.FontSize = 11
    required_hint.Foreground = Brushes.Gray
    required_hint.Margin = Thickness(0, 12, 0, 0)
    root.Children.Add(required_hint)

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(16, 8, 16, 12)
    DockPanel.SetDock(buttons, Dock.Bottom)

    reset_btn = Button()
    reset_btn.Content = u"Сбросить"
    reset_btn.Padding = Thickness(10, 4, 10, 4)
    reset_btn.Margin = Thickness(0, 0, 8, 0)

    cancel_btn = Button()
    cancel_btn.Content = u"Отмена"
    cancel_btn.Padding = Thickness(10, 4, 10, 4)
    cancel_btn.Margin = Thickness(0, 0, 8, 0)

    ok_btn = Button()
    ok_btn.Content = u"Сохранить"
    ok_btn.Padding = Thickness(10, 4, 10, 4)
    ok_btn.FontWeight = FontWeights.Bold

    def on_reset(sender, args):
        for key, _s, _label, _hint, default, _req in TEXT_FIELDS:
            boxes[key].Text = default

    def on_ok(sender, args):
        result["values"] = {key: box.Text for key, box in boxes.items()}
        win.Close()

    def on_cancel(sender, args):
        win.Close()

    reset_btn.Click += on_reset
    ok_btn.Click += on_ok
    cancel_btn.Click += on_cancel

    buttons.Children.Add(reset_btn)
    buttons.Children.Add(cancel_btn)
    buttons.Children.Add(ok_btn)

    def _on_settings_imported():
        result["values"] = settings_transfer.RELOAD
        win.Close()

    settings_transfer.add_transfer_buttons(
        buttons, _read_all, _write_all, u"зон обзора", _on_settings_imported
    )

    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scroll.Content = root

    outer.Children.Add(buttons)
    outer.Children.Add(scroll)

    win.Content = outer
    win.ShowDialog()

    return result["values"]


def get_settings_interactive():
    """Окно настроек: сохраняет и возвращает значения; None при отмене.
    Открывается по Shift+клику на кнопке «Зоны обзора»."""
    while True:
        saved = load_saved_values()
        edited = show_settings_form(saved)

        if edited == settings_transfer.RELOAD:
            continue
        if edited is None:
            return None

        save_values(edited)
        return edited


def get_settings_silent():
    """Сохранённые значения без показа окна (или значения по умолчанию)."""
    return load_saved_values()
