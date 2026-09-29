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
    FilteredElementCollector, SectionType, StorageType, ViewSchedule,
)

from lowlife.schedule_excel import _param_to_text, _set_param_text

# Заголовок столбца ключевого имени в выгрузке/окне правки.
KEY_COLUMN = u"Ключевое имя"

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


# --- правка справочника: добавление строк, запись значений, Excel ------------

def refresh(doc, ks):
    """Перечитывает строки спецификации (после добавления строк)."""
    ks.rows = _schedule_rows(doc, ks.schedule)
    return ks


def writable_fields(ks):
    """
    {имя поля: True/False} — можно ли писать значение этого столбца.
    Смотрим на первую строку: вычисляемые поля (параметра у строки нет),
    read-only и ссылочные (ElementId) — только для чтения. Пустой
    справочник — все поля считаем записываемыми.
    """
    result = {}
    sample = ks.rows[0] if ks.rows else None
    for name in ks.field_names():
        if sample is None:
            result[name] = True
            continue
        try:
            p = sample.LookupParameter(name)
            result[name] = bool(p is not None and not p.IsReadOnly
                                and p.StorageType != StorageType.ElementId)
        except Exception:
            result[name] = False
    return result


def row_values(row, field_names):
    """[ключевое имя, значения полей...] строкой, как в спецификации."""
    return [key_name(row) or u""] + [_param_to_text(row.LookupParameter(n)) for n in field_names]


def catalog_to_table(ks):
    """(rows, col_widths) для xlsx_io.write_xlsx: заголовок + строки справочника."""
    fields = ks.field_names()
    rows = [[KEY_COLUMN] + fields]
    for row in ks.rows:
        rows.append(row_values(row, fields))
    widths = [max(12, min(60, max(len(unicode(r[i] or u"")) for r in rows) + 2))
              for i in range(len(rows[0]))]
    return rows, widths


def add_row(doc, ks):
    """
    Новая строка ключевой спецификации (вызывать в транзакции). Revit API
    не даёт «создать строку-элемент» напрямую — вставляем строку в тело
    таблицы спецификации (TableSectionData.InsertRow), Revit сам создаёт
    элемент. Какой индекс допустим, зависит от наличия заголовков/
    группировки в теле, поэтому перебираем несколько. Новый элемент
    находим по разнице строк до/после. Возвращает элемент или None.
    """
    before = set(r.Id.IntegerValue for r in _schedule_rows(doc, ks.schedule))
    section = ks.schedule.GetTableData().GetSectionData(SectionType.Body)
    first, last = section.FirstRowNumber, section.LastRowNumber
    inserted = False
    for idx in (first + 1, first, last + 1, last):
        try:
            if not section.CanInsertRow(idx):
                continue
            section.InsertRow(idx)
            inserted = True
            break
        except Exception:
            continue
    if not inserted:
        return None
    doc.Regenerate()
    for row in _schedule_rows(doc, ks.schedule):
        if row.Id.IntegerValue not in before:
            return row
    return None


def _set_key_name(row, text):
    try:
        p = row.get_Parameter(BuiltInParameter.REF_TABLE_ELEM_NAME)
        return bool(p is not None and not p.IsReadOnly and p.Set(text))
    except Exception:
        return False


def write_row(row, values, writable):
    """
    values — {имя столбца: текст}. Пишет только записываемые столбцы и
    только если значение отличается от текущего. Возвращает
    (число изменённых значений, [ошибки]).
    """
    changed = 0
    errors = []
    for name, text in values.items():
        text = u"" if text is None else unicode(text).strip()
        if name == KEY_COLUMN:
            if text and text != (key_name(row) or u""):
                if _set_key_name(row, text):
                    changed += 1
                else:
                    errors.append(u"«{}»: не удалось задать ключевое имя".format(text))
            continue
        if not writable.get(name):
            continue
        p = row.LookupParameter(name)
        if p is None:
            continue
        if _param_to_text(p) == text:
            continue
        if not text and p.StorageType != StorageType.String:
            continue
        if _set_param_text(p, text):
            changed += 1
        else:
            errors.append(u"«{}», {}: не записалось значение «{}»".format(
                key_name(row) or row.Id.IntegerValue, name, text))
    return changed, errors


def apply_entries(doc, ks, entries):
    """
    entries — список (строка-элемент или None, {столбец: текст}); None —
    новая строка. Проверяет уникальность ключевых имён, создаёт новые
    строки и пишет значения (вызывать в транзакции). Возвращает dict
    added/updated/changed/unchanged/errors.
    """
    stats = {"added": 0, "updated": 0, "changed": 0, "unchanged": 0, "errors": []}
    writable = writable_fields(ks)

    # ключевые имена строк, которые правка не трогает, + имена из записей
    touched = set(el.Id.IntegerValue for el, _ in entries if el is not None)
    names = set()
    for row in ks.rows:
        if row.Id.IntegerValue not in touched:
            names.add((key_name(row) or u"").strip().lower())
    ok_entries = []
    for el, values in entries:
        name = (values.get(KEY_COLUMN) or u"").strip()
        if not name and el is not None:
            name = key_name(el) or u""
        if not name:
            stats["errors"].append(u"Строка без ключевого имени пропущена")
            continue
        if name.lower() in names:
            stats["errors"].append(u"Ключевое имя «{}» повторяется — строка пропущена".format(name))
            continue
        names.add(name.lower())
        ok_entries.append((el, values))

    for el, values in ok_entries:
        if el is None:
            el = add_row(doc, ks)
            if el is None:
                stats["errors"].append(
                    u"«{}»: Revit не дал добавить строку в спецификацию «{}»".format(
                        values.get(KEY_COLUMN), ks.name))
                continue
            stats["added"] += 1
            ks.rows.append(el)
            n, errs = write_row(el, values, writable)
            stats["changed"] += n
            stats["errors"].extend(errs)
            continue
        n, errs = write_row(el, values, writable)
        stats["errors"].extend(errs)
        if n:
            stats["updated"] += 1
            stats["changed"] += n
        else:
            stats["unchanged"] += 1
    return stats


def table_to_entries(ks, table):
    """
    Строки прочитанного .xlsx (первая — заголовок) -> (entries для
    apply_entries, [неизвестные столбцы]). Сопоставление со справочником —
    по ключевому имени (ID элементов в другом проекте другие). Столбцы,
    которых нет в спецификации, пропускаются.
    """
    if not table:
        raise ValueError(u"Файл пустой или не прочитался.")
    header = [(c or u"").strip() for c in table[0]]
    if KEY_COLUMN not in header:
        raise ValueError(u"В первой строке файла нет столбца «{}».".format(KEY_COLUMN))
    fields = set(ks.field_names())
    unknown = [h for h in header if h and h != KEY_COLUMN and h not in fields]

    by_name = {}
    for row in ks.rows:
        by_name[(key_name(row) or u"").strip().lower()] = row

    entries = []
    key_idx = header.index(KEY_COLUMN)
    for cells in table[1:]:
        cells = list(cells) + [None] * (len(header) - len(cells))
        if not any((c or u"").strip() for c in cells):
            continue  # пустая строка
        name = (cells[key_idx] or u"").strip()
        values = {}
        for i, h in enumerate(header):
            if h == KEY_COLUMN or h in fields:
                values[h] = cells[i]
        entries.append((by_name.get(name.lower()), values))
    return entries, unknown
