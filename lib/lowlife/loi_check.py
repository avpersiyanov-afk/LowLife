# -*- coding: utf-8 -*-
"""
Логика кнопки «Проверка LOI» (LOI.panel/CheckLOI.pushbutton): проверяет,
заполнены ли у элементов выбранных категорий параметры из настроек
(loi_check_settings.py), и строит по каждой категории спецификацию со
столбцами «Тип», «Семейство», «Этаж» и выбранными параметрами.

Спецификация — по одной на категорию: обычная спецификация Revit всегда
одной категории, а у многокатегорийной нельзя ограничить набор категорий
(фильтры спецификации объединяются только через «И»). По той же причине
спецификация показывает все элементы категории, а не только незаполненные —
«хотя бы один параметр пуст» фильтром не выразить; незаполненные элементы
перечисляются в отчёте кнопки (loi_check_core.CategorySummary).

Повторный запуск не плодит спецификации: спецификация с тем же именем и той
же категорией пересобирается (поля/сортировка/фильтры заменяются), поэтому
её можно один раз положить на лист.

Значение параметра ищется сначала у экземпляра, потом у его типа — так же,
как его показывает спецификация.
"""

from Autodesk.Revit.DB import (
    BuiltInParameter, CategoryType, ElementId, FilteredElementCollector,
    ScheduleFieldType, ScheduleSortGroupField, ScheduleSortOrder,
    StorageType, ViewSchedule
)

from lowlife import geometry, loi_check_core as core
from lowlife.params import param_to_text

SCHEDULE_PREFIX = u"LOI проверка"

TYPE_HEADING = u"Тип"
FAMILY_HEADING = u"Семейство"
FLOOR_HEADING = u"Этаж"

# Встроенные параметры по порядку предпочтения — у разных категорий поле
# называется/устроено по-разному (у семейств «Уровень», у лотков и труб
# «Базовый уровень» и т.п.). Берётся первый, что есть среди полей
# спецификации категории. getattr — часть имён есть не во всех версиях Revit.
_TYPE_BIPS = ("ELEM_TYPE_PARAM", "SYMBOL_NAME_PARAM")
_FAMILY_BIPS = ("ELEM_FAMILY_PARAM", "ALL_MODEL_FAMILY_NAME")
_LEVEL_BIPS = (
    "FAMILY_LEVEL_PARAM", "INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM",
    "RBS_START_LEVEL_PARAM", "SCHEDULE_LEVEL_PARAM", "LEVEL_PARAM",
)


def _element_name(el):
    try:
        from Autodesk.Revit.DB import Element
        return Element.Name.GetValue(el)
    except Exception:
        try:
            return el.Name
        except Exception:
            return u""


def _bip_keys(names):
    keys = []
    for name in names:
        bip = getattr(BuiltInParameter, name, None)
        if bip is not None:
            keys.append(str(ElementId(bip)))
    return keys


# --- категории ---------------------------------------------------------------

class CategoryOption(object):
    """Категория — для forms.SelectFromList (по образцу selection.CategoryOption)."""

    def __init__(self, category, count):
        self.category = category
        self.raw_name = category.Name
        self.count = count
        self.name = u"{} ({})".format(category.Name, count)

    def __str__(self):
        return self.name


def _instance_count(doc, category):
    try:
        return (FilteredElementCollector(doc).OfCategoryId(category.Id)
                .WhereElementIsNotElementType().GetElementCount())
    except Exception:
        return 0


def list_categories(doc):
    """Модельные категории документа, у которых есть экземпляры и к которым
    можно привязывать параметры, — отсортированный по имени список
    CategoryOption."""
    options = []
    for cat in doc.Settings.Categories:
        try:
            if cat.CategoryType != CategoryType.Model or not cat.AllowsBoundParameters:
                continue
            name = cat.Name
        except Exception:
            continue
        if not name:
            continue
        count = _instance_count(doc, cat)
        if count:
            options.append(CategoryOption(cat, count))
    options.sort(key=lambda o: o.raw_name.lower())
    return options


