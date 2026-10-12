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

Два режима (loi_check_settings): «свой список» — категории и параметры из
настроек, обязательны все; «этап приложения LOI» — категории, классы и
параметры из импортированного приложения (loi_appendix), у каждого элемента
обязательны только параметры его класса на выбранном этапе
(loi_check_core.CategoryPlan).

Незаполненные элементы всех категорий показываются на 3D-виде
VIEW_3D_NAME (build_3d_view): изометрия без шаблона вида, на которой
остальные модельные элементы документа скрыты («Скрыть элементы»,
постоянно). Повторный запуск переиспользует вид: прошлое скрытие снимается
и считается заново (_apply_visibility).
"""

from Autodesk.Revit.DB import (
    BuiltInParameter, CategoryType, ElementId, FilteredElementCollector,
    ScheduleFieldType, ScheduleSortGroupField, ScheduleSortOrder,
    StorageType, ViewSchedule
)

from lowlife import geometry, loi_check_core as core
from lowlife.params import param_to_text

SCHEDULE_PREFIX = u"LOI проверка"
VIEW_3D_NAME = u"LOI проверка — незаполненные"

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
    def __init__(self, category, summary, rows):
        self.category = category
        self.summary = summary
        self.rows = rows  # [(строка, параметр)] — столбцы отчёта и спецификации
        self.incomplete_rows = []
        self.schedule = None
        self.missing_fields = []  # строки, которых нет среди полей спецификации
        self.unknown_codes = {}  # код не из приложения -> число элементов (не проверялись)
        self.no_code = 0  # элементов без кода классификатора (проверены по общим параметрам)


def check_category(doc, category, rows, floor_param, plan=None, code_param=None):
    """
    Проверяет все экземпляры категории. rows — [(строка, параметр)].

    plan (loi_check_core.CategoryPlan) — проверка по этапу приложения LOI:
    у каждого элемента обязательны только параметры его класса (класс — по
    значению параметра code_param), остальные ячейки строки не проверяются.
    Без plan обязательны все rows.
    """
    summary = core.CategorySummary(category.Name, rows)
    result = CategoryResult(category, summary, rows)

    for el in collect_elements(doc, category):
        type_name, family_name, el_type = element_info(doc, el)
        required = None
        if plan is not None:
            code = u""
            if code_param:
                _found, code = read_param(doc, el, code_param, el_type)
                code = code or u""
            required, how = plan.required_for(code)
            if how == plan.UNKNOWN:
                key = code.strip()
                result.unknown_codes[key] = result.unknown_codes.get(key, 0) + 1
                continue
            if how == plan.NO_CODE:
                result.no_code += 1
            required = set(required)
        statuses, cells = [], []
        for _label, param in rows:
            if required is not None and param not in required:
                status, value = None, None
            else:
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


def resolve_plan_categories(doc, plans):
    """[(Category, CategoryPlan)] для категорий приложения, найденных в
    документе, и список ненайденных имён. Сравнение — без регистра и «ё»."""
    by_norm = {}
    for cat in doc.Settings.Categories:
        try:
            by_norm.setdefault(core.norm_name(cat.Name), cat)
        except Exception:
            continue
    found, missing = [], []
    for plan in plans:
        cat = by_norm.get(core.norm_name(plan.category))
        if cat is None:
            missing.append(plan.category)
        else:
            found.append((cat, plan))
    return found, missing


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
    """(по ключу ParameterId, по имени) -> SchedulableField. Имя —
    нормализованное (core.norm_name: регистр, «ё», пробелы), поле экземпляра
    важнее поля типа."""
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
        name = core.norm_name(name)
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


# причины, по которым параметр не попал в спецификацию
REASON_NOT_FOUND = u"нет ни у одного элемента категории"
REASON_FAMILY_PARAM = (u"параметр семейства (не общий) — Revit не выводит такие "
                       u"в спецификацию, нужен общий параметр или параметр проекта")
REASON_NOT_SCHEDULABLE = u"Revit не даёт вывести этот параметр в спецификацию категории"


def _field_via_elements(doc, by_id, param_name, elements):
    """
    Поле спецификации для параметра, найденного у самих элементов (экземпляр,
    потом тип) — по его Id, а не по имени. Возвращает (SchedulableField или
    None, причина отсутствия).
    """
    seen_family_param = False
    seen_any = False
    for el in elements:
        el_type = _element_type(doc, el)
        for owner in (el, el_type):
            if owner is None:
                continue
            try:
                p = owner.LookupParameter(param_name)
            except Exception:
                p = None
            if p is None:
                continue
            seen_any = True
            try:
                sf = by_id.get(str(p.Id))
            except Exception:
                sf = None
            if sf is not None:
                return sf, None
            try:
                if not p.IsShared and p.Id.IntegerValue > 0:
                    seen_family_param = True
            except Exception:
                pass
    if seen_family_param:
        return None, REASON_FAMILY_PARAM
    if seen_any:
        return None, REASON_NOT_SCHEDULABLE
    return None, REASON_NOT_FOUND


def _add_field(definition, sf, heading):
    field = definition.AddField(sf)
    try:
        field.ColumnHeading = heading
    except Exception:
        pass
    return field


def build_schedule(doc, category, rows, floor_param, elements=None):
    """
    Спецификация категории: «Тип», «Семейство», «Этаж» (параметр из
    настроек, иначе уровень элемента) и по столбцу на каждую строку списка
    (заголовок столбца — строка списка). Вызывать внутри транзакции.

    Поле ищется по имени (без учёта регистра, «ё» и лишних пробелов), а если
    не нашлось — по Id параметра, найденного у элементов категории
    (elements; по умолчанию — все экземпляры категории).
    Возвращает (schedule, [(строка списка, причина)] — что не попало).
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

    floor_sf = by_name.get(core.norm_name(floor_param)) if floor_param else None
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

    if elements is None:
        elements = collect_elements(doc, category)
    missing = []
    for label, param in rows:
        sf = by_name.get(core.norm_name(param))
        if sf is None:
            sf, reason = _field_via_elements(doc, by_id, param, elements)
            if sf is None:
                missing.append((label, reason))
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


