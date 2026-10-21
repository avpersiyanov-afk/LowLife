# -*- coding: utf-8 -*-
u"""
Элементы модели и загруженных связей «в одном списке» — для кнопок, которым
всё равно, где лежит элемент (Tools.panel/ZoomToElement «Зум к элементу»).

Элемент описывается `Item`: сам элемент, его документ и экземпляр связи
(None — элемент активной модели). Координаты элемента связи переводятся в
координаты модели через `link.GetTotalTransform()`.

Выбор элементов связей (через Tab или «Выбрать элементы связей») Revit
отдаёт только через `Selection.GetReferences()` (Revit 2023+); в
`GetElementIds()` попадает лишь сам экземпляр связи.

Видимость элемента связи на виде — `FilteredElementCollector(doc, view.Id,
link.Id)` (Revit 2024+), суженный до проверяемых элементов; в более старых версиях элемент связи считается
видимым, если не скрыт сам экземпляр связи.
"""

from Autodesk.Revit.DB import (
    BuiltInParameter, Element, ElementId, ElementIdSetFilter,
    FilteredElementCollector, Level,
    LocationCurve, LocationPoint, Reference, RevitLinkInstance, Transform, XYZ,
)
from System.Collections.Generic import List

MM_IN_FOOT = 304.8

# Параметры, в которых у разных категорий лежит ссылка на уровень элемента —
# перебираем по очереди, если у элемента нет прямого свойства LevelId.
LEVEL_BIPS = (
    BuiltInParameter.FAMILY_LEVEL_PARAM,
    BuiltInParameter.SCHEDULE_LEVEL_PARAM,
    BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM,
    BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM,
    BuiltInParameter.FAMILY_BASE_LEVEL_PARAM,
    BuiltInParameter.RBS_START_LEVEL_PARAM,
    BuiltInParameter.LEVEL_PARAM,
)


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


class Item(object):
    u"""Элемент модели (link=None) или элемент связи `link`."""

    def __init__(self, element, doc, link=None):
        self.element = element
        self.doc = doc
        self.link = link

    @property
    def is_linked(self):
        return self.link is not None

    @property
    def transform(self):
        if self.link is None:
            return Transform.Identity
        try:
            return self.link.GetTotalTransform()
        except Exception:
            return Transform.Identity

    @property
    def link_name(self):
        return _safe_name(self.link) if self.link is not None else u""

    def to_host(self, point):
        return self.transform.OfPoint(point) if point is not None else None

    def reference(self):
        u"""Reference для Selection.SetReferences (для связи — ссылка через связь)."""
        ref = Reference(self.element)
        if self.link is not None:
            ref = ref.CreateLinkReference(self.link)
        return ref

    def label(self):
        u"""Подпись для списка выбора: категория, имя, источник."""
        el = self.element
        try:
            cat = el.Category.Name if el.Category is not None else u""
        except Exception:
            cat = u""
        name = _safe_name(el)
        what = u" — ".join(x for x in (cat, name) if x) or u"Элемент"
        where = (u"связь «{}»".format(self.link_name) if self.link is not None
                 else u"текущая модель")
        return u"{} (ID {}, {})".format(what, _id_int(el.Id), where)


def loaded_links(doc):
    u"""Экземпляры связей с загруженным документом."""
    result = []
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        try:
            if link.GetLinkDocument() is not None:
                result.append(link)
        except Exception:
            pass
    return result


def selected_items(uidoc):
    u"""Выбранные элементы модели и (Revit 2023+) элементы связей."""
    doc = uidoc.Document
    items = []
    seen = set()

    def add(el, el_doc, link):
        if el is None:
            return
        key = (_id_int(link.Id) if link is not None else None, _id_int(el.Id))
        if key in seen:
            return
        seen.add(key)
        items.append(Item(el, el_doc, link))

    linked_refs = []
    try:
        refs = list(uidoc.Selection.GetReferences())
    except Exception:
        refs = []
    for ref in refs:
        try:
            if ref.LinkedElementId != ElementId.InvalidElementId:
                linked_refs.append(ref)
        except Exception:
            pass

    # Экземпляр связи, через который выбран её элемент, сам по себе тоже
    # оказывается в GetElementIds — его пропускаем, зумируем к элементу.
    links_via_refs = set(_id_int(r.ElementId) for r in linked_refs)
    for eid in uidoc.Selection.GetElementIds():
        if _id_int(eid) in links_via_refs:
            continue
        add(doc.GetElement(eid), doc, None)

    for ref in linked_refs:
        link = doc.GetElement(ref.ElementId)
        if not isinstance(link, RevitLinkInstance):
            continue
        link_doc = link.GetLinkDocument()
        if link_doc is None:
            continue
        add(link_doc.GetElement(ref.LinkedElementId), link_doc, link)
    return items


def find_by_id(doc, int_id):
    u"""Все элементы с этим ID: в модели и в каждой загруженной связи."""
    eid = ElementId(int_id)
    items = []
    el = doc.GetElement(eid)
    if el is not None:
        items.append(Item(el, doc, None))
    for link in loaded_links(doc):
        link_doc = link.GetLinkDocument()
        try:
            lel = link_doc.GetElement(eid)
        except Exception:
            lel = None
        if lel is not None and lel.Category is not None:
            items.append(Item(lel, link_doc, link))
    return items


