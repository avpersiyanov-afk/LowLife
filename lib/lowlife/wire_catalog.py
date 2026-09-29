# -*- coding: utf-8 -*-
"""
Поиск в модели справочника кабелей — ключевой спецификации, на строки
которой ссылается параметр электрической цепи «Проводник»
(StorageType.ElementId, но НЕ Autodesk.Revit.DB.Electrical.WireType, а
строка ключевой спецификации).

Раньше строки искались перебором ВСЕХ элементов документа с отбором по
BuiltInParameter.REF_TABLE_ELEM_NAME + наличию параметра-признака — в
выдачу попадали строки любых ключевых спецификаций (помещений, других
категорий), у которых случайно оказался такой же параметр. Теперь поиск
идёт от самих ключевых спецификаций:

1. ViewSchedule с Definition.IsKeySchedule категории «Электрические цепи»
   (OST_ElectricalCircuit) — только такой ключ может стоять в параметре
   цепи. Если таких нет вовсе — запасной вариант: любые ключевые
   спецификации, чей ключевой параметр называется key_param_name.
2. Если среди них есть спецификации с ключевым параметром key_param_name
   («Проводник») — берутся только они.
3. Параметр-признак (marker_param_name, необязательный) — дополнительно
   сужает выбор до спецификаций, у строк которых он есть; если после
   сужения ничего не осталось, признак игнорируется (он устарел/опечатка,
   а сами спецификации уже отобраны точно).
4. Строки спецификации — элементы, принадлежащие её виду
   (ElementOwnerViewFilter), с «Ключевым именем».
"""

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, ElementId, ElementOwnerViewFilter,
    FilteredElementCollector, StorageType, ViewSchedule,
)

# Имя параметра цепи, ссылающегося на строку справочника (то же, что
# scs_manual_circuits.CONDUCTOR_PARAM_NAME; в СКУД/СПС — настройка
# cable_type_param, по умолчанию тоже «Проводник»).
DEFAULT_KEY_PARAM_NAME = u"Проводник"


def _name(el):
    try:
        from Autodesk.Revit.DB import Element
        return Element.Name.GetValue(el)
    except Exception:
        try:
            return el.Name
        except Exception:
            return None


def key_name(row):
    """«Ключевое имя» строки ключевой спецификации (или None)."""
    try:
        p = row.get_Parameter(BuiltInParameter.REF_TABLE_ELEM_NAME)
        if p and p.HasValue:
            return p.AsString()
    except Exception:
        pass
    return None


class KeySchedule(object):
    """Ключевая спецификация и её строки."""

    def __init__(self, schedule, rows):
        self.schedule = schedule
        self.rows = rows
        self.name = _name(schedule) or u"ID {}".format(schedule.Id.IntegerValue)
        d = schedule.Definition
        self.key_param_name = u""
        try:
            self.key_param_name = d.KeyScheduleParameterName or u""
        except Exception:
            pass
        self.category_id = d.CategoryId

    @property
    def is_circuit(self):
        return self.category_id == ElementId(BuiltInCategory.OST_ElectricalCircuit)

    def has_param(self, param_name):
        for row in self.rows:
            try:
                if row.LookupParameter(param_name) is not None:
                    return True
            except Exception:
                pass
        return False

    def field_names(self):
        """Имена параметров в полях спецификации (порядок столбцов)."""
        names = []
        try:
            d = self.schedule.Definition
            for field_id in d.GetFieldOrder():
                field = d.GetField(field_id)
                try:
                    if field.IsHidden:
                        continue
                except Exception:
                    pass
                try:
                    if field.ParameterId == ElementId(BuiltInParameter.REF_TABLE_ELEM_NAME):
                        continue  # «Ключевое имя» выводится отдельно
                except Exception:
                    pass
                n = field.GetName()
                if n and n not in names:
                    names.append(n)
        except Exception:
            pass
        return names


