# -*- coding: utf-8 -*-
"""Экспликация фрагмента — Revit API (`ToolsRooms.panel/FragmentExplication`).

1. Помещения фрагмента: помещения модели и видимых связей, чья точка
   размещения попадает в рамку подрезки плана (в плане) и в его секущий
   диапазон (по высоте).
2. Данные таблицы пишутся в строки КЛЮЧЕВОЙ спецификации помещений — она
   не зависит от фильтров и показывает ровно переданный список. Столбцы —
   четыре текстовых общих параметра LowLife с фиксированными GUID
   (`PARAMS`), привязанные к помещениям; заводятся автоматически через
   временный ФОП (подключённый ФОП пользователя не меняется). Помещениям
   ключ не назначается, поэтому на сами помещения эти параметры не влияют.
3. Спецификация называется по виду (`room_explication_core.schedule_name`);
   повторный запуск на том же виде обновляет её строки, заголовки и
   ширины — на листе она остаётся на месте.
"""

import io
import os
import tempfile

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, ElementId, ElementOwnerViewFilter,
    FilteredElementCollector, RevitLinkInstance, ScheduleSortGroupField,
    SectionType, SharedParameterElement, ViewSchedule, ViewType,
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

# Запас по высоте при отборе помещений по секущему диапазону плана, футы.
Z_TOLERANCE_FT = 1.0


# ---------------------------------------------------------------------------
# Вид и помещения
# ---------------------------------------------------------------------------

_PLAN_TYPES = set(getattr(ViewType, n) for n in
                  ("FloorPlan", "CeilingPlan", "EngineeringPlan", "AreaPlan")
                  if hasattr(ViewType, n))


def unsupported_reason(view):
    """None, если по виду можно строить экспликацию, иначе текст причины."""
    if view is None or view.IsTemplate:
        return u"Откройте план, по которому нужна экспликация."
    if view.ViewType not in _PLAN_TYPES:
        return (u"Экспликация фрагмента строится по плану (этажа, потолка, "
                u"несущих конструкций, зон). Активный вид: {}.".format(view.ViewType))
    if not view.CropBoxActive:
        return (u"У вида не включена подрезка — непонятно, какой это "
                u"фрагмент. Обрежьте вид (кнопка «Обрезать вид») и "
                u"запустите снова.")
    return None


def _crop_frame(view):
    """(преобразование модель -> вид, (xmin, ymin, xmax, ymax)) рамки подрезки."""
    box = view.CropBox
    rect = (min(box.Min.X, box.Max.X), min(box.Min.Y, box.Max.Y),
            max(box.Min.X, box.Max.X), max(box.Min.Y, box.Max.Y))
    return box.Transform.Inverse, rect


def _z_range(doc, view):
    """(низ, верх) секущего диапазона плана во внутренних координатах."""
    level = view.GenLevel
    base = level.ProjectElevation if level is not None else 0.0
    lo, hi = base, base
    try:
        from Autodesk.Revit.DB import PlanViewPlane
        vr = view.GetViewRange()
        for plane in (PlanViewPlane.BottomClipPlane, PlanViewPlane.CutPlane,
                      PlanViewPlane.TopClipPlane):
            lvl = doc.GetElement(vr.GetLevelId(plane))
            if lvl is None:
                continue
            z = lvl.ProjectElevation + vr.GetOffset(plane)
            if plane == PlanViewPlane.TopClipPlane:
                hi = max(hi, min(z, base + 3 * Z_TOLERANCE_FT))
            else:
                lo, hi = min(lo, z), max(hi, z)
    except Exception:
        pass
    return lo - Z_TOLERANCE_FT, hi + Z_TOLERANCE_FT


def _rooms(source_doc):
    return (FilteredElementCollector(source_doc)
            .OfCategory(BuiltInCategory.OST_Rooms)
            .WhereElementIsNotElementType())


def _text_param(el, bip=None, name=None):
    try:
        p = el.get_Parameter(bip) if bip is not None else el.LookupParameter(name)
    except Exception:
        p = None
    if p is None or not p.HasValue:
        return u""
    try:
        return p.AsString() or p.AsValueString() or u""
    except Exception:
        return u""


def _room_data(room, category_param):
    return {
        "number": _text_param(room, BuiltInParameter.ROOM_NUMBER),
        "name": _text_param(room, BuiltInParameter.ROOM_NAME),
        "area_m2": room.Area * core.SQ_FT_TO_SQ_M,
        "category": _text_param(room, name=category_param) if category_param else u"",
    }


def collect_fragment_rooms(doc, view, category_param=u""):
    """
    Помещения фрагмента по источникам: {подпись источника: [dict помещения]}
    (dict — как ждёт room_explication_core.build_rows) и число отброшенных
    неразмещённых/незамкнутых помещений (площадь 0) внутри рамки.
    """
    to_view, rect = _crop_frame(view)
    lo, hi = _z_range(doc, view)

    sources = [(u"Эта модель", doc, None)]
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        try:
            link_doc = link.GetLinkDocument()
            if link_doc is None or link.IsHidden(view):
                continue
        except Exception:
            continue
        sources.append((u"Связь: {}".format(link_doc.Title), link_doc,
                        link.GetTotalTransform()))

    result = {}
    skipped = 0
    for label, source_doc, transform in sources:
        for room in _rooms(source_doc):
            loc = room.Location
            if loc is None or not hasattr(loc, "Point"):
                continue
            pt = loc.Point if transform is None else transform.OfPoint(loc.Point)
            if not lo <= pt.Z <= hi:
                continue
            local = to_view.OfPoint(pt)
            if not core.in_rect(local.X, local.Y, rect):
                continue
            if room.Area <= 0:
                skipped += 1
                continue
            result.setdefault(label, []).append(_room_data(room, category_param))
    return result, skipped


# ---------------------------------------------------------------------------
# Общие параметры столбцов
# ---------------------------------------------------------------------------

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

def _element_name(el):
    try:
        from Autodesk.Revit.DB import Element
        return Element.Name.GetValue(el)
    except Exception:
        return el.Name


def find_schedule(doc, name):
    for v in FilteredElementCollector(doc).OfClass(ViewSchedule):
        try:
            if not v.IsTemplate and v.Definition.IsKeySchedule and _element_name(v) == name:
                return v
        except Exception:
            continue
    return None


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


def build_schedule(doc, app, view_name, rows, columns, heights=None):
    """
    Создаёт или обновляет ключевую спецификацию фрагмента. Вызывать в
    транзакции. rows — из room_explication_core.build_rows; columns — из
    room_explication_settings.columns; heights — (шапка, строка) в мм.
    Возвращает (спецификация, создана ли, задана ли высота строк).
    """
    param_ids = ensure_params(doc, app)
    name = core.schedule_name(view_name)
    schedule = find_schedule(doc, name)
    created = schedule is None
    if created:
        schedule = ViewSchedule.CreateKeySchedule(doc, ElementId(BuiltInCategory.OST_Rooms))
        schedule.Name = name
        try:
            schedule.Definition.KeyScheduleParameterName = core.key_param_name(view_name)
        except Exception:
            pass
        doc.Regenerate()

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
        header.SetCellText(header.FirstRowNumber, header.FirstColumnNumber, core.TITLE)
    except Exception:
        pass

    doc.Regenerate()
    header_mm, row_mm = heights or (core.HEADER_HEIGHT_MM, core.ROW_HEIGHT_MM)
    rows_ok = _set_row_heights(schedule, header_mm, row_mm)
    return schedule, created, rows_ok
