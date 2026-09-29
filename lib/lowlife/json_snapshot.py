# -*- coding: utf-8 -*-
"""
Снимок модели в JSON и обратная загрузка правок из него в модель
(кнопки ToolsSchedules.panel/ModelToJson и JsonToModel).

Зачем: снимок можно отдать Claude (или любому другому инструменту) —
проанализировать модель, найти ошибки, предложить правки, — а изменённый
файл загрузить обратно. Модель при этом меняется только кнопкой загрузки,
после предпросмотра «было → станет», одной транзакцией (Ctrl+Z отменяет).

Формат (version 1) — см. README_LINES ниже, они же пишутся в сам файл,
чтобы тот, кто его правит, знал правила без этой документации:
  - "params"      — записываемые параметры экземпляра, ЕДИНСТВЕННОЕ, что
                    загрузка переносит обратно в модель;
  - "readonly"    — только чтение (вычисляемые, ссылки на элементы) — для
                    анализа, на загрузке игнорируется;
  - "type_params" — параметры типа, тоже только для анализа (изменение
                    параметра типа меняет все экземпляры — через этот
                    сценарий намеренно не делается);
  - "circuit"     — у электрических цепей: панель и элементы цепи (UniqueId);
  - "uid"/"id"    — ключ связи с элементом (сначала UniqueId, запасной — Id);
  - "h"           — отпечатки значений "params" на момент выгрузки, по
                    параметру. На загрузке по ним видно, что именно правили
                    в файле (значение ≠ отпечатку), а что меняли в модели
                    после выгрузки (модель ≠ отпечатку). Нетронутые в файле
                    значения не пишутся вовсе — иначе они откатили бы
                    чужие изменения модели; правка поверх изменения модели
                    — конфликт (по умолчанию не отмечен), чтобы не затереть
                    чужую работу молча.

Значения — текст «как видно в Revit» (params.param_to_text / set_param_text,
та же пара, что у обмена спецификаций с Excel): числа — в единицах проекта,
«Да/Нет» — да/нет.
"""

import datetime
import hashlib
import io
import json
from collections import OrderedDict

from Autodesk.Revit.DB import (
    BuiltInCategory, CategoryType, Element, ElementId, FilteredElementCollector,
    LocationCurve, LocationPoint, StorageType,
)
from Autodesk.Revit.DB.Electrical import ElectricalSystem

from lowlife.geometry import get_element_level
from lowlife.params import param_to_text, set_param_text

FORMAT = u"lowlife-snapshot"
VERSION = 1

SCOPE_VIEW = "view"
SCOPE_SELECTION = "selection"
SCOPE_ALL = "all"

_MM_IN_FOOT = 304.8
# StorageType.None — «None» в Python 2 ключевое слово, через точку не достать
_STORAGE_NONE = getattr(StorageType, "None")

README_LINES = [
    u"Снимок модели Revit, выгружен кнопкой LowLife «Модель → JSON».",
    u"Обратно в модель загружается ТОЛЬКО содержимое \"params\" у элементов "
    u"(кнопка «JSON → модель», с предпросмотром перед записью).",
    u"Можно менять значения в \"params\" и добавлять туда ключи — имена "
    u"существующих параметров экземпляра этого элемента.",
    u"Значения — текст, как в Revit: числа в единицах проекта (\"1500\"), "
    u"«Да/Нет» — \"Да\"/\"Нет\". Пустая строка очищает текстовый параметр.",
    u"Удаление ключа из \"params\" ничего не меняет в модели.",
    u"\"readonly\", \"type_params\", \"circuit\", \"level\", \"location\" и "
    u"прочие поля — только для анализа, их правки игнорируются.",
    u"Не менять \"uid\", \"id\" и \"h\" — по ним загрузка находит элемент и "
    u"отличает правки в файле от изменений модели после выгрузки.",
    u"Новые элементы в \"elements\" не создаются, удалённые из файла — не "
    u"удаляются из модели.",
]


