# -*- coding: utf-8 -*-
"""Поворот 3D вида вокруг оси (`Tools.panel/Rotate3DView`).

Revit умеет вращать 3D вид только мышью/видовым кубом — без точного угла и
без выбора оси. Кнопка поворачивает камеру 3D вида (ViewOrientation3D:
точка глаза, направления «вперёд» и «вверх») вокруг оси модели X/Y/Z или
вокруг оси сетки (Grid) на заданный угол. Модель в кадре поворачивается на
этот угол против часовой стрелки, если смотреть с конца оси на начало
(отрицательный угол — по часовой); для этого камера поворачивается на
противоположный угол.

Оси X/Y/Z проходят через центр рамки 3D вида (если она включена), иначе —
через центр области подрезки вида; ось сетки — по самой линии сетки.

Чистая часть (`parse_angle`, `rotate_vector`, `rotate_point`,
`rotate_orientation`, `AXES`) работает на кортежах и покрыта
`tests/test_view_rotate.py`; Revit API импортируется лениво.
"""

import math

AXIS_GRID = "grid"

# (ключ, подпись в окне).
AXES = (
    ("x", u"X модели"),
    ("y", u"Y модели"),
    ("z", u"Z модели (вертикаль)"),
    (AXIS_GRID, u"Ось сетки"),
)
DEFAULT_AXIS = "z"
DEFAULT_ANGLE = 90.0

AXIS_VECTORS = {
    "x": (1.0, 0.0, 0.0),
    "y": (0.0, 1.0, 0.0),
    "z": (0.0, 0.0, 1.0),
}


def parse_angle(text):
    """Текст угла в градусах («90», «-45», «12,5», «30°») -> float.

    Угол приводится к (-360, 360). ValueError — если не число или поворот
    нулевой (на полный оборот тоже).
    """
    raw = (text or u"").strip().replace(u",", u".").replace(u"°", u"").strip()
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(u"Угол поворота должен быть числом в градусах, например 90 или -45.")
    if math.isnan(value) or math.isinf(value):
        raise ValueError(u"Угол поворота должен быть числом в градусах, например 90 или -45.")
    value = math.fmod(value, 360.0)
    if abs(value) < 1e-9:
        raise ValueError(u"Угол поворота не должен быть нулевым (или кратным 360°).")
    return value


def _norm(v):
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if length < 1e-12:
        raise ValueError(u"Нулевое направление оси.")
    return (v[0] / length, v[1] / length, v[2] / length)


def rotate_vector(v, axis, angle_rad):
    """Поворот вектора v вокруг направления axis на angle_rad (правило правой
    руки, формула Родрига)."""
    k = _norm(axis)
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    dot = k[0] * v[0] + k[1] * v[1] + k[2] * v[2]
    cross = (k[1] * v[2] - k[2] * v[1],
             k[2] * v[0] - k[0] * v[2],
             k[0] * v[1] - k[1] * v[0])
    return tuple(v[i] * c + cross[i] * s + k[i] * dot * (1.0 - c) for i in range(3))


def rotate_point(p, origin, axis, angle_rad):
    """Поворот точки p вокруг прямой (origin, axis) на angle_rad."""
    rel = (p[0] - origin[0], p[1] - origin[1], p[2] - origin[2])
    r = rotate_vector(rel, axis, angle_rad)
    return (r[0] + origin[0], r[1] + origin[1], r[2] + origin[2])


def rotate_orientation(eye, up, forward, origin, axis, model_angle_deg):
    """Новая (eye, up, forward) камеры, при которой модель в кадре повёрнута
    на model_angle_deg вокруг прямой (origin, axis) против часовой стрелки
    (если смотреть с конца оси). Камера поворачивается на противоположный
    угол, взаимная перпендикулярность up/forward сохраняется."""
    a = -math.radians(model_angle_deg)
    return (rotate_point(eye, origin, axis, a),
            _norm(rotate_vector(up, axis, a)),
            _norm(rotate_vector(forward, axis, a)))


# --- Revit API --------------------------------------------------------------

def _name(el):
    from Autodesk.Revit.DB import Element
    return Element.Name.GetValue(el)


def list_3d_views(doc):
    """[(имя, View3D)] — 3D виды проекта без шаблонов, по имени."""
    from Autodesk.Revit.DB import FilteredElementCollector, View3D
    views = [v for v in FilteredElementCollector(doc).OfClass(View3D) if not v.IsTemplate]
    items = [(_name(v), v) for v in views]
    items.sort(key=lambda it: it[0].lower())
    return items


def list_grids(doc):
    """[(имя, Grid)] — прямые оси сетки проекта (дуговые не годятся как ось
    поворота), по имени."""
    from Autodesk.Revit.DB import FilteredElementCollector, Grid, Line
    items = []
    for g in FilteredElementCollector(doc).OfClass(Grid):
        try:
            if g.IsCurved or not isinstance(g.Curve, Line):
                continue
        except Exception:
            continue
        items.append((_name(g), g))
    items.sort(key=lambda it: it[0].lower())
    return items


def unsupported_reason(view):
    """Текст причины, почему вид не повернуть, или None."""
    if view.IsTemplate:
        return u"«{}» — шаблон вида.".format(_name(view))
    try:
        if view.IsLocked:
            return (u"Вид «{}» заблокирован (ориентация сохранена). Разблокируйте "
                    u"его на видовом кубе или панели вида и повторите.".format(_name(view)))
    except Exception:
        pass
    return None


def _xyz_tuple(p):
    return (p.X, p.Y, p.Z)


def _box_center(box):
    mid = box.Min.Add(box.Max).Multiply(0.5)
    return box.Transform.OfPoint(mid)


def model_pivot(view):
    """Точка, через которую идут оси X/Y/Z: центр рамки 3D вида, если она
    включена, иначе центр области подрезки вида, иначе точка глаза."""
    try:
        if view.IsSectionBoxActive:
            return _box_center(view.GetSectionBox())
    except Exception:
        pass
    try:
        crop = view.CropBox
        if crop is not None:
            return _box_center(crop)
    except Exception:
        pass
    return view.GetOrientation().EyePosition


def axis_line(view, axis_key, grid=None):
    """(точка, направление) оси поворота в координатах модели (XYZ)."""
    from Autodesk.Revit.DB import XYZ
    if axis_key == AXIS_GRID:
        if grid is None:
            raise ValueError(u"Не выбрана ось сетки.")
        line = grid.Curve
        return line.GetEndPoint(0), line.Direction
    vec = AXIS_VECTORS.get(axis_key)
    if vec is None:
        raise ValueError(u"Неизвестная ось: {}".format(axis_key))
    return model_pivot(view), XYZ(*vec)


def rotate_view(view, axis_key, angle_deg, grid=None):
    """Поворачивает камеру 3D вида (в открытой транзакции)."""
    from Autodesk.Revit.DB import XYZ, ViewOrientation3D
    origin, direction = axis_line(view, axis_key, grid)
    ori = view.GetOrientation()
    eye, up, fwd = rotate_orientation(
        _xyz_tuple(ori.EyePosition), _xyz_tuple(ori.UpDirection),
        _xyz_tuple(ori.ForwardDirection), _xyz_tuple(origin),
        _xyz_tuple(direction), angle_deg)
    view.SetOrientation(ViewOrientation3D(XYZ(*eye), XYZ(*up), XYZ(*fwd)))
