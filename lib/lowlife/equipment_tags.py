# -*- coding: utf-8 -*-
"""
Марки оборудования (IndependentTag) на активном виде, разложенные ровно
и без пересечений — кнопка «Марки оборудования» (Tools.panel/TagEquipment).

Revit сам ставит марку прямо над/сбоку элемента, не глядя на соседей:
рядом стоящее оборудование даёт марки друг на друге. Здесь Revit-часть:
собрать элементы, поставить недостающие марки, измерить их габарит,
отдать всё в чистую раскладку ``tag_layout.layout`` и записать
результат — положение головы марки, конец и излом выноски.

Координаты: всё переводится в 2D-систему вида (u — ``RightDirection``,
v — ``UpDirection``, начало — ``view.Origin``), там же раскладывается,
и обратно в XYZ с сохранением «глубины» (координаты вдоль
``ViewDirection``) самой марки — поэтому работает и на планах, и на
разрезах/фасадах.

Выноска начинается от УГО, а не от семейства. УГО — это то, что
элемент реально рисует на ЭТОМ виде: геометрия ``get_Geometry`` с
``Options.View = view`` (вложенные аннотации, символьные линии —
отдельные кривые, не рёбра тела). Её габарит — «прямоугольник элемента»
для раскладки (на него не кладутся марки), центр — точка, куда смотрит
выноска, а конец выноски ставится на край этого габарита. Точка
вставки/габарит семейства целиком не годятся: УГО часто смещено от
точки вставки (к стене, к потолку) и меньше/больше 3D-тела. Если на виде
у элемента нет отдельных кривых — берётся вся его видимая геометрия, а
если и её нет — ``get_BoundingBox(view)``.

Конец выноски свободный (``LeaderEndCondition.Free``) — только так он
встаёт точно на край УГО, а излом — ровно по вертикали/горизонтали.
Минус: если потом подвинуть оборудование, конец выноски за ним не
поедет — перезапустите кнопку на этих элементах.

Совместимость с версиями Revit: API выносок марок поменялся в 2022
(много ссылок на одну марку — ``GetTaggedReferences``/``SetLeaderEnd``/
``SetLeaderElbow``), старые свойства ``LeaderEnd``/``LeaderElbow``/
``TaggedLocalElementId`` удалены в 2023. Пробуем новый путь, при
AttributeError — старый.
"""

from Autodesk.Revit.DB import (
    BuiltInCategory, CategoryType, Element, ElementId, Family,
    FamilyInstance, FamilySymbol, FilteredElementCollector, IndependentTag,
    LeaderEndCondition, Reference, TagMode, TagOrientation, TextNote, ViewType,
    XYZ, Options, GeometryInstance, Curve, Solid, PolyLine, Point
)
from Autodesk.Revit.UI.Selection import ISelectionFilter

import System

from lowlife import tag_layout

MM_TO_FT = 1.0 / 304.8

# Виды, на которых вообще можно ставить марки на элементы модели
# (3D — только заблокированный, не связываемся).
TAGGABLE_VIEW_TYPES = (
    ViewType.FloorPlan, ViewType.CeilingPlan, ViewType.EngineeringPlan,
    ViewType.AreaPlan, ViewType.Section, ViewType.Elevation, ViewType.Detail,
)


# ------------------------------------------------------------
# МЕЛОЧИ
# ------------------------------------------------------------

def id_int(eid):
    try:
        return eid.Value  # Revit 2024+
    except AttributeError:
        return eid.IntegerValue


def _safe_name(el):
    try:
        return Element.Name.GetValue(el)
    except Exception:
        return u""


def is_taggable_view(view):
    if view is None:
        return False
    try:
        if view.IsTemplate:
            return False
    except Exception:
        pass
    return view.ViewType in TAGGABLE_VIEW_TYPES


def is_equipment(el):
    """Экземпляр семейства модели (любая категория оборудования/устройств/
    обобщённых моделей) — то, на что ставим марку."""
    if not isinstance(el, FamilyInstance):
        return False
    cat = el.Category
    if cat is None:
        return False
    try:
        return cat.CategoryType == CategoryType.Model
    except Exception:
        return False