def _bic_ids(*names):
    ids = set()
    for name in names:
        try:
            ids.add(int(getattr(BuiltInCategory, name)))
        except Exception:
            pass
    return ids


# Служебное, что попадает в коллектор, но данными модели не является.
# В отличие от selection.is_pickable_model_element, обобщённые модели и
# помещения НЕ отсекаются — маркеры трассы СКС/СКУД и помещения как раз
# нужны в снимке.
_JUNK_CATEGORY_IDS = _bic_ids(
    "OST_Grids", "OST_Levels", "OST_Lines", "OST_CLines", "OST_SketchLines",
    "OST_RvtLinks", "OST_SectionBox", "OST_Cameras", "OST_Viewers",
    "OST_ScopeBoxes", "OST_Views", "OST_Sheets", "OST_Viewports",
    "OST_ProjectInformation", "OST_Materials", "OST_IOSModelGroups",
    "OST_WeakDims", "OST_Constraints",
)
_CIRCUIT_CATEGORY_IDS = _bic_ids("OST_ElectricalCircuit")


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


def _category_name(el):
    try:
        cat = el.Category
        return cat.Name if cat is not None else u""
    except Exception:
        return u""


def _is_exportable(el, allow_annotation=False):
    try:
        if el.Document.IsLinked:
            return False
    except Exception:
        pass
    try:
        cat = el.Category
    except Exception:
        cat = None
    if cat is None:
        return False
    try:
        cid = cat.Id.IntegerValue
    except Exception:
        return False
    if cid in _JUNK_CATEGORY_IDS:
        return False
    if cid in _CIRCUIT_CATEGORY_IDS or allow_annotation:
        return True
    try:
        return cat.CategoryType == CategoryType.Model
    except Exception:
        return False


def _is_writable(p):
    try:
        if p.IsReadOnly:
            return False
        st = p.StorageType
        return st != StorageType.ElementId and st != _STORAGE_NONE
    except Exception:
        return False


def _instance_params(el):
    u"""[(имя, Parameter)] без дублей имён (первый встреченный — тот же, что
    найдёт загрузка), в порядке имён."""
    seen = {}
    try:
        for p in el.Parameters:
            try:
                seen.setdefault(p.Definition.Name, p)
            except Exception:
                pass
    except Exception:
        pass
    return sorted(seen.items(), key=lambda kv: kv[0].lower())


def _fingerprint(text):
    u"""Короткий отпечаток значения параметра (текстом, без краевых пробелов).
    Одинаково считается при выгрузке и при загрузке."""
    data = (text or u"").strip().encode("utf-8")
    return hashlib.md5(data).hexdigest()[:8]


# --- отбор элементов -------------------------------------------------------

def collect_elements(doc, uidoc, options):
    u"""
    Элементы для снимка по настройкам: область (активный вид / выделение /
    весь документ) и фильтр категорий по имени (пусто — все). Возвращает
    (список элементов, текст ошибки или None).
    """
    scope = options.get("scope") or SCOPE_VIEW
    cat_names = set(options.get("categories") or [])

    if scope == SCOPE_SELECTION:
        ids = list(uidoc.Selection.GetElementIds())
        if not ids:
            return [], (u"В настройках выбрана выгрузка выделенных элементов, "
                        u"а в Revit ничего не выделено.")
        raw = [doc.GetElement(i) for i in ids]
        allow_annotation = True
    elif scope == SCOPE_ALL:
        raw = (FilteredElementCollector(doc)
               .WhereElementIsNotElementType().ToElements())
        allow_annotation = False
    else:
        view = doc.ActiveView
        try:
            raw = (FilteredElementCollector(doc, view.Id)
                   .WhereElementIsNotElementType().ToElements())
        except Exception:
            return [], (u"Не удалось собрать элементы активного вида «{}». "
                        u"Откройте план/3D-вид или выберите в настройках "
                        u"другую область.".format(_safe_name(view)))
        allow_annotation = False

    out = []
    for el in raw:
        if el is None or not _is_exportable(el, allow_annotation):
            continue
        if cat_names and _category_name(el) not in cat_names:
            continue
        out.append(el)
    return out, None


