# -*- coding: utf-8 -*-
"""
Создание новых элементов из снимка модели (json_snapshot): раздел "new"
файла и каталог загруженных типоразмеров ("catalog"), из которого их
выбирать.

Запись в "new":
  {
    "family": "…", "type": "…",   — какой типоразмер поставить, ИЛИ
    "copy_of": "<uid>",           — скопировать существующий элемент (для
                                    семейств на основе грани/рабочей
                                    плоскости, которые по точке не ставятся:
                                    копия сохраняет основу/плоскость);
                                    вместе с "type" — копия с заменой типа
                                    (в пределах того же семейства);
    "host": "<uid>",              — необязательно: основа (стена/потолок
                                    текущей модели) для семейств на основе;
    "level": "Этаж 01",           — необязательно: иначе ближайший снизу по Z;
    "point_mm": [x, y, z],        — точка вставки, координаты как в "location";
    "rotation_deg": 0,            — необязательно: поворот вокруг вертикали;
    "params": {"…": "…"}          — необязательно: значения параметров
  }

Вставка: create_companion_instance (companion_placement) — первое, что
примет Revit: с основой и уровнем, с основой, по уровню, без привязки;
затем элемент сдвигается точно в point_mm и поворачивается (так высота не
зависит от того, как семейство трактует Z точки вставки).

Повторная загрузка того же файла дублей не плодит: если в пределах
DEDUPE_RADIUS_MM от точки уже стоит экземпляр того же типоразмера,
запись пропускается (попадает в отчёт как «уже есть»).
"""

from collections import OrderedDict

from Autodesk.Revit.DB import (
    ElementTransformUtils, Family, FamilyInstance, FilteredElementCollector,
    LocationPoint,
)

from lowlife.companion_placement import create_companion_instance
from lowlife.geometry import find_level_for_elevation, get_document_levels
from lowlife.json_snapshot_common import (
    Change, MM_IN_FOOT, Partial, category_name, mm_xyz, safe_name,
)
from lowlife import json_snapshot_geometry as geometry
from lowlife.params import set_param_text

DEDUPE_RADIUS_MM = 10.0
_DEDUPE_FT = DEDUPE_RADIUS_MM / MM_IN_FOOT


def _key(family, type_name):
    return (unicode(family or u"").strip().lower(), unicode(type_name or u"").strip().lower())


def _families(doc):
    u"""Загруженные семейства (через Family -> GetFamilySymbolIds: так видны и
    ещё не расставленные типоразмеры, см. CLAUDE.md)."""
    return list(FilteredElementCollector(doc).OfClass(Family))


def _instance_stats(doc):
    u"""{id типоразмера: (число экземпляров, UniqueId первого)}."""
    stats = {}
    for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
        try:
            sid = fi.Symbol.Id.IntegerValue
        except Exception:
            continue
        n, uid = stats.get(sid, (0, None))
        stats[sid] = (n + 1, uid or fi.UniqueId)
    return stats


def catalog_section(doc, category_names):
    u"""
    Каталог загруженных типоразмеров семейств выбранных категорий (пусто —
    всех): категория, семейство, тип, способ размещения, сколько уже
    расставлено и пример экземпляра (для "copy_of").
    """
    cats = set(category_names or [])
    stats = _instance_stats(doc)
    out = []
    for fam in _families(doc):
        try:
            cat = fam.FamilyCategory.Name if fam.FamilyCategory is not None else u""
        except Exception:
            cat = u""
        if cats and cat not in cats:
            continue
        try:
            placement = unicode(fam.FamilyPlacementType)
        except Exception:
            placement = u""
        fam_name = safe_name(fam)
        for sid in fam.GetFamilySymbolIds():
            sym = doc.GetElement(sid)
            if sym is None:
                continue
            n, uid = stats.get(sid.IntegerValue, (0, None))
            rec = OrderedDict([
                ("category", cat),
                ("family", fam_name),
                ("type", safe_name(sym)),
                ("placement", placement),
                ("instances", n),
            ])
            if uid:
                rec["example_uid"] = uid
            out.append(rec)
    out.sort(key=lambda r: (r["category"], r["family"], r["type"]))
    return out


class _Context(object):
    u"""То, что нужно всем записям "new" разом — собирается один раз."""

    def __init__(self, doc):
        self.doc = doc
        self.symbols = {}
        for fam in _families(doc):
            fam_name = safe_name(fam)
            for sid in fam.GetFamilySymbolIds():
                sym = doc.GetElement(sid)
                if sym is not None:
                    self.symbols[_key(fam_name, safe_name(sym))] = sym
        self.levels = get_document_levels(doc)
        self.levels_by_name = dict((safe_name(lv).strip().lower(), lv)
                                   for lv in self.levels)
        # точки уже стоящих экземпляров по типоразмеру — для отсева дублей;
        # пополняется и созданными в этой же загрузке
        self.points = {}
        for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
            try:
                loc = fi.Location
                if isinstance(loc, LocationPoint):
                    self.points.setdefault(fi.Symbol.Id.IntegerValue, []).append(loc.Point)
            except Exception:
                pass

    def exists_near(self, symbol, point):
        for p in self.points.get(symbol.Id.IntegerValue, []):
            if p.DistanceTo(point) <= _DEDUPE_FT:
                return True
        return False


