# -*- coding: utf-8 -*-
"""Поворот 3D вида под ось (`Tools.panel/Rotate3DView`).

В открытом 3D виде пользователь выбирает ось сетки из списка (оси модели и
загруженных связей — в 3D видах Revit оси обычно не показывает) или кликает
на виде прямой линейный элемент (стену, линию модели, лоток…, в том числе в
связанном файле), и вид поворачивается вокруг вертикали так, чтобы смотреть вдоль
или поперёк этой оси: камера доворачивается на ближайший из четырёх углов
(ось / перпендикуляр к ней, в обе стороны), наклон камеры не меняется.
Включённая рамка 3D вида поворачивается так же — её стороны становятся
параллельны и перпендикулярны оси.

Поворот — вокруг вертикали через центр рамки 3D вида, без рамки — через
центр области подрезки вида, чтобы модель оставалась в кадре.

Чистая часть (`align_angle`, `rotate_vector`, `rotate_point`,
`rotate_camera`, `natural_key`) работает на кортежах и покрыта
`tests/test_view_rotate.py`; Revit API импортируется лениво.
"""

import math
import re

Z_AXIS = (0.0, 0.0, 1.0)

# Направление в плане короче этого (после проекции на XY) считаем
# вертикальным — вдоль такой оси вид не повернуть.
MIN_PLAN_LENGTH = 1e-6


def _norm(v):
    length = math.sqrt(sum(c * c for c in v))
    if length < 1e-12:
        raise ValueError(u"Нулевое направление.")
    return tuple(c / length for c in v)


def plan_angle(v):
    """Угол направления v в плане (рад) или None, если v почти вертикален."""
    if math.hypot(v[0], v[1]) < MIN_PLAN_LENGTH:
        return None
    return math.atan2(v[1], v[0])


def align_angle(current, axis):
    """Наименьший поворот вокруг вертикали (рад, (-π/4, π/4]), после которого
    направление `current` в плане идёт вдоль `axis` или перпендикулярно ей.

    current/axis — векторы (x, y[, z]); ValueError, если какой-то из них
    вертикален (нет направления в плане).
    """
    a = plan_angle(current)
    b = plan_angle(axis)
    if a is None or b is None:
        raise ValueError(u"Направление вертикально — в плане его нет.")
    quarter = math.pi / 2
    delta = math.fmod(b - a, quarter)
    if delta > quarter / 2:
        delta -= quarter
    elif delta <= -quarter / 2:
        delta += quarter
    return delta


def natural_key(text):
    """Ключ сортировки имён осей «по-человечески»: «2» раньше «10», буквы без
    учёта регистра."""
    parts = re.split(r"(\d+)", text or u"")
    return [(0, int(p), u"") if p.isdigit() else (1, 0, p.lower()) for p in parts if p]


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


def camera_plan_direction(up, forward):
    """Направление взгляда камеры в плане: forward, а если камера смотрит
    строго вверх/вниз — up (он тогда горизонтален)."""
    if plan_angle(forward) is not None:
        return forward
    return up


def rotate_camera(eye, up, forward, origin, angle_rad):
    """(eye, up, forward) камеры, повёрнутой вокруг вертикали через origin."""
    return (rotate_point(eye, origin, Z_AXIS, angle_rad),
            _norm(rotate_vector(up, Z_AXIS, angle_rad)),
            _norm(rotate_vector(forward, Z_AXIS, angle_rad)))


# --- Revit API --------------------------------------------------------------

def _xyz_tuple(p):
    return (p.X, p.Y, p.Z)


def unsupported_reason(view):
    """Текст причины, почему активный вид не повернуть, или None."""
    from Autodesk.Revit.DB import View3D
    if not isinstance(view, View3D) or view.IsTemplate:
        return u"Откройте 3D вид, который нужно повернуть, и запустите кнопку на нём."
    try:
        if view.IsLocked:
            return (u"3D вид заблокирован (ориентация сохранена). Разблокируйте "
                    u"его на панели вида и повторите.")
    except Exception:
        pass
    return None


def element_line(element):
    """Прямая линия элемента (Line) или None: ось сетки, линия модели/
    детализации, элемент с линейной LocationCurve (стена, лоток, балка…)."""
    from Autodesk.Revit.DB import CurveElement, Grid, Line, LocationCurve
    curve = None
    try:
        if isinstance(element, Grid):
            curve = element.Curve
        elif isinstance(element, CurveElement):
            curve = element.GeometryCurve
        else:
            loc = element.Location
            if isinstance(loc, LocationCurve):
                curve = loc.Curve
    except Exception:
        return None
    return curve if isinstance(curve, Line) else None


def _is_axis_element(element):
    line = element_line(element)
    return line is not None and plan_angle(_xyz_tuple(line.Direction)) is not None