def resolve_categories(doc, names):
    """Имена категорий -> (найденные Category в порядке names, ненайденные имена).
    Регистр не важен."""
    by_lower = {}
    for cat in doc.Settings.Categories:
        try:
            by_lower.setdefault(cat.Name.lower(), cat)
        except Exception:
            continue
    found, missing = [], []
    for name in names:
        cat = by_lower.get(unicode(name).lower())
        if cat is None:
            missing.append(name)
        else:
            found.append(cat)
    return found, missing


def collect_elements(doc, category):
    """Экземпляры категории текущего документа (без типов)."""
    try:
        return list(FilteredElementCollector(doc).OfCategoryId(category.Id)
                    .WhereElementIsNotElementType().ToElements())
    except Exception:
        return []


# --- значения параметров -----------------------------------------------------

def _element_type(doc, el):
    try:
        type_id = el.GetTypeId()
        if type_id is not None and type_id != ElementId.InvalidElementId:
            return doc.GetElement(type_id)
    except Exception:
        pass
    return None


def read_param(doc, el, name, el_type=None):
    """(найден ли параметр, текст значения или None) — сначала у экземпляра,
    потом у типа."""
    if el_type is None:
        el_type = _element_type(doc, el)
    for owner in (el, el_type):
        if owner is None:
            continue
        try:
            p = owner.LookupParameter(name)
        except Exception:
            p = None
        if p is None:
            continue
        if not p.HasValue:
            return True, None
        try:
            if p.StorageType == StorageType.ElementId:
                eid = p.AsElementId()
                if eid is None or eid == ElementId.InvalidElementId:
                    return True, None
        except Exception:
            pass
        return True, param_to_text(p)
    return False, None


def element_info(doc, el):
    """(тип, семейство, тип-элемент) элемента для отчёта."""
    el_type = _element_type(doc, el)
    type_name = _element_name(el_type) if el_type is not None else u""
    family_name = u""
    try:
        family_name = el_type.FamilyName if el_type is not None else u""
    except Exception:
        family_name = u""
    return type_name or u"", family_name or u"", el_type


def floor_text(doc, el, floor_param, el_type=None):
    """Этаж элемента для отчёта: параметр «Этаж» из настроек, иначе — имя
    уровня элемента."""
    if floor_param:
        found, value = read_param(doc, el, floor_param, el_type)
        if found:
            return value or u""
    level = geometry.get_element_level(doc, el)
    return geometry.level_name(level) if level is not None else u""


class ElementRow(object):
    def __init__(self, element, type_name, family_name, floor, cells):
        self.element = element
        self.type_name = type_name
        self.family_name = family_name
        self.floor = floor
        self.cells = cells  # тексты ячеек по строкам списка


class CategoryResult(object):
    def __init__(self, category, summary):
        self.category = category
        self.summary = summary
        self.incomplete_rows = []
        self.schedule = None
        self.missing_fields = []  # строки, которых нет среди полей спецификации


def check_category(doc, category, rows, floor_param):
    """Проверяет все экземпляры категории. rows — [(строка, параметр)]."""
    summary = core.CategorySummary(category.Name, rows)
    result = CategoryResult(category, summary)

    for el in collect_elements(doc, category):
        type_name, family_name, el_type = element_info(doc, el)
        statuses, cells = [], []
        for _label, param in rows:
            found, value = read_param(doc, el, param, el_type)
            status = core.status_of(found, value)
            statuses.append(status)
            cells.append(core.status_text(status, value))
        if summary.add(statuses):
            result.incomplete_rows.append(ElementRow(
                el, type_name, family_name,
                floor_text(doc, el, floor_param, el_type), cells))

    result.incomplete_rows.sort(key=lambda r: (r.floor, r.family_name, r.type_name))
    return result


# --- спецификация ------------------------------------------------------------

