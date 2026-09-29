# -*- coding: utf-8 -*-
"""
Положение элементов в снимке модели (json_snapshot): выгрузка координат и
поворота и обратная загрузка — перемещение, поворот, перенос марок.

"location" в записи элемента:
  - точечный элемент:  {"point_mm": [x, y, z], "rotation_deg": 90.0}
                       (rotation_deg — поворот вокруг вертикали, если он у
                       элемента есть);
  - линейный элемент:  {"start_mm": [...], "end_mm": [...]}; у дуги ещё
                       "shape": "arc" — её концы только для чтения;
  - марка (IndependentTag): {"tag_head_mm": [x, y, z]} — положение головы.
Координаты — в мм, в системе координат проекта (внутреннее начало Revit).

Защита от затирания — как у параметров: отпечаток положения на момент
выгрузки лежит в "h" под ключом LOCATION_KEY. Положение, которое в файле не
правили, не трогается; правка поверх перемещения в модели — конфликт.
"""

import math
from collections import OrderedDict

from Autodesk.Revit.DB import (
    ElementId, ElementTransformUtils, FilteredElementCollector, IndependentTag, Line,
    LocationCurve, LocationPoint, XYZ,
)

from lowlife.json_snapshot_common import (
    Change, category_name, fingerprint, mm_xyz, safe_name, xyz_mm,
)

LOCATION_KEY = u"@location"

_POINT_KEYS = ("point_mm", "start_mm", "end_mm", "tag_head_mm")
_TOL_FT = 1e-6


def _rotation_deg(loc):
    try:
        deg = math.degrees(loc.Rotation) % 360.0
    except Exception:
        return None
    deg = round(deg, 2)
    return 0.0 if deg >= 360.0 else deg


def location_record(el):
    u"""Положение элемента для снимка (OrderedDict) или None, если его нет."""
    if isinstance(el, IndependentTag):
        try:
            return OrderedDict([("tag_head_mm", xyz_mm(el.TagHeadPosition))])
        except Exception:
            return None
    try:
        loc = el.Location
    except Exception:
        return None
    try:
        if isinstance(loc, LocationPoint):
            rec = OrderedDict([("point_mm", xyz_mm(loc.Point))])
            rot = _rotation_deg(loc)
            if rot is not None:
                rec["rotation_deg"] = rot
            return rec
        if isinstance(loc, LocationCurve):
            c = loc.Curve
            rec = OrderedDict([("start_mm", xyz_mm(c.GetEndPoint(0))),
                               ("end_mm", xyz_mm(c.GetEndPoint(1)))])
            if not isinstance(c, Line):
                rec["shape"] = u"arc"
            return rec
    except Exception:
        pass
    return None


def location_text(loc):
    u"""
    Нормализованный текст положения — для сравнения и отпечатка: координаты
    с точностью 0.1 мм, поворот 0.01° в диапазоне [0, 360). Так «1000» и
    1000.04 от Claude не считаются правкой. ValueError, если не числа.
    """
    parts = []
    for key in _POINT_KEYS:
        if key in loc:
            vals = loc[key]
            if not isinstance(vals, (list, tuple)) or len(vals) != 3:
                raise ValueError(key)
            parts.append(key + u"=" + u",".join(u"%.1f" % _num(v) for v in vals))
    if "rotation_deg" in loc:
        r = round(_num(loc["rotation_deg"]) % 360.0, 2)
        if r >= 360.0:
            r = 0.0
        parts.append(u"rotation_deg=%.2f" % r)
    return u";".join(parts)


def _num(v):
    return float(unicode(v).replace(u",", u"."))


def _pt(vals):
    return u"({})".format(u", ".join(u"%.0f" % _num(v) for v in vals))


def _describe(loc):
    if "tag_head_mm" in loc:
        return _pt(loc["tag_head_mm"])
    if "point_mm" in loc:
        text = _pt(loc["point_mm"])
        if "rotation_deg" in loc:
            text += u" ∠%.1f°" % _num(loc["rotation_deg"])
        return text
    return u"{} — {}".format(_pt(loc["start_mm"]), _pt(loc["end_mm"]))


