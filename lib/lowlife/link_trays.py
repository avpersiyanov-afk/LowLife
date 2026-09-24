# -*- coding: utf-8 -*-
u"""
Кабельные лотки из связанных моделей, видимые на активном виде, —
кнопка Tools.panel/LinkTraysToExcel («Лотки связи в Эксель»).

Видимость на виде:
  * Revit 2024+ — FilteredElementCollector(doc, view.Id, link.Id): Revit сам
    отдаёт элементы связи, видимые на виде хоста (с учётом подрезки,
    диапазона вида, фильтров).
  * Старее — запасной вариант: габарит вида (подрезка плана + диапазон вида,
    либо 3D-подрезка) переводится в координаты связи и фильтруется
    BoundingBoxIntersectsFilter. Без подрезки берутся все лотки связи.
"""

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, BoundingBoxIntersectsFilter, Element,
    ElementId, FilteredElementCollector, Outline, PlanViewPlane,
    RevitLinkInstance, View3D, ViewPlan, XYZ,
)

FT_TO_MM = 304.8
_BIG = 1.0e6  # футов — «бесконечность» для неограниченного диапазона вида

HEADER = [
    u"ID", u"Имя типа", u"Модель", u"Отметка (середина), мм",
    u"Базовый уровень", u"Связь",
]
COL_WIDTHS = [12, 40, 30, 22, 28, 40]


def _id_int(eid):
    try:
        return eid.Value  # Revit 2024+
    except Exception:
        return eid.IntegerValue


def _safe_name(el):
    if el is None:
        return u""
    try:
        return Element.Name.GetValue(el) or u""
    except Exception:
        try:
            return el.Name or u""
        except Exception:
            return u""


def visible_links(doc, view):
    u"""Загруженные экземпляры связей, не скрытые на виде."""
    result = []
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        if link.GetLinkDocument() is None:
            continue
        try:
            if link.IsHidden(view):
                continue
        except Exception:
            pass
        result.append(link)
    return result


def link_label(link):
    return _safe_name(link)


# --- запасной вариант (Revit < 2024) -----------------------------------------

def _box_corners(bbox):
    t = bbox.Transform
    mn, mx = bbox.Min, bbox.Max
    pts = []
    for x in (mn.X, mx.X):
        for y in (mn.Y, mx.Y):
            for z in (mn.Z, mx.Z):
                pts.append(t.OfPoint(XYZ(x, y, z)))
    return pts


def _plane_z(doc, view_range, plane, default):
    lvl_id = view_range.GetLevelId(plane)
    if lvl_id is None or lvl_id == ElementId.InvalidElementId:
        return default
    lvl = doc.GetElement(lvl_id)
    if lvl is None:
        return default
    return lvl.Elevation + view_range.GetOffset(plane)


def _view_world_points(doc, view):
    u"""Точки-габарит вида в координатах модели хоста или None (весь объём)."""
    if isinstance(view, View3D):
        try:
            if view.IsSectionBoxActive:
                return _box_corners(view.GetSectionBox())
        except Exception:
            pass
        return None

    if isinstance(view, ViewPlan):
        vr = view.GetViewRange()
        z_lo = _plane_z(doc, vr, PlanViewPlane.ViewDepthPlane, -_BIG)
        z_lo = min(z_lo, _plane_z(doc, vr, PlanViewPlane.BottomClipPlane, -_BIG))
        z_hi = _plane_z(doc, vr, PlanViewPlane.TopClipPlane, _BIG)
        if view.CropBoxActive:
            xy = _box_corners(view.CropBox)
            xs = [p.X for p in xy]
            ys = [p.Y for p in xy]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        else:
            x0, x1, y0, y1 = -_BIG, _BIG, -_BIG, _BIG
        return [XYZ(x, y, z) for x in (x0, x1) for y in (y0, y1)
                for z in (z_lo, z_hi)]

    try:
        if view.CropBoxActive:
            return _box_corners(view.CropBox)
    except Exception:
        pass
    return None


def _fallback_collect(doc, view, link):
    link_doc = link.GetLinkDocument()
    col = (FilteredElementCollector(link_doc)
           .OfCategory(BuiltInCategory.OST_CableTray)
           .WhereElementIsNotElementType())
    pts = _view_world_points(doc, view)
    if pts is None:
        return list(col)
    inv = link.GetTotalTransform().Inverse
    local = [inv.OfPoint(p) for p in pts]
    mn = XYZ(min(p.X for p in local), min(p.Y for p in local),
             min(p.Z for p in local))
    mx = XYZ(max(p.X for p in local), max(p.Y for p in local),
             max(p.Z for p in local))
    return list(col.WherePasses(BoundingBoxIntersectsFilter(Outline(mn, mx))))


def collect_trays(doc, view, link):
    u"""(лотки связи, видимые на виде; True, если использован запасной способ)."""
    try:
        col = FilteredElementCollector(doc, view.Id, link.Id)
    except Exception:
        return _fallback_collect(doc, view, link), True
    trays = list(col.OfCategory(BuiltInCategory.OST_CableTray)
                 .WhereElementIsNotElementType())
    return trays, False


# --- строки таблицы -----------------------------------------------------------

def _param(el, bip):
    try:
        p = el.get_Parameter(bip)
    except Exception:
        return None
    if p is None or not p.HasValue:
        return None
    return p


def _model(tray, tray_type):
    for el in (tray, tray_type):
        if el is None:
            continue
        p = _param(el, BuiltInParameter.ALL_MODEL_MODEL)
        if p is not None and p.AsString():
            return p.AsString()
    return u""


def _elevation_mm(tray):
    p = _param(tray, BuiltInParameter.RBS_OFFSET_PARAM)
    if p is None:
        return None
    return round(p.AsDouble() * FT_TO_MM, 1)


def _base_level(link_doc, tray):
    lvl = None
    p = _param(tray, BuiltInParameter.RBS_START_LEVEL_PARAM)
    if p is not None:
        lvl = link_doc.GetElement(p.AsElementId())
    if lvl is None:
        try:
            lvl = tray.ReferenceLevel
        except Exception:
            lvl = None
    return _safe_name(lvl)


def tray_row(link_doc, tray, link_name):
    tray_type = link_doc.GetElement(tray.GetTypeId())
    return [
        _id_int(tray.Id),
        _safe_name(tray_type),
        _model(tray, tray_type),
        _elevation_mm(tray),
        _base_level(link_doc, tray),
        link_name,
    ]


def build_rows(doc, view, links):
    u"""(строки с заголовком, {имя связи: число лотков}, был ли запасной способ)."""
    rows = [list(HEADER)]
    counts = []
    used_fallback = False
    for link in links:
        link_doc = link.GetLinkDocument()
        name = link_label(link)
        trays, fb = collect_trays(doc, view, link)
        used_fallback = used_fallback or fb
        body = [tray_row(link_doc, t, name) for t in trays]
        body.sort(key=lambda r: (r[4], r[1], r[0]))
        rows.extend(body)
        counts.append((name, len(body)))
    return rows, counts, used_fallback