def _circuit_members(system):
    members = []
    try:
        for m in system.Elements:
            members.append(m)
    except Exception:
        pass
    return members


def add_circuits(doc, elements):
    u"""
    Дополнить список электрическими цепями, в которые входят выгружаемые
    элементы (как устройство или как панель). Цепей на виде не видно,
    поэтому коллектор по виду их не находит — добираем отдельно.
    """
    ids = set(el.Id.IntegerValue for el in elements)
    extra = []
    for system in FilteredElementCollector(doc).OfClass(ElectricalSystem):
        if system.Id.IntegerValue in ids:
            continue
        related = False
        try:
            base = system.BaseEquipment
            related = base is not None and base.Id.IntegerValue in ids
        except Exception:
            pass
        if not related:
            related = any(m.Id.IntegerValue in ids for m in _circuit_members(system))
        if related:
            extra.append(system)
            ids.add(system.Id.IntegerValue)
    return list(elements) + extra


# --- выгрузка --------------------------------------------------------------

def _location(el):
    try:
        loc = el.Location
    except Exception:
        return None

    def mm(xyz):
        return [round(xyz.X * _MM_IN_FOOT, 1),
                round(xyz.Y * _MM_IN_FOOT, 1),
                round(xyz.Z * _MM_IN_FOOT, 1)]

    try:
        if isinstance(loc, LocationPoint):
            return OrderedDict([("point_mm", mm(loc.Point))])
        if isinstance(loc, LocationCurve):
            c = loc.Curve
            return OrderedDict([("start_mm", mm(c.GetEndPoint(0))),
                                ("end_mm", mm(c.GetEndPoint(1)))])
    except Exception:
        pass
    return None


def _circuit_info(system):
    try:
        base = system.BaseEquipment
    except Exception:
        base = None
    return OrderedDict([
        ("panel", base.UniqueId if base is not None else None),
        ("elements", [m.UniqueId for m in _circuit_members(system)]),
    ])


def element_record(doc, el, options):
    u"""Запись одного элемента снимка (OrderedDict — читаемый порядок ключей)."""
    param_filter = options.get("param_names") or None
    names = set(param_filter) if param_filter else None
    include_empty = bool(options.get("include_empty"))

    type_el = None
    try:
        type_el = doc.GetElement(el.GetTypeId())
    except Exception:
        pass

    rec = OrderedDict()
    rec["id"] = el.Id.IntegerValue
    rec["uid"] = el.UniqueId
    rec["category"] = _category_name(el)
    if type_el is not None:
        rec["family"] = getattr(type_el, "FamilyName", None) or u""
        rec["type"] = _safe_name(type_el)
    else:
        rec["name"] = _safe_name(el)
    try:
        level = get_element_level(doc, el)
    except Exception:
        level = None
    if level is not None:
        rec["level"] = _safe_name(level)

    if options.get("include_location"):
        loc = _location(el)
        if loc is not None:
            rec["location"] = loc

    params = OrderedDict()
    readonly = OrderedDict()
    for name, p in _instance_params(el):
        if names is not None and name not in names:
            continue
        text = param_to_text(p)
        if not text and not include_empty:
            continue
        if _is_writable(p):
            params[name] = text
        elif options.get("include_readonly"):
            readonly[name] = text
    rec["params"] = params
    if readonly:
        rec["readonly"] = readonly

    if options.get("include_type_params") and type_el is not None:
        tparams = OrderedDict()
        for name, p in _instance_params(type_el):
            if names is not None and name not in names:
                continue
            text = param_to_text(p)
            if text or include_empty:
                tparams[name] = text
        if tparams:
            rec["type_params"] = tparams

    if isinstance(el, ElectricalSystem):
        rec["circuit"] = _circuit_info(el)

    rec["h"] = OrderedDict((name, _fingerprint(text)) for name, text in params.items())
    return rec