# --- 3D-вид с незаполненными элементами ------------------------------------------

def _three_d_type(doc):
    from Autodesk.Revit.DB import ViewFamily, ViewFamilyType
    for vft in FilteredElementCollector(doc).OfClass(ViewFamilyType):
        try:
            if vft.ViewFamily == ViewFamily.ThreeDimensional:
                return vft
        except Exception:
            continue
    return None


def _find_3d_view(doc, name):
    from Autodesk.Revit.DB import View3D
    for v in FilteredElementCollector(doc).OfClass(View3D):
        try:
            if not v.IsTemplate and v.Name == name:
                return v
        except Exception:
            continue
    return None


# Модельные категории, которые не скрываем: служебные точки проекта —
# их скрытие поштучно ни к чему, а режим «Показать скрытые элементы» на
# виде с ними ведёт себя ненадёжно.
_NEVER_HIDE_BICS = ("OST_ProjectBasePoint", "OST_SharedBasePoint", "OST_IOS_GeoSite",
                    "OST_Cameras", "OST_Viewers", "OST_SectionBox")


def _never_hide_ids():
    from Autodesk.Revit.DB import BuiltInCategory
    ids = set()
    for name in _NEVER_HIDE_BICS:
        bic = getattr(BuiltInCategory, name, None)
        if bic is not None:
            ids.add(int(bic))
    return ids


def _hideable(el, view, skip_cat_ids):
    """Только «настоящие» модельные элементы: с модельной категорией, не
    видозависимые, не служебные точки, и Revit разрешает их скрыть. Плюс
    вставленные связи и импорт (DWG) — иначе их геометрия остаётся на виде."""
    from Autodesk.Revit.DB import ImportInstance, RevitLinkInstance
    try:
        if el.ViewSpecific:
            return False
        if isinstance(el, (RevitLinkInstance, ImportInstance)):
            return el.CanBeHidden(view)
        cat = el.Category
        if cat is None or cat.CategoryType != CategoryType.Model:
            return False
        if cat.Id.IntegerValue in skip_cat_ids:
            return False
        return el.CanBeHidden(view)
    except Exception:
        return False