class EquipmentOrTagFilter(ISelectionFilter):
    """Выбор рамкой: оборудование и уже стоящие марки (марка = её элемент)."""

    def AllowElement(self, elem):
        return is_equipment(elem) or isinstance(elem, IndependentTag)

    def AllowReference(self, reference, position):
        return True


def tagged_local_ids(tag):
    """Id элементов текущего документа, на которые смотрит марка."""
    try:
        return [id_int(i) for i in tag.GetTaggedLocalElementIds()]  # 2022+
    except AttributeError:
        pass
    try:
        eid = tag.TaggedLocalElementId
        if eid is not None and eid != ElementId.InvalidElementId:
            return [id_int(eid)]
    except Exception:
        pass
    return []


def resolve_elements(doc, picked):
    """Выбранное → уникальный список оборудования (марки → их элементы)."""
    result = []
    seen = set()
    for el in picked:
        if isinstance(el, IndependentTag):
            targets = [doc.GetElement(ElementId(i)) for i in tagged_local_ids(el)]
        else:
            targets = [el]
        for t in targets:
            if t is None or not is_equipment(t):
                continue
            k = id_int(t.Id)
            if k in seen:
                continue
            seen.add(k)
            result.append(t)
    return result


def existing_tags_by_element(doc, view):
    """{id элемента: первая марка на этом виде, которая на него смотрит}."""
    result = {}
    for tag in FilteredElementCollector(doc, view.Id).OfClass(IndependentTag):
        for i in tagged_local_ids(tag):
            result.setdefault(i, tag)
    return result


# ------------------------------------------------------------
# ТИПЫ МАРОК ПО КАТЕГОРИИ
# ------------------------------------------------------------

def _builtin_category(cat):
    try:
        return cat.BuiltInCategory  # 2023+
    except AttributeError:
        pass
    try:
        return System.Enum.ToObject(BuiltInCategory, id_int(cat.Id))
    except Exception:
        return None


def tag_category_ids(cat):
    """Категории марок для категории элемента: «своя» (OST_XxxTags,
    с учётом единственного числа — OST_LightingFixtures → OST_LightingFixtureTags)
    и мультикатегорийная."""
    ids = []
    bic = _builtin_category(cat)
    if bic is not None:
        name = str(bic)
        names = [name + "Tags"]
        if name.endswith("s"):
            names.append(name[:-1] + "Tags")
        for n in names:
            tag_bic = getattr(BuiltInCategory, n, None)
            if tag_bic is not None:
                ids.append(id_int(ElementId(tag_bic)))
                break
    ids.append(id_int(ElementId(BuiltInCategory.OST_MultiCategoryTags)))
    return ids


def tag_types_for_category(doc, cat):
    """Все загруженные типоразмеры марок, которыми можно пометить элемент
    категории cat (через Family → GetFamilySymbolIds, чтобы не терять
    невставленные типы — см. CLAUDE.md). Своя категория — первой."""
    wanted = tag_category_ids(cat)
    by_cat = dict((c, []) for c in wanted)
    for fam in FilteredElementCollector(doc).OfClass(Family):
        fcat = fam.FamilyCategory
        if fcat is None:
            continue
        key = id_int(fcat.Id)
        if key not in by_cat:
            continue
        for sid in fam.GetFamilySymbolIds():
            sym = doc.GetElement(sid)
            if isinstance(sym, FamilySymbol):
                by_cat[key].append(sym)
    result = []
    for c in wanted:
        result.extend(sorted(by_cat[c], key=tag_type_label))
    return result


def tag_type_label(symbol):
    fam_name = u""
    try:
        fam_name = symbol.FamilyName
    except Exception:
        pass
    return u"{}: {}".format(fam_name, _safe_name(symbol))


def default_tag_type_id(doc, cat):
    """Типоразмер марки «по умолчанию» для категории (как у Revit при
    «Марка по категории»), либо None."""
    for c in tag_category_ids(cat)[:1]:
        try:
            tid = doc.GetDefaultFamilyTypeId(ElementId(c))
            if tid is not None and tid != ElementId.InvalidElementId:
                return tid
        except Exception:
            pass
    return None


# ------------------------------------------------------------
# 2D-СИСТЕМА ВИДА
# ------------------------------------------------------------