def _level_for(ctx, item, point):
    name = item.get("level")
    if name:
        level = ctx.levels_by_name.get(unicode(name).strip().lower())
        if level is None:
            raise ValueError(u"нет уровня «{}»".format(name))
        return level
    return find_level_for_elevation(point.Z, ctx.levels)


def _symbol_for(ctx, item, source=None):
    fam = item.get("family")
    typ = item.get("type")
    if source is not None:
        if not typ:
            return source.Symbol
        fam = fam or source.Symbol.FamilyName
    if not fam or not typ:
        raise ValueError(u"нужны \"family\" и \"type\" (или \"copy_of\")")
    sym = ctx.symbols.get(_key(fam, typ))
    if sym is None:
        raise ValueError(u"нет загруженного типоразмера «{} / {}»".format(fam, typ))
    return sym


def _set_params(el, params):
    u"""Записать "params" новому элементу; список не записавшихся имён."""
    failed = []
    for name, raw in (params or {}).items():
        try:
            p = el.LookupParameter(name)
        except Exception:
            p = None
        if raw is None:
            continue
        text = raw if isinstance(raw, basestring) else (
            (u"Да" if raw else u"Нет") if isinstance(raw, bool) else unicode(raw))
        if p is None or p.IsReadOnly or not set_param_text(p, unicode(text)):
            failed.append(name)
    return failed


def _create(ctx, item, symbol, point, level, source, host):
    doc = ctx.doc
    if source is not None:
        delta = point - source.Location.Point
        ids = list(ElementTransformUtils.CopyElement(doc, source.Id, delta))
        if not ids:
            return u"Revit не скопировал элемент"
        el = doc.GetElement(ids[0])
        if el.GetTypeId().IntegerValue != symbol.Id.IntegerValue:
            el.ChangeTypeId(symbol.Id)
    else:
        el = create_companion_instance(doc, symbol, point, host, level)
        if el is None:
            return (u"Revit не принял вставку этого семейства ({}) — для "
                    u"семейств на основе грани используйте \"copy_of\""
                    .format(unicode(symbol.Family.FamilyPlacementType)))
    doc.Regenerate()

    target = OrderedDict([("point_mm", item["point_mm"])])
    if item.get("rotation_deg") is not None:
        target["rotation_deg"] = item["rotation_deg"]
    problems = []
    if isinstance(el.Location, LocationPoint):
        try:
            err = geometry.apply_location(doc, el, target)
        except Exception as exc:
            # элемент уже создан — не выдаём это за провал всей записи
            err = unicode(exc) or exc.__class__.__name__
        if err:
            problems.append(u"положение: " + err)
    failed = _set_params(el, item.get("params"))
    if failed:
        problems.append(u"не записаны параметры: " + u", ".join(failed))
    if problems:
        return Partial(u"создан (ID {}), но {}".format(
            el.Id.IntegerValue, u"; ".join(problems)))
    return None


def plan_new(doc, items, res):
    u"""
    Правки-создания по разделу "new" (список Change). Ошибки записей — в
    res["bad_value"] как ("new[i]", что, причина); дубли — в res["exists"].
    """
    if not isinstance(items, list) or not items:
        return []
    ctx = _Context(doc)
    out = []
    for i, item in enumerate(items):
        tag = u"new[{}]".format(i)
        if not isinstance(item, dict):
            res["bad_value"].append((tag, u"", u"не объект"))
            continue
        try:
            point = mm_xyz(item.get("point_mm"))
            source = None
            if item.get("copy_of"):
                source = doc.GetElement(unicode(item["copy_of"]))
                if source is None or not isinstance(getattr(source, "Location", None), LocationPoint) \
                        or not isinstance(source, FamilyInstance):
                    raise ValueError(u"\"copy_of\": нет такого точечного экземпляра семейства")
            symbol = _symbol_for(ctx, item, source)
            level = _level_for(ctx, item, point)
            host = None
            if item.get("host"):
                host = doc.GetElement(unicode(item["host"]))
                if host is None:
                    raise ValueError(u"\"host\": нет такого элемента")
            if item.get("rotation_deg") is not None:
                float(unicode(item["rotation_deg"]).replace(u",", u"."))
        except Exception as exc:
            what = u"{} / {}".format(item.get("family") or u"", item.get("type") or u"")
            res["bad_value"].append((tag, what, unicode(exc)))
            continue

        if ctx.exists_near(symbol, point):
            res["exists"].append(tag)
            continue
        # две одинаковые записи в самом файле — вторую тоже считаем дублем
        ctx.points.setdefault(symbol.Id.IntegerValue, []).append(point)

        label = u"＋ создать · {} · {} / {} · {} · ({})".format(
            category_name(symbol), symbol.FamilyName, safe_name(symbol),
            safe_name(level) if level is not None else u"без уровня",
            u", ".join(u"%.0f" % (c * MM_IN_FOOT) for c in (point.X, point.Y, point.Z)))
        if source is not None:
            label += u" · копия ID {}".format(source.Id.IntegerValue)
        out.append(Change(
            label,
            lambda item=item, symbol=symbol, point=point, level=level,
            source=source, host=host: _create(ctx, item, symbol, point, level, source, host)))
    return out
