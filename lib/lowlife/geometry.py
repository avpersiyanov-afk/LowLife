# -*- coding: utf-8 -*-
"""Общие геометрические хелперы для работы с элементами Revit."""

from Autodesk.Revit.DB import LocationPoint, LocationCurve, Line


def get_point(el):
    """Точка расположения элемента (для point-based экземпляров)."""
    try:
        if isinstance(el.Location, LocationPoint):
            return el.Location.Point
    except:
        pass
    return None


def get_curve_data(el, view):
    """
    Кривая элемента и её концевые точки.
    Если у элемента нет LocationCurve, используется диагональ bounding box.
    """
    try:
        if isinstance(el.Location, LocationCurve):
            c = el.Location.Curve
            return c, c.GetEndPoint(0), c.GetEndPoint(1)
    except:
        pass
    try:
        bbox = el.get_BoundingBox(view)
        if bbox:
            return Line.CreateBound(bbox.Min, bbox.Max), bbox.Min, bbox.Max
    except:
        pass
    return None, None, None


def point_key(p, tol):
    """Ключ для группировки близких точек по сетке с шагом tol."""
    return (
        int(round(p.X / tol)),
        int(round(p.Y / tol)),
        int(round(p.Z / tol))
    )


def points_close(p1, p2, tol):
    try:
        return p1.DistanceTo(p2) <= tol
    except:
        return False


def is_point_on_curve(curve, pt, tol):
    try:
        proj = curve.Project(pt)
        if proj is None:
            return False, None
        p = proj.XYZPoint
        return p.DistanceTo(pt) <= tol, p
    except:
        return False, None


def sort_points(curve, points):
    """Сортировка точек по расстоянию от начала кривой."""
    try:
        p0 = curve.GetEndPoint(0)
        return sorted(points, key=lambda p: p0.DistanceTo(p))
    except:
        return points