def _apply_location(doc, el, target):
    u"""Переместить/повернуть элемент в положение target. None или текст ошибки."""
    try:
        if el.Pinned:
            return u"элемент закреплён (pin)"
    except Exception:
        pass

    if isinstance(el, IndependentTag):
        el.TagHeadPosition = mm_xyz(target["tag_head_mm"])
        return None

    loc = el.Location
    if isinstance(loc, LocationPoint):
        new_pt = mm_xyz(target["point_mm"])
        delta = new_pt - loc.Point
        if delta.GetLength() > _TOL_FT:
            ElementTransformUtils.MoveElement(doc, el.Id, delta)
        if "rotation_deg" in target:
            loc = el.Location
            want = math.radians(_num(target["rotation_deg"]))
            d = want - loc.Rotation
            d = math.atan2(math.sin(d), math.cos(d))  # в (-π, π]
            if abs(d) > 1e-6:
                axis = Line.CreateBound(loc.Point, loc.Point + XYZ.BasisZ)
                ElementTransformUtils.RotateElement(doc, el.Id, axis, d)
        return None

    if isinstance(loc, LocationCurve):
        start = mm_xyz(target["start_mm"])
        end = mm_xyz(target["end_mm"])
        if start.DistanceTo(end) < 1.0 / 304.8:
            return u"начало и конец совпадают"
        loc.Curve = Line.CreateBound(start, end)
        return None

    return u"у элемента нет положения, которое можно изменить"


def plan_location(doc, el, rec, hashes, res):
    u"""
    Правка положения элемента по записи снимка или None. Считает в res
    unchanged / not_edited / bad_value так же, как правки параметров.
    """
    file_loc = rec.get("location")
    if not isinstance(file_loc, dict) or not file_loc:
        return None
    eid = el.Id.IntegerValue

    cur = location_record(el)
    if cur is None:
        res["bad_value"].append((eid, u"location", u"у элемента нет положения"))
        return None

    # берём из файла только ключи, которые у элемента есть; отсутствующие
    # в файле ключи (например удалённый rotation_deg) = без изменений
    target = OrderedDict(cur)
    for key in cur:
        if key in file_loc and key != "shape":
            target[key] = file_loc[key]

    try:
        cur_text = location_text(cur)
        new_text = location_text(target)
        mm_xyz(target.get("point_mm") or target.get("start_mm")
               or target.get("tag_head_mm"))
        if "end_mm" in target:
            mm_xyz(target["end_mm"])
    except Exception:
        res["bad_value"].append((eid, u"location", u"координаты — не числа"))
        return None

    if new_text == cur_text:
        res["unchanged"] += 1
        return None
    orig = hashes.get(LOCATION_KEY)
    if orig is not None and fingerprint(new_text) == orig:
        res["not_edited"] += 1
        return None
    if cur.get("shape") == u"arc":
        res["bad_value"].append((eid, u"location", u"дугу переместить нельзя"))
        return None

    conflict = orig is None or fingerprint(cur_text) != orig
    label = u"{} · ID {} · положение: {} → {}".format(
        category_name(el), eid, _describe(cur), _describe(target))
    return Change(label, lambda: _apply_location(doc, el, target), conflict)


# --- марки ------------------------------------------------------------------

def tagged_ids(tag):
    u"""Id (int) элементов текущего документа, которые марка маркирует."""
    try:
        return [i.IntegerValue for i in tag.GetTaggedLocalElementIds()]
    except Exception:
        pass
    try:
        return [tag.TaggedLocalElementId.IntegerValue]
    except Exception:
        return []


def collect_tags(doc, elements, view=None):
    u"""
    Марки (IndependentTag) выгружаемых элементов: на виде view, если задан,
    иначе на всех видах. Возвращает список марок, которых ещё нет в elements.
    """
    ids = set(el.Id.IntegerValue for el in elements)
    if view is not None:
        collector = FilteredElementCollector(doc, view.Id)
    else:
        collector = FilteredElementCollector(doc)
    out = []
    for tag in collector.OfClass(IndependentTag):
        if tag.Id.IntegerValue in ids:
            continue
        if any(i in ids for i in tagged_ids(tag)):
            out.append(tag)
            ids.add(tag.Id.IntegerValue)
    return out


def tag_info(doc, tag):
    u"""{"view": имя вида, "tagged": [UniqueId]} для записи марки."""
    uids = []
    for i in tagged_ids(tag):
        try:
            el = doc.GetElement(ElementId(i))
            if el is not None:
                uids.append(el.UniqueId)
        except Exception:
            pass
    view_name = u""
    try:
        view_name = safe_name(doc.GetElement(tag.OwnerViewId))
    except Exception:
        pass
    return OrderedDict([("view", view_name), ("tagged", uids)])