def make_pick_filter(doc, linked=False):
    """ISelectionFilter для PickObject: прямые невертикальные линейные
    элементы. linked=False — элементы модели (ObjectType.Element), True —
    элементы связанных файлов (ObjectType.LinkedElement: в этом режиме Revit
    даёт выбирать только содержимое связей)."""
    from Autodesk.Revit.DB import ElementId, RevitLinkInstance
    from Autodesk.Revit.UI.Selection import ISelectionFilter

    class AxisFilter(ISelectionFilter):
        def AllowElement(self, element):
            if linked:
                return isinstance(element, RevitLinkInstance)
            return _is_axis_element(element)

        def AllowReference(self, reference, position):
            if not linked or reference.LinkedElementId == ElementId.InvalidElementId:
                return True
            try:
                link = doc.GetElement(reference.ElementId)
                return _is_axis_element(link.GetLinkDocument().GetElement(reference.LinkedElementId))
            except Exception:
                return False

    return AxisFilter()


def picked_direction(doc, reference):
    """(направление оси в координатах модели, имя элемента) по выбранной
    ссылке, или ValueError с пояснением."""
    from Autodesk.Revit.DB import Element, ElementId, RevitLinkInstance
    element = doc.GetElement(reference.ElementId)
    transform = None
    if isinstance(element, RevitLinkInstance) and reference.LinkedElementId != ElementId.InvalidElementId:
        transform = element.GetTotalTransform()
        element = element.GetLinkDocument().GetElement(reference.LinkedElementId)
    line = element_line(element) if element is not None else None
    if line is None:
        raise ValueError(u"Выбранный элемент — не прямая ось: выберите ось сетки, "
                         u"линию или прямую стену/лоток.")
    direction = line.Direction
    if transform is not None:
        direction = transform.OfVector(direction)
    if plan_angle(_xyz_tuple(direction)) is None:
        raise ValueError(u"Выбранная линия вертикальна — под неё вид в плане не повернуть.")
    try:
        name = Element.Name.GetValue(element)
    except Exception:
        name = u""
    return direction, name


def list_grid_axes(doc):
    """[(подпись, направление XYZ в координатах модели)] — прямые оси сетки
    модели и загруженных связей (подпись связи — в скобках), по имени."""
    from Autodesk.Revit.DB import Element, FilteredElementCollector, Grid, RevitLinkInstance

    def grids(source):
        for g in FilteredElementCollector(source).OfClass(Grid):
            line = element_line(g)
            if line is None or plan_angle(_xyz_tuple(line.Direction)) is None:
                continue
            yield Element.Name.GetValue(g), line.Direction

    items = [(name, name, d) for name, d in grids(doc)]
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        link_doc = link.GetLinkDocument()
        if link_doc is None:
            continue
        transform = link.GetTotalTransform()
        link_name = Element.Name.GetValue(link).split(u" : ")[0]
        for name, d in grids(link_doc):
            items.append((name, u"{}  (связь: {})".format(name, link_name), transform.OfVector(d)))
    items.sort(key=lambda it: (natural_key(it[0]), it[1]))
    return [(label, d) for _name, label, d in items]


def _box_center(box):
    return box.Transform.OfPoint(box.Min.Add(box.Max).Multiply(0.5))


def view_pivot(view):
    """Центр рамки 3D вида, если она включена, иначе центр области подрезки,
    иначе точка глаза."""
    try:
        if view.IsSectionBoxActive:
            return _box_center(view.GetSectionBox())
    except Exception:
        pass
    try:
        return _box_center(view.CropBox)
    except Exception:
        return view.GetOrientation().EyePosition


def align_view(view, direction):
    """Поворачивает камеру (и рамку 3D вида, если включена) под направление
    оси. В открытой транзакции. Возвращает (угол камеры, угол рамки или None)
    в градусах."""
    from Autodesk.Revit.DB import Transform, ViewOrientation3D, XYZ
    axis = _xyz_tuple(direction)

    box_deg = None
    if view.IsSectionBoxActive:
        box = view.GetSectionBox()
        angle = align_angle(_xyz_tuple(box.Transform.BasisX), axis)
        if abs(angle) > 1e-9:
            rot = Transform.CreateRotationAtPoint(XYZ.BasisZ, angle, _box_center(box))
            box.Transform = rot.Multiply(box.Transform)
            view.SetSectionBox(box)
        box_deg = math.degrees(angle)

    pivot = _xyz_tuple(view_pivot(view))
    ori = view.GetOrientation()
    up, fwd = _xyz_tuple(ori.UpDirection), _xyz_tuple(ori.ForwardDirection)
    angle = align_angle(camera_plan_direction(up, fwd), axis)
    if abs(angle) > 1e-9:
        eye, up, fwd = rotate_camera(_xyz_tuple(ori.EyePosition), up, fwd, pivot, angle)
        view.SetOrientation(ViewOrientation3D(XYZ(*eye), XYZ(*up), XYZ(*fwd)))
    return math.degrees(angle), box_deg
