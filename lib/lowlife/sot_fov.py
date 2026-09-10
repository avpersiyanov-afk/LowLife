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


# ======================================================================
#  ГЕОМЕТРИЯ КАМЕРЫ
# ======================================================================

def _look_direction(fi, offset_deg):
    """
    Горизонтальный единичный вектор «куда смотрит» камера. Основной
    источник — FamilyInstance.FacingOrientation (учитывает поворот и
    зеркалирование экземпляра). Резерв — оси её Transform. offset_deg —
    фиксированный доворот против часовой стрелки, если «взгляд» семейства
    не совпал с FacingOrientation. None, если направление не определить.
    """
    d = None
    try:
        f = fi.FacingOrientation
        if f is not None and f.GetLength() > 1e-9:
            d = XYZ(f.X, f.Y, 0.0)
    except Exception:
        d = None

    if d is None or d.GetLength() < 1e-9:
        try:
            t = fi.GetTransform()
            d = XYZ(t.BasisX.X, t.BasisX.Y, 0.0)
            if d.GetLength() < 1e-6:
                d = XYZ(t.BasisY.X, t.BasisY.Y, 0.0)
        except Exception:
            d = None

    if d is None or d.GetLength() < 1e-9:
        return None

    d = d.Normalize()

    if offset_deg:
        a = math.radians(offset_deg)
        ca, sa = math.cos(a), math.sin(a)
        d = XYZ(d.X * ca - d.Y * sa, d.X * sa + d.Y * ca, 0.0)

    return d


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
            try:
                curve = seg.GetCurve().CreateTransformed(tf)
                tess = curve.Tessellate()
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
    Контуры помещения (в координатах хоста), в котором находится
    host_point, перебирая все RevitLinkInstance. Проход 1 — точное
    попадание (Room.IsPointInRoom в координатах связи). Проход 2 —
    ближайший Room, чей контур не дальше 90 мм по горизонтали (камера
    «сидит» в стене). None, если ничего не нашлось.
    """
    opt = _boundary_options(boundary_mode)

    candidates = []   # (dist, rings) для прохода 2

    for li in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        ldoc = li.GetLinkDocument()
        if ldoc is None:
            continue
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

            hit = False
            try:
                hit = room.IsPointInRoom(p_link)
            except Exception:
                hit = False

            rings = None
            if hit:
                rings = _room_boundary_rings(room, opt, tf)
                if rings:
                    return rings

            # для прохода 2
            if not hit:
                rings = rings or _room_boundary_rings(room, opt, tf)
                if not rings:
                    continue
                if _point_in_ring(host_point.X, host_point.Y, rings[0]) and \
                   not any(_point_in_ring(host_point.X, host_point.Y, h) for h in rings[1:]):
                    return rings
                d = _dist_point_to_rings(host_point.X, host_point.Y, rings)
                if d is not None and d <= _ROOM_TOLERANCE_FT:
                    candidates.append((d, rings))

    if candidates:
        candidates.sort(key=lambda c: c[0])
        return candidates[0][1]
    return None


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

    ang_p = cam.LookupParameter((s.get("angle_param_name") or u"").strip())
    if ang_p is None or not ang_p.HasValue:
        return (cam, u"no_angle_param", s.get("angle_param_name") or u"")
    dist_p = cam.LookupParameter((s.get("distance_param_name") or u"").strip())
    if dist_p is None or not dist_p.HasValue:
        return (cam, u"no_distance_param", s.get("distance_param_name") or u"")

    hfov = _param_radians(ang_p, unit_mode)
    max_r = dist_p.AsDouble()
    if hfov <= 1e-4 or max_r <= 0.02:
        return (cam, u"bad_geometry", u"угол/дальность = 0")
    hfov = min(hfov, 2.0 * math.pi - 1e-3)
    half = hfov / 2.0

    d = _look_direction(cam, offset_deg)
    if d is None:
        return (cam, u"bad_geometry", u"нет направления")
    base = math.atan2(d.Y, d.X)

    p = cam.Location.Point
    center = XYZ(p.X, p.Y, 0.0)

    tilt = _opt_param_radians(cam, s.get("tilt_param_name"), unit_mode)
    vfov = _opt_param_radians(cam, s.get("vfov_param_name"), unit_mode)
    h_ft = _mounting_height_ft(doc, cam, view, s.get("height_param_name"))
    if h_ft is not None:
        h_ft = h_ft - target_off_ft

    near_r, far_r = _near_far_radius(h_ft, tilt, vfov, max_r)
    if not dead_zone_on:
        near_r = 0.0

    status = u"ok"
    rings = None
    if clip:
        rings = room_rings_for_point(doc, center, boundary_mode)
        if rings is None:
            status = u"ok_no_room"

    cl = _zone_curveloop(center, base, half, near_r, far_r, rings, ray_count, z)
    if cl is None:
        return (cam, u"bad_geometry", u"пустой контур")

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

    return (cam, status, u"")


def build_fov_zones(doc, cameras, view, settings):
    """
    Построить/перестроить зоны обзора по списку камер на виде view.
    Возвращает список (camera, status, detail); status:
      "ok" / "ok_no_room" / "no_location" / "no_angle_param" /
      "no_distance_param" / "bad_geometry" / "create_failed".
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
        "angle_param_name",
        u"① Параметры камеры (в этой модели)",
        u"Параметр «горизонтальный угол обзора»",
        u"Имя параметра экземпляра камеры с углом обзора в плане. Если это "
        u"параметр типа «Угол» — значение берётся как есть (радианы); иначе "
        u"см. поле «Единицы углов» ниже.",
        u"УГО_ПВ_Угол обзора", True
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
        "direction_offset_deg",
        u"",
        u"Доворот направления «взгляда», градусы",
        u"Фиксированная поправка направления относительно FacingOrientation "
        u"семейства (против часовой стрелки), если геометрия камеры в "
        u"семействе смотрит не «вперёд». Обычно 0. Параметр поворота "
        u"экземпляра отдельно НЕ прибавляется — FacingOrientation его уже "
        u"учитывает.",
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