def select_items(uidoc, items):
    u"""Выделяет элементы; элементы связей — через SetReferences (2023+)."""
    if not any(it.is_linked for it in items):
        ids = List[ElementId]()
        for it in items:
            ids.Add(it.element.Id)
        try:
            uidoc.Selection.SetElementIds(ids)
        except Exception:
            pass
        return
    refs = List[Reference]()
    for it in items:
        try:
            refs.Add(it.reference())
        except Exception:
            pass
    try:
        uidoc.Selection.SetReferences(refs)
    except Exception:
        pass


class Visibility(object):
    u"""
    Видим ли элемент на виде: показывает ли его Revit на этом виде
    (FilteredElementCollector по Id вида учитывает видимость категорий,
    фильтры, диапазон вида, скрытые элементы; для связи — через link.Id,
    Revit 2024+).

    Собираются не все элементы вида, а только проверяемые: сбор сужается
    ElementIdSetFilter — быстрым фильтром, который Revit применяет до
    проверки видимости, поэтому на большом виде или большой связи
    проверка стоит столько же, сколько на маленьких. Элементы группируются
    по источнику (модель/связь) — по одному сбору на источник.
    """

    def __init__(self, doc, view, items):
        self.doc = doc
        self.view = view
        self._ids = {}
        by_source = {}
        for it in items:
            key = _id_int(it.link.Id) if it.link is not None else None
            by_source.setdefault(key, (it.link, []))[1].append(it.element.Id)
        for key, (link, el_ids) in by_source.items():
            self._ids[key] = self._collect(link, el_ids)

    def _collect(self, link, el_ids):
        ids = List[ElementId]()
        for eid in el_ids:
            ids.Add(eid)
        try:
            if link is None:
                col = FilteredElementCollector(self.doc, self.view.Id)
            else:
                col = FilteredElementCollector(self.doc, self.view.Id, link.Id)
            return set(_id_int(x) for x in
                       col.WherePasses(ElementIdSetFilter(ids)).ToElementIds())
        except Exception:
            return None

    def _visible_ids(self, item):
        key = _id_int(item.link.Id) if item.link is not None else None
        if key not in self._ids:
            self._ids[key] = self._collect(item.link, [item.element.Id])
        return self._ids[key]

    def is_visible(self, item):
        ids = self._visible_ids(item)
        if ids is not None and _id_int(item.element.Id) in ids:
            return True
        if item.link is None:
            # У части семейств (символьных) элемента нет в сборе по виду,
            # но габарит на виде есть.
            try:
                return item.element.get_BoundingBox(self.view) is not None
            except Exception:
                return False
        if ids is not None:
            return False
        # Revit < 2024: судим по самой связи.
        try:
            return not item.link.IsHidden(self.view)
        except Exception:
            return True


def _bbox_center(bb):
    u"""Центр габарита с учётом собственного Transform контейнера."""
    mid = XYZ((bb.Min.X + bb.Max.X) / 2.0,
              (bb.Min.Y + bb.Max.Y) / 2.0,
              (bb.Min.Z + bb.Max.Z) / 2.0)
    try:
        return bb.Transform.OfPoint(mid)
    except Exception:
        return mid


def target_point(item, view):
    u"""
    Точка элемента в координатах модели для зума, или None.

    Приоритет: точка расположения (LocationPoint) -> середина оси
    (LocationCurve) -> центр габарита (на активном виде — только для
    элемента модели, иначе модельного).
    """
    el = item.element
    loc = getattr(el, "Location", None)
    if isinstance(loc, LocationPoint):
        try:
            return item.to_host(loc.Point)
        except Exception:
            pass
    elif isinstance(loc, LocationCurve):
        try:
            return item.to_host(loc.Curve.Evaluate(0.5, True))
        except Exception:
            pass

    for v in ((view, None) if not item.is_linked else (None,)):
        try:
            bb = el.get_BoundingBox(v)
        except Exception:
            bb = None
        if bb is not None:
            return item.to_host(_bbox_center(bb))
    return None


def _model_center_z(item):
    try:
        bb = item.element.get_BoundingBox(None)
    except Exception:
        bb = None
    if bb is None:
        return None
    return item.to_host(_bbox_center(bb)).Z


def level_name(item):
    u"""Имя уровня элемента (в его документе): LevelId -> параметры -> ближайший по Z."""
    el, doc = item.element, item.doc
    try:
        lid = el.LevelId
        if lid is not None and lid != ElementId.InvalidElementId:
            lvl = doc.GetElement(lid)
            if lvl is not None:
                return lvl.Name
    except Exception:
        pass

    for bip in LEVEL_BIPS:
        try:
            p = el.get_Parameter(bip)
            if p and p.HasValue:
                lvl = doc.GetElement(p.AsElementId())
                if lvl is not None:
                    return lvl.Name
        except Exception:
            pass

    # Ближайший уровень по средней отметке габарита (в координатах документа
    # элемента — там же и его уровни).
    try:
        bb = el.get_BoundingBox(None)
        if bb is not None:
            z = (bb.Min.Z + bb.Max.Z) / 2.0
            levels = list(FilteredElementCollector(doc).OfClass(Level))
            if levels:
                return min(levels, key=lambda L: abs(L.Elevation - z)).Name
    except Exception:
        pass
    return None


def elevation_m(item):
    u"""Отметка середины габарита в координатах модели, м, или None."""
    z = _model_center_z(item)
    return z * MM_IN_FOOT / 1000.0 if z is not None else None