class ViewFrame(object):
    def __init__(self, view):
        self.o = view.Origin
        self.r = view.RightDirection
        self.u = view.UpDirection
        self.d = view.ViewDirection

    def uv(self, p):
        v = p - self.o
        return (v.DotProduct(self.r), v.DotProduct(self.u))

    def depth(self, p):
        return (p - self.o).DotProduct(self.d)

    def xyz(self, uv, depth):
        return (self.o + self.r.Multiply(uv[0]) + self.u.Multiply(uv[1]) +
                self.d.Multiply(depth))

    def rect(self, bbox):
        if bbox is None:
            return None
        mn, mx = bbox.Min, bbox.Max
        us, vs = [], []
        for x in (mn.X, mx.X):
            for y in (mn.Y, mx.Y):
                for z in (mn.Z, mx.Z):
                    u, v = self.uv(bbox.Transform.OfPoint(XYZ(x, y, z)))
                    us.append(u)
                    vs.append(v)
        return (min(us), min(vs), max(us), max(vs))

    def rect_of_points(self, points):
        if not points:
            return None
        us, vs = [], []
        for p in points:
            u, v = self.uv(p)
            us.append(u)
            vs.append(v)
        return (min(us), min(vs), max(us), max(vs))


# ------------------------------------------------------------
# УГО НА ВИДЕ
# ------------------------------------------------------------

def _walk_geometry(geom, curve_pts, body_pts):
    """Точки видимой на виде геометрии: отдельные кривые (УГО, символьные
    линии) — в curve_pts, тела/точки — в body_pts."""
    if geom is None:
        return
    for g in geom:
        try:
            if isinstance(g, GeometryInstance):
                _walk_geometry(g.GetInstanceGeometry(), curve_pts, body_pts)
            elif isinstance(g, Curve):
                curve_pts.extend(g.Tessellate())
            elif isinstance(g, PolyLine):
                curve_pts.extend(g.GetCoordinates())
            elif isinstance(g, Solid):
                for edge in g.Edges:
                    body_pts.extend(edge.Tessellate())
            elif isinstance(g, Point):
                body_pts.append(g.Coord)
        except Exception:
            continue


def symbol_rect(el, view, frame):
    """Габарит УГО элемента на виде (u0, v0, u1, v1) или None."""
    curve_pts, body_pts = [], []
    try:
        opts = Options()
        opts.View = view
        opts.ComputeReferences = False
        opts.IncludeNonVisibleObjects = False
        _walk_geometry(el.get_Geometry(opts), curve_pts, body_pts)
    except Exception:
        pass
    rect = frame.rect_of_points(curve_pts) or frame.rect_of_points(body_pts)
    if rect is None:
        rect = frame.rect(el.get_BoundingBox(view))
    return rect


# ------------------------------------------------------------
# ВЫНОСКИ
# ------------------------------------------------------------

def _set_leader(tag, ref, end, elbow):
    tag.HasLeader = True
    tag.LeaderEndCondition = LeaderEndCondition.Free
    try:
        tag.SetLeaderEnd(ref, end)  # 2022+
        tag.SetLeaderElbow(ref, elbow)
    except AttributeError:
        tag.LeaderEnd = end
        tag.LeaderElbow = elbow


def _tag_reference(tag, el):
    try:
        refs = list(tag.GetTaggedReferences())  # 2022+
        for r in refs:
            if r.ElementId == el.Id:
                return r
        if refs:
            return refs[0]
    except AttributeError:
        pass
    return Reference(el)


def _create_tag(doc, view, el, type_id, point):
    ref = Reference(el)
    if type_id is not None:
        sym = doc.GetElement(type_id)
        if sym is not None and not sym.IsActive:
            sym.Activate()
        return IndependentTag.Create(
            doc, type_id, view.Id, ref, False, TagOrientation.Horizontal, point
        )
    return IndependentTag.Create(
        doc, view.Id, ref, False, TagMode.TM_ADDBY_CATEGORY,
        TagOrientation.Horizontal, point
    )


# ------------------------------------------------------------
# ПРЕПЯТСТВИЯ
# ------------------------------------------------------------

