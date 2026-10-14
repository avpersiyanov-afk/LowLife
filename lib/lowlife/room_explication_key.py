# -*- coding: utf-8 -*-
"""Экспликация фрагмента в виде КЛЮЧЕВОЙ спецификации помещений
(вид таблицы «ключевая спецификация» в настройках кнопки).

Строки ключевой спецификации свободные, но каждый столбец, кроме
«Ключевого имени», в Revit обязан быть параметром категории. Поэтому здесь
четыре текстовых общих параметра LowLife с фиксированными GUID (`PARAMS`),
привязанные к помещениям; заводятся автоматически через временный ФОП
(подключённый ФОП пользователя не меняется). Помещениям ключ не назначается,
так что на сами помещения параметры не влияют; Revit лишь добавляет
помещениям ключевой параметр каждой такой спецификации.

«Ключевое имя» скрыто, по нему (001, 002, …) идёт сортировка. Высота строк
задаётся через TableSectionData.SetRowHeight; если Revit её для строк тела
не принимает — `fill` сообщает об этом (высота идёт от размера текста).
Создание/метку/выбор вида таблицы ведёт room_explication.
"""

import io
import os
import tempfile

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, ElementId, ElementOwnerViewFilter,
    FilteredElementCollector, ScheduleSortGroupField, SectionType,
    SharedParameterElement, ViewSchedule,
)
from System import Guid

from lowlife import room_explication_core as core

# Ключ столбца -> (имя общего параметра, GUID). Имена/GUID не менять:
# по GUID повторный запуск находит уже заведённые параметры.
PARAMS = (
    ("number", u"LL_Экспликация_Номер", "0d49f254-a0c7-4953-b450-116639cca2e2"),
    ("name", u"LL_Экспликация_Наименование", "cf634822-e8ed-4901-8aab-3626a0804411"),
    ("area", u"LL_Экспликация_Площадь", "13bf02c5-69f7-4fb1-9d5b-6d9208a2112c"),
    ("category", u"LL_Экспликация_Категория", "590902e1-804a-4a96-aec1-e0d7d60437ce"),
)
GROUP_NAME = u"LowLife"


def _text_spec():
    try:
        from Autodesk.Revit.DB import SpecTypeId
        return SpecTypeId.String.Text
    except Exception:
        from Autodesk.Revit.DB import ParameterType
        return ParameterType.Text


def _insert_binding(doc, definition, binding, reinsert):
    method = doc.ParameterBindings.ReInsert if reinsert else doc.ParameterBindings.Insert
    try:
        from Autodesk.Revit.DB import GroupTypeId
        return method(definition, binding, GroupTypeId.Text)
    except Exception:
        from Autodesk.Revit.DB import BuiltInParameterGroup
        return method(definition, binding, BuiltInParameterGroup.PG_TEXT)


def _find_binding(doc, guid):
    it = doc.ParameterBindings.ForwardIterator()
    while it.MoveNext():
        definition = it.Key
        try:
            shared = doc.GetElement(definition.Id)
            if isinstance(shared, SharedParameterElement) and shared.GuidValue == guid:
                return definition, it.Current
        except Exception:
            continue
    return None, None


def _create_definitions(app, missing):
    """Определения недостающих параметров из временного ФОП (подключённый ФОП
    пользователя восстанавливается). {ключ: ExternalDefinition}."""
    from Autodesk.Revit.DB import ExternalDefinitionCreationOptions
    old_path = app.SharedParametersFilename
    path = os.path.join(tempfile.gettempdir(), u"LowLife_explication_params.txt")
    with io.open(path, "wb"):
        pass  # пустой файл — Revit сам запишет в него заголовок ФОП
    result = {}
    try:
        app.SharedParametersFilename = path
        sp_file = app.OpenSharedParameterFile()
        group = sp_file.Groups.Create(GROUP_NAME)
        for key, name, guid in missing:
            opts = ExternalDefinitionCreationOptions(name, _text_spec())
            opts.GUID = Guid(guid)
            opts.Visible = True
            result[key] = group.Definitions.Create(opts)
    finally:
        try:
            app.SharedParametersFilename = old_path or u""
        except Exception:
            pass
        try:
            os.remove(path)
        except Exception:
            pass
    return result