def _schedule_rows(doc, schedule):
    rows = []
    try:
        collector = (FilteredElementCollector(doc)
                     .WherePasses(ElementOwnerViewFilter(schedule.Id))
                     .WhereElementIsNotElementType())
        rows = [el for el in collector if key_name(el) is not None]
    except Exception:
        rows = []

    if not rows:
        # Запасной путь: элементы, «видимые» в самой спецификации.
        try:
            collector = FilteredElementCollector(doc, schedule.Id).WhereElementIsNotElementType()
            rows = [el for el in collector if key_name(el) is not None]
        except Exception:
            rows = []

    rows.sort(key=lambda r: (key_name(r) or u"").lower())
    return rows


def list_key_schedules(doc):
    """Все ключевые спецификации документа (без шаблонов) со строками."""
    result = []
    for v in FilteredElementCollector(doc).OfClass(ViewSchedule):
        try:
            if v.IsTemplate:
                continue
            d = v.Definition
            if d is None or not d.IsKeySchedule:
                continue
        except Exception:
            continue
        result.append(KeySchedule(v, _schedule_rows(doc, v)))
    result.sort(key=lambda ks: ks.name.lower())
    return result


def pick_wire_catalogs(key_schedules, marker_param_name=None,
                       key_param_name=DEFAULT_KEY_PARAM_NAME):
    """Из списка KeySchedule отбирает справочники кабелей (см. docstring модуля)."""
    key_param_name = (key_param_name or u"").strip()
    marker_param_name = (marker_param_name or u"").strip()

    candidates = [ks for ks in key_schedules if ks.is_circuit]
    if key_param_name:
        by_key = [ks for ks in candidates if ks.key_param_name == key_param_name]
        if by_key:
            candidates = by_key
        elif not candidates:
            candidates = [ks for ks in key_schedules if ks.key_param_name == key_param_name]

    if marker_param_name:
        marked = [ks for ks in candidates if ks.has_param(marker_param_name)]
        if marked:
            candidates = marked

    return [ks for ks in candidates if ks.rows]


def find_wire_catalogs(doc, marker_param_name=None, key_param_name=DEFAULT_KEY_PARAM_NAME):
    return pick_wire_catalogs(list_key_schedules(doc), marker_param_name, key_param_name)


def list_wire_catalog_rows(doc, marker_param_name=None, key_param_name=DEFAULT_KEY_PARAM_NAME):
    """Плоский список строк всех найденных справочников кабелей (без дублей)."""
    seen = set()
    rows = []
    for ks in find_wire_catalogs(doc, marker_param_name, key_param_name):
        for row in ks.rows:
            rid = row.Id.IntegerValue
            if rid in seen:
                continue
            seen.add(rid)
            rows.append(row)
    return rows


def param_text(el, param_name):
    """Значение параметра строкой (как в спецификации) или u""."""
    try:
        p = el.LookupParameter(param_name)
        if p is None or not p.HasValue:
            return u""
        if p.StorageType == StorageType.String:
            return p.AsString() or u""
        return p.AsValueString() or u""
    except Exception:
        return u""


def count_circuit_usage(doc, key_param_name=DEFAULT_KEY_PARAM_NAME):
    """{id строки справочника (int): число цепей, где она стоит в key_param_name}."""
    usage = {}
    if not key_param_name:
        return usage
    circuits = (FilteredElementCollector(doc)
                .OfCategory(BuiltInCategory.OST_ElectricalCircuit)
                .WhereElementIsNotElementType())
    for c in circuits:
        try:
            p = c.LookupParameter(key_param_name)
            if p is None or p.StorageType != StorageType.ElementId:
                continue
            eid = p.AsElementId()
            if eid is None or eid == ElementId.InvalidElementId:
                continue
            usage[eid.IntegerValue] = usage.get(eid.IntegerValue, 0) + 1
        except Exception:
            pass
    return usage