def build_snapshot(doc, elements, options):
    u"""Весь снимок: шапка (документ, настройки выгрузки, правила) + элементы."""
    view_name = None
    if (options.get("scope") or SCOPE_VIEW) == SCOPE_VIEW:
        view_name = _safe_name(doc.ActiveView)
    settings_info = OrderedDict([
        ("scope", options.get("scope") or SCOPE_VIEW),
        ("view", view_name),
        ("categories", list(options.get("categories") or [])),
        ("param_filter", list(options.get("param_names") or []) or None),
        ("include_readonly", bool(options.get("include_readonly"))),
        ("include_type_params", bool(options.get("include_type_params"))),
        ("include_empty", bool(options.get("include_empty"))),
        ("include_circuits", bool(options.get("include_circuits"))),
        ("include_location", bool(options.get("include_location"))),
    ])
    return OrderedDict([
        ("format", FORMAT),
        ("version", VERSION),
        ("readme", README_LINES),
        ("document", OrderedDict([
            ("title", doc.Title),
            ("path", doc.PathName or u""),
        ])),
        ("exported_at", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ("settings", settings_info),
        ("elements", [element_record(doc, el, options) for el in elements]),
    ])


def write_snapshot(path, snapshot):
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(unicode(json.dumps(snapshot, ensure_ascii=False, indent=2)))


# --- подсказки для окна настроек ------------------------------------------

def list_model_category_names(doc):
    u"""Имена категорий, у которых в документе есть выгружаемые элементы."""
    names = set()
    for el in FilteredElementCollector(doc).WhereElementIsNotElementType():
        if _is_exportable(el):
            nm = _category_name(el)
            if nm:
                names.add(nm)
    return sorted(names, key=lambda s: s.lower())


def list_param_names(doc, category_names, per_category=200):
    u"""
    Имена параметров экземпляра у элементов выбранных категорий (пусто —
    всех). По каждой категории смотрим не больше per_category элементов:
    набор параметров у элементов одной категории почти всегда одинаков,
    а полный обход большой модели ради подсказки — лишнее ожидание.
    Возвращает [(имя, записываемый ли хоть у кого-то)].
    """
    cat_names = set(category_names or [])
    seen_per_cat = {}
    names = {}
    for el in FilteredElementCollector(doc).WhereElementIsNotElementType():
        if not _is_exportable(el):
            continue
        cat = _category_name(el)
        if cat_names and cat not in cat_names:
            continue
        n = seen_per_cat.get(cat, 0)
        if n >= per_category:
            continue
        seen_per_cat[cat] = n + 1
        for name, p in _instance_params(el):
            names[name] = names.get(name, False) or _is_writable(p)
    return sorted(names.items(), key=lambda kv: kv[0].lower())


# --- загрузка --------------------------------------------------------------

def read_snapshot(path):
    u"""Прочитать файл снимка. Возвращает (data, текст ошибки или None)."""
    try:
        with io.open(path, "r", encoding="utf-8-sig") as f:
            data = json.loads(f.read())
    except Exception as exc:
        return None, u"Не удалось прочитать JSON:\n{}".format(exc)
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        return None, (u"Файл не похож на снимок LowLife (нет \"format\": "
                      u"\"{}\").".format(FORMAT))
    if not isinstance(data.get("elements"), list):
        return None, u"В файле нет списка \"elements\"."
    try:
        version = int(data.get("version") or 0)
    except Exception:
        version = 0
    if version > VERSION:
        return None, (u"Снимок сделан более новой версией LowLife (формат {}), "
                      u"обновите расширение.".format(version))
    return data, None


class Change(object):
    u"""Одна правка «параметр элемента: было → станет»."""

    def __init__(self, el, param, name, old, new, conflict):
        self.el = el
        self.param = param
        self.param_name = name
        self.old = old
        self.new = new
        self.conflict = conflict
        self.name = self._label()

    def _label(self):
        def short(s):
            s = (s or u"").replace(u"\n", u" ")
            return s if len(s) <= 60 else s[:57] + u"…"

        prefix = u"⚠ в модели изменён после выгрузки · " if self.conflict else u""
        return u"{}{} · ID {} · «{}»: «{}» → «{}»".format(
            prefix, _category_name(self.el), self.el.Id.IntegerValue,
            self.param_name, short(self.old), short(self.new),
        )

    def __str__(self):
        return self.name


def _value_text(value):
    u"""Значение из JSON -> текст для записи; None, если значение не годится."""
    if value is None:
        return u""
    if isinstance(value, bool):
        return u"Да" if value else u"Нет"
    if isinstance(value, (int, long, float)):
        return unicode(value)
    if isinstance(value, basestring):
        return unicode(value)
    return None


def _find_element(doc, rec):
    uid = rec.get("uid")
    if uid:
        try:
            el = doc.GetElement(unicode(uid))
            if el is not None:
                return el
        except Exception:
            pass
    try:
        return doc.GetElement(ElementId(int(rec.get("id"))))
    except Exception:
        return None


def plan_changes(doc, data):
    u"""
    Сравнить снимок с текущей моделью. Ничего не пишет. Возвращает dict:
      changes        — [Change] (сначала конфликтные);
      unchanged      — сколько значений совпало с моделью;
      not_edited     — сколько значений в файле не правили, а в модели они
                       с выгрузки изменились (не пишутся);
      no_element     — [id/uid] элементов, которых нет в модели;
      no_param       — [(id, имя)] параметров, которых нет у элемента;
      read_only      — [(id, имя)] параметров только для чтения;
      bad_value      — [(id, имя, причина)] значений, которые не записать.
    """
    res = {"changes": [], "unchanged": 0, "not_edited": 0, "no_element": [],
           "no_param": [], "read_only": [], "bad_value": []}
    conflicts = []
    plain = []

    for rec in data.get("elements") or []:
        if not isinstance(rec, dict):
            continue
        params = rec.get("params")
        if not isinstance(params, dict) or not params:
            continue

        el = _find_element(doc, rec)
        if el is None:
            res["no_element"].append(rec.get("id") or rec.get("uid"))
            continue
        eid = el.Id.IntegerValue

        pmap = dict(_instance_params(el))
        hashes = rec.get("h")
        if not isinstance(hashes, dict):
            hashes = {}

        for name, raw in params.items():
            p = pmap.get(name)
            if p is None:
                res["no_param"].append((eid, name))
                continue
            if not _is_writable(p):
                res["read_only"].append((eid, name))
                continue
            new = _value_text(raw)
            if new is None:
                res["bad_value"].append((eid, name, u"не текст/число"))
                continue
            old = param_to_text(p)
            if old.strip() == new.strip():
                res["unchanged"] += 1
                continue
            orig = hashes.get(name)
            if orig is not None and _fingerprint(new) == orig:
                # в файле не правили, а модель с выгрузки изменилась —
                # не откатываем чужое изменение
                res["not_edited"] += 1
                continue
            # параметра не было в выгрузке (пустой или не в фильтре) —
            # считался пустым; модель ≠ исходному -> правка поверх чужой
            conflict = _fingerprint(old) != (orig if orig is not None
                                             else _fingerprint(u""))
            if not new.strip() and p.StorageType != StorageType.String:
                res["bad_value"].append(
                    (eid, name, u"пустое значение у числового параметра"))
                continue
            ch = Change(el, p, name, old, new, conflict)
            (conflicts if conflict else plain).append(ch)

    res["changes"] = conflicts + plain
    return res


def apply_changes(changes):
    u"""Записать правки. Вызывать внутри транзакции. (сколько записано, [ошибки])."""
    done = 0
    errors = []
    for ch in changes:
        if set_param_text(ch.param, ch.new):
            done += 1
        else:
            errors.append(u"ID {} / «{}»: не удалось записать «{}»".format(
                ch.el.Id.IntegerValue, ch.param_name, ch.new))
    return done, errors