def ensure_params(doc, app):
    """
    Четыре параметра столбцов привязаны к помещениям (экземпляр). Вызывать
    в транзакции. Возвращает {ключ: ElementId параметра}.
    """
    rooms_cat = doc.Settings.Categories.get_Item(BuiltInCategory.OST_Rooms)
    missing = []
    for key, name, guid in PARAMS:
        definition, binding = _find_binding(doc, Guid(guid))
        if definition is None:
            missing.append((key, name, guid))
        elif not binding.Categories.Contains(rooms_cat):
            cats = app.Create.NewCategorySet()
            for c in binding.Categories:
                cats.Insert(c)
            cats.Insert(rooms_cat)
            _insert_binding(doc, definition, app.Create.NewInstanceBinding(cats), True)

    if missing:
        created = _create_definitions(app, missing)
        for key, name, guid in missing:
            cats = app.Create.NewCategorySet()
            cats.Insert(rooms_cat)
            if not _insert_binding(doc, created[key], app.Create.NewInstanceBinding(cats), False):
                raise RuntimeError(u"Не удалось привязать параметр «{}» к помещениям.".format(name))

    ids = {}
    for key, name, guid in PARAMS:
        shared = SharedParameterElement.Lookup(doc, Guid(guid))
        if shared is None:
            raise RuntimeError(u"Параметр «{}» не найден после создания.".format(name))
        ids[key] = shared.Id
    return ids


# ---------------------------------------------------------------------------
# Ключевая спецификация
# ---------------------------------------------------------------------------

def _schedule_rows(doc, schedule):
    return list(FilteredElementCollector(doc)
                .WherePasses(ElementOwnerViewFilter(schedule.Id))
                .WhereElementIsNotElementType())


def _is_key_name_field(field):
    try:
        return field.ParameterId == ElementId(BuiltInParameter.REF_TABLE_ELEM_NAME)
    except Exception:
        return False


def _fields_by_param(definition):
    # Ключ — str(ElementId): не полагаемся на хеширование .NET-объектов в dict.
    result = {}
    for field_id in definition.GetFieldOrder():
        field = definition.GetField(field_id)
        result[str(field.ParameterId)] = field
    return result


def _setup_fields(doc, schedule, param_ids, columns):
    """Поля в порядке столбцов, заголовки, ширины; «Ключевое имя» скрыто и по
    нему сортировка."""
    d = schedule.Definition
    existing = _fields_by_param(d)
    schedulable = dict((str(sf.ParameterId), sf) for sf in d.GetSchedulableFields())

    key_field = None
    for field in existing.values():
        if _is_key_name_field(field):
            key_field = field
    order = []
    for key, heading, width_mm in columns:
        pid = str(param_ids[key])
        field = existing.get(pid)
        if field is None:
            sf = schedulable.get(pid)
            if sf is None:
                raise RuntimeError(u"Параметр столбца «{}» недоступен в "
                                   u"ключевой спецификации помещений.".format(heading))
            field = d.AddField(sf)
        field.IsHidden = False
        field.ColumnHeading = heading
        field.GridColumnWidth = width_mm / core.MM_IN_FOOT
        order.append(field.FieldId)

    rest = [fid for fid in d.GetFieldOrder() if fid not in order]
    try:
        from System.Collections.Generic import List
        from Autodesk.Revit.DB import ScheduleFieldId
        d.SetFieldOrder(List[ScheduleFieldId](order + rest))
    except Exception:
        pass

    if key_field is not None:
        key_field.IsHidden = True
        try:
            d.ClearSortGroupFields()
            d.AddSortGroupField(ScheduleSortGroupField(key_field.FieldId))
        except Exception:
            pass