def _schedules_by_name(doc):
    found = {}
    for v in FilteredElementCollector(doc).OfClass(ViewSchedule):
        try:
            if v.IsTemplate:
                continue
            found[_element_name(v)] = v
        except Exception:
            continue
    return found


def _get_or_create_schedule(doc, category):
    """Спецификация категории с именем schedule_name: существующая (очищенная)
    той же категории или новая (при занятом имени — с номером)."""
    base = core.schedule_name(SCHEDULE_PREFIX, category.Name)
    existing = _schedules_by_name(doc)

    schedule = existing.get(base)
    if schedule is not None and schedule.Definition.CategoryId == category.Id:
        d = schedule.Definition
        d.ClearSortGroupFields()
        d.ClearFilters()
        for fid in list(d.GetFieldOrder()):
            d.RemoveField(fid)
        return schedule

    schedule = ViewSchedule.CreateSchedule(doc, category.Id)
    name = base
    n = 2
    while name in existing:
        name = u"{} ({})".format(base, n)
        n += 1
    schedule.Name = name
    return schedule


def _schedulable_index(doc, definition):
    """(по ключу встроенного параметра, по имени) -> SchedulableField. По
    имени — поле экземпляра важнее поля типа."""
    by_id, by_name = {}, {}
    for sf in definition.GetSchedulableFields():
        try:
            by_id.setdefault(str(sf.ParameterId), sf)
        except Exception:
            pass
        try:
            name = sf.GetName(doc)
        except Exception:
            continue
        if not name:
            continue
        current = by_name.get(name)
        if current is None or (current.FieldType != ScheduleFieldType.Instance
                               and sf.FieldType == ScheduleFieldType.Instance):
            by_name[name] = sf
    return by_id, by_name


def _first_by_bips(by_id, bip_names):
    for key in _bip_keys(bip_names):
        sf = by_id.get(key)
        if sf is not None:
            return sf
    return None


def _add_field(definition, sf, heading):
    field = definition.AddField(sf)
    try:
        field.ColumnHeading = heading
    except Exception:
        pass
    return field


def build_schedule(doc, category, rows, floor_param):
    """
    Спецификация категории: «Тип», «Семейство», «Этаж» (параметр из
    настроек, иначе уровень элемента) и по столбцу на каждую строку списка
    (заголовок столбца — строка списка). Вызывать внутри транзакции.
    Возвращает (schedule, [строки списка, для которых нет поля]).
    """
    schedule = _get_or_create_schedule(doc, category)
    d = schedule.Definition
    d.IsItemized = True
    try:
        d.ShowGrandTotal = False
    except Exception:
        pass

    by_id, by_name = _schedulable_index(doc, d)

    sort_fields = []
    used = set()

    floor_sf = by_name.get(floor_param) if floor_param else None
    if floor_sf is None:
        floor_sf = _first_by_bips(by_id, _LEVEL_BIPS)

    for sf, heading in (
        (_first_by_bips(by_id, _TYPE_BIPS), TYPE_HEADING),
        (_first_by_bips(by_id, _FAMILY_BIPS), FAMILY_HEADING),
        (floor_sf, FLOOR_HEADING),
    ):
        if sf is None:
            continue
        field = _add_field(d, sf, heading)
        used.add(str(sf.ParameterId))
        sort_fields.append((heading, field))

    missing = []
    for label, param in rows:
        sf = by_name.get(param)
        if sf is None:
            missing.append(label)
            continue
        key = str(sf.ParameterId)
        if key in used:
            continue
        used.add(key)
        _add_field(d, sf, label)

    # Сортировка: этаж, семейство, тип
    order = {FLOOR_HEADING: 0, FAMILY_HEADING: 1, TYPE_HEADING: 2}
    for _heading, field in sorted(sort_fields, key=lambda x: order[x[0]]):
        try:
            d.AddSortGroupField(ScheduleSortGroupField(field.FieldId, ScheduleSortOrder.Ascending))
        except Exception:
            pass

    return schedule, missing