def _unhide_all(doc, view):
    """Показывает всё, что скрыто на виде поштучно (прошлый запуск кнопки,
    в том числе старой версии, скрывавшей и служебные элементы)."""
    from System.Collections.Generic import List
    hidden = List[ElementId]()
    for el in FilteredElementCollector(doc).WhereElementIsNotElementType():
        try:
            if el.IsHidden(view):
                hidden.Add(el.Id)
        except Exception:
            continue
    if hidden.Count:
        view.UnhideElements(hidden)


def _keep_with_nested(doc, keep_ids):
    """keep_ids + вложенные общие семейства оставляемых элементов (иначе у
    оставленного семейства пропадают его вложенные части)."""
    from Autodesk.Revit.DB import FamilyInstance
    keep = set(keep_ids)
    for eid in list(keep_ids):
        el = doc.GetElement(ElementId(eid))
        if not isinstance(el, FamilyInstance):
            continue
        stack = [el]
        while stack:
            parent = stack.pop()
            try:
                sub_ids = parent.GetSubComponentIds()
            except Exception:
                continue
            for sid in sub_ids:
                if sid.IntegerValue not in keep:
                    keep.add(sid.IntegerValue)
                    sub = doc.GetElement(sid)
                    if isinstance(sub, FamilyInstance):
                        stack.append(sub)
    return keep


def _apply_visibility(doc, view, keep_ids):
    """
    На виде видны только элементы keep_ids (int ElementId.IntegerValue) и
    их вложенные семейства. Возвращает число скрытых элементов.

    Сначала всё скрытое поштучно показывается (прошлый запуск), потом
    скрываются модельные элементы ВСЕГО документа, кроме оставляемых
    (_hideable: без видозависимых и служебных — иначе режим «Показать
    скрытые элементы» на таком виде ронял Revit). Выборка по документу, а не
    по виду (FilteredElementCollector(doc, view.Id)): для только что
    созданного в той же транзакции вида выборка по виду может оказаться
    пустой — тогда ничего не скрывалось и на виде оставалась вся модель.
    """
    from System.Collections.Generic import List

    _unhide_all(doc, view)

    keep = _keep_with_nested(doc, keep_ids)
    skip = _never_hide_ids()
    to_hide = List[ElementId]()
    for el in FilteredElementCollector(doc).WhereElementIsNotElementType():
        if el.Id.IntegerValue in keep:
            continue
        try:
            if el.IsHidden(view):
                continue
        except Exception:
            continue
        if _hideable(el, view, skip):
            to_hide.Add(el.Id)
    if to_hide.Count:
        view.HideElements(to_hide)
    return to_hide.Count


def build_3d_view(doc, elements):
    """
    3D-вид VIEW_3D_NAME, на котором видны только elements. Вызывать внутри
    транзакции. Возвращает (вид, сколько элементов скрыто) или (None, 0) —
    нет элементов / нет типа 3D-вида.
    """
    from Autodesk.Revit.DB import View3D

    if not elements:
        return None, 0

    view = _find_3d_view(doc, VIEW_3D_NAME)
    if view is None:
        vft = _three_d_type(doc)
        if vft is None:
            return None, 0
        view = View3D.CreateIsometric(doc, vft.Id)
        view.Name = VIEW_3D_NAME
    else:
        # вид мог остаться во временном режиме — «Показать скрытые элементы»
        # (лампочка) или временное скрытие/изоляция; менять скрытие под ними
        # не стоит
        for mode in _temporary_modes():
            try:
                view.DisableTemporaryViewMode(mode)
            except Exception:
                pass

    try:
        view.ViewTemplateId = ElementId.InvalidElementId
    except Exception:
        pass
    try:
        view.IsSectionBoxActive = False
    except Exception:
        pass

    hidden = _apply_visibility(doc, view, set(el.Id.IntegerValue for el in elements))
    return view, hidden


def _temporary_modes():
    from Autodesk.Revit.DB import TemporaryViewMode
    modes = []
    for name in ("RevealHiddenElements", "TemporaryHideIsolate"):
        mode = getattr(TemporaryViewMode, name, None)
        if mode is not None:
            modes.append(mode)
    return modes