def _obstacle_rects(doc, view, frame, own_ids, category_ids):
    """Прочее оборудование тех же категорий на виде + чужие марки и
    тексты — на них новые марки стараются не ставить."""
    rects = []
    for el in FilteredElementCollector(doc, view.Id).OfClass(FamilyInstance):
        if id_int(el.Id) in own_ids or el.Category is None:
            continue
        if id_int(el.Category.Id) not in category_ids:
            continue
        r = symbol_rect(el, view, frame)
        if r is not None:
            rects.append(r)
    for cls in (IndependentTag, TextNote):
        for el in FilteredElementCollector(doc, view.Id).OfClass(cls):
            if id_int(el.Id) in own_ids:
                continue
            r = frame.rect(el.get_BoundingBox(view))
            if r is not None:
                rects.append(r)
    return rects


# ------------------------------------------------------------
# ОСНОВНОЙ ПРОХОД
# ------------------------------------------------------------

def run(doc, view, elements, settings, type_by_category):
    """
    Ставит недостающие марки и раскладывает все марки элементов elements
    на view. type_by_category — {id категории элемента: ElementId типа
    марки или None («по категории», как Revit)}. Вызывать внутри
    транзакции. Возвращает словарь статистики.
    """
    stats = {"created": 0, "moved": 0, "no_bbox": 0, "failed": 0,
             "overlaps": 0, "crossings": 0}

    scale = float(view.Scale or 1)
    k = MM_TO_FT * scale
    offset = settings["offset_mm"] * k
    gap = settings["gap_mm"] * k
    shelf = settings["shelf_mm"] * k
    cluster_dist = settings["cluster_mm"] * k

    frame = ViewFrame(view)
    existing = existing_tags_by_element(doc, view)

    # 1. элементы с габаритом на виде; недостающие марки
    entries = []  # (el, tag, elem_rect, anchor)
    for el in elements:
        rect = symbol_rect(el, view, frame)
        if rect is None:
            stats["no_bbox"] += 1
            continue
        anchor = tag_layout.rect_center(rect)
        tag = existing.get(id_int(el.Id))
        if tag is None:
            try:
                bb = el.get_BoundingBox(view)
                depth = frame.depth(bb.Min) if bb is not None else 0.0
                tag = _create_tag(doc, view, el,
                                  type_by_category.get(id_int(el.Category.Id)),
                                  frame.xyz(anchor, depth))
                stats["created"] += 1
            except Exception:
                stats["failed"] += 1
                continue
        entries.append((el, tag, rect, anchor))

    if not entries:
        return stats

    # 2. габарит марок без выноски
    for _el, tag, _r, _a in entries:
        try:
            tag.HasLeader = False
        except Exception:
            pass
    doc.Regenerate()

    items = []
    info = {}
    for el, tag, rect, anchor in entries:
        trect = frame.rect(tag.get_BoundingBox(view))
        if trect is None:
            stats["failed"] += 1
            continue
        head = tag.TagHeadPosition
        hu, hv = frame.uv(head)
        cu, cv = tag_layout.rect_center(trect)
        key = id_int(el.Id)
        info[key] = (el, tag, (hu - cu, hv - cv), frame.depth(head))
        items.append(tag_layout.TagItem(
            key, anchor, rect,
            (tag_layout.rect_w(trect), tag_layout.rect_h(trect))
        ))

    # 3. раскладка
    own_ids = set(info.keys())
    for _k, (_el, tag, _o, _d) in info.items():
        own_ids.add(id_int(tag.Id))
    category_ids = set(id_int(el.Category.Id) for el, _t, _r, _a in entries)
    obstacles = _obstacle_rects(doc, view, frame, own_ids, category_ids)

    placements = tag_layout.layout(items, obstacles, offset=offset, gap=gap,
                                   shelf=shelf, cluster_dist=cluster_dist)
    stats["overlaps"], stats["crossings"] = tag_layout.count_conflicts(placements, items, gap)

    # 4. запись
    for p in placements:
        el, tag, (ou, ov), depth = info[p.key]
        cu, cv = tag_layout.rect_center(p.tag_rect)
        try:
            tag.TagHeadPosition = frame.xyz((cu + ou, cv + ov), depth)
            _set_leader(tag, _tag_reference(tag, el),
                        frame.xyz(p.end, depth), frame.xyz(p.elbow, depth))
            stats["moved"] += 1
        except Exception:
            stats["failed"] += 1

    return stats