def _insert_rows(doc, schedule, count):
    """Добавляет count строк (Revit сам создаёт элементы-строки)."""
    section = schedule.GetTableData().GetSectionData(SectionType.Body)
    for _ in range(count):
        first, last = section.FirstRowNumber, section.LastRowNumber
        for idx in (last + 1, last, first + 1, first):
            try:
                if section.CanInsertRow(idx):
                    section.InsertRow(idx)
                    break
            except Exception:
                continue
        else:
            raise RuntimeError(u"Revit не дал добавить строку в ключевую спецификацию.")


def _set_row_heights(schedule, header_mm, row_mm):
    """
    Высота строки заголовков граф (первая строка тела) и строк помещений.
    Возвращает True, если высоту строк помещений удалось задать (Revit
    может её не принимать — тогда она идёт от размера текста).
    """
    body = schedule.GetTableData().GetSectionData(SectionType.Body)
    first, last = body.FirstRowNumber, body.LastRowNumber
    try:
        body.SetRowHeight(first, header_mm / core.MM_IN_FOOT)
    except Exception:
        pass
    ok = True
    for row in range(first + 1, last + 1):
        try:
            body.SetRowHeight(row, row_mm / core.MM_IN_FOOT)
        except Exception:
            ok = False
    return ok




def create(doc, name):
    """Новая ключевая спецификация помещений (вызывать в транзакции)."""
    schedule = ViewSchedule.CreateKeySchedule(doc, ElementId(BuiltInCategory.OST_Rooms))
    schedule.Name = name
    try:
        schedule.Definition.KeyScheduleParameterName = core.key_param_name(name)
    except Exception:
        pass
    doc.Regenerate()
    return schedule


def fill(doc, app, schedule, title, columns, rows, heights):
    """
    Поля/заголовки/ширины, строки помещений, название, высота строк.
    Вызывать в транзакции. Возвращает список замечаний (пустой — всё задано).
    """
    param_ids = ensure_params(doc, app)
    _setup_fields(doc, schedule, param_ids, columns)

    old = _schedule_rows(doc, schedule)
    if old:
        from System.Collections.Generic import List
        doc.Delete(List[ElementId]([r.Id for r in old]))
        doc.Regenerate()

    _insert_rows(doc, schedule, len(rows))
    doc.Regenerate()
    new_rows = _schedule_rows(doc, schedule)
    if len(new_rows) != len(rows):
        raise RuntimeError(u"Создано строк: {}, нужно: {}.".format(len(new_rows), len(rows)))

    # Ключевые имена уникальны: сначала временные, чтобы «007» не совпало
    # с автоматическим именем другой новой строки.
    for row_el in new_rows:
        row_el.get_Parameter(BuiltInParameter.REF_TABLE_ELEM_NAME).Set(
            u"tmp-{}".format(row_el.UniqueId))
    guids = [(i, Guid(guid)) for i, (_key, _name, guid) in enumerate(PARAMS)]
    for row_el, key_name, values in zip(new_rows, core.key_names(len(rows)), rows):
        row_el.get_Parameter(BuiltInParameter.REF_TABLE_ELEM_NAME).Set(key_name)
        for i, guid in guids:
            row_el.get_Parameter(guid).Set(values[i])

    try:
        header = schedule.GetTableData().GetSectionData(SectionType.Header)
        header.SetCellText(header.FirstRowNumber, header.FirstColumnNumber, title)
    except Exception:
        pass

    doc.Regenerate()
    header_mm, row_mm = heights
    notes = []
    if rows and not _set_row_heights(schedule, header_mm, row_mm):
        notes.append(u"Высоту строк помещений Revit задать не дал — она идёт "
                     u"от размера текста спецификации.")
    return notes


def uses_params(schedule):
    """Ключевая спецификация, в полях которой есть параметры PARAMS."""
    try:
        d = schedule.Definition
        if not d.IsKeySchedule:
            return False
        ids = set()
        for _key, _name, guid in PARAMS:
            el = SharedParameterElement.Lookup(schedule.Document, Guid(guid))
            if el is not None:
                ids.add(str(el.Id))
        return any(str(d.GetField(fid).ParameterId) in ids for fid in d.GetFieldOrder())
    except Exception:
        return False
