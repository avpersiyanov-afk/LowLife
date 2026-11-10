# -*- coding: utf-8 -*-
"""
Revit-часть кнопки «Проверка орфографии» (Tools.panel/SpellCheck): сбор
заметок, названий листов, штампов, типовых аннотаций и ручных таблиц.

Исправление пишется точечно: в FormattedText заметки заменяются только
изменённые слова (spellcheck_core.replacement_spans), поэтому жирный /
курсив / подчёркивание, списки и размеры остального текста сохраняются.
Если точечная запись не удалась или дала не тот текст — текст заметки
записывается целиком (TextNote.Text), форматирование заметки тогда
сбрасывается; это отмечается в отчёте.
"""

from Autodesk.Revit.DB import (
    FilteredElementCollector, TextNote, TextRange, ElementId,
    WorksharingUtils, CheckoutStatus, ModelUpdatesStatus,
    FamilyInstance, ViewSheet, Viewport, BuiltInParameter, BuiltInCategory, StorageType,
    ViewSchedule, ScheduleSheetInstance, SectionType
)
from lowlife.i18n import tr
from lowlife.params import param_to_text, set_param_text
from lowlife.link_views import safe_name
from lowlife import schedule_excel

from lowlife import spellcheck_core as core

SCOPE_SELECTION = "selection"
SCOPE_VIEW = "view"
SCOPE_SHEETS = "sheets"
SCOPE_MODEL = "model"

# Итог apply_fix
APPLIED_FORMATTED = "formatted"
APPLIED_PLAIN = "plain"
APPLIED_PARAMETER = "parameter"


class TextTarget(object):
    """Точное место записи: заметка или конкретный параметр владельца."""
    def __init__(self, element, kind, parameter=None, cell=None):
        self.element = element
        self.kind = kind
        self.parameter = parameter
        self.cell = cell
        self.Id = element.Id

    @property
    def field(self):
        if self.kind == "note":
            return tr(u"Текстовые заметки", u"Text notes")
        if self.kind == "sheet":
            return tr(u"Названия листов", u"Sheet names")
        if self.cell is not None:
            return tr(u"Ручная таблица: строка {}, столбец {}",
                      u"Manual table: row {}, column {}").format(self.cell[0] + 1, self.cell[1] + 1)
        level = (tr(u"Тип — все экземпляры", u"Type — all instances")
                 if self.kind == "type" else tr(u"Экземпляр", u"Instance"))
        return u"{}: {}".format(level, self.parameter.Definition.Name)

    @property
    def label(self):
        return u"{} — {} [ {} ]".format(self.field, safe_name(self.element), self.Id)


def sheet_scope_view_ids(doc, sheets):
    """Идентификаторы видов для полного обхода листов: сам лист плюс виды
    во всех размещённых на нём видовых экранах (включая легенды и узлы)."""
    ids = []
    for sheet in sheets:
        ids.append(sheet.Id)
        for viewport in FilteredElementCollector(doc, sheet.Id).OfClass(Viewport):
            ids.append(viewport.ViewId)
    return ids


def collect_targets(doc, scope, view=None, selected=None, kinds=None, sheets=None):
    """Тексты документа: заметки, листы, штампы, типовые аннотации, ручные таблицы.

    На листе проверяется его имя, а семейства/заметки — видимые на самом
    листе, без обхода размещённых видовых экранов. Тип проверяется один раз.
    Область SCOPE_SHEETS обходит листы вместе с видами в их видовых экранах
    (`sheets` — выбранные листы), остальные области `sheets` не используют."""
    kinds = set(kinds if kinds is not None else ("note", "sheet", "titleblock", "annotation", "schedule"))
    selected = list(selected or [])
    sheets = list(sheets or [])
    result = []
    if "note" in kinds:
        if scope == SCOPE_SHEETS:
            notes = []
            seen = set()
            for view_id in sheet_scope_view_ids(doc, sheets):
                collector = FilteredElementCollector(doc, view_id)
                for note in collector.OfClass(TextNote).WhereElementIsNotElementType():
                    if note.Id not in seen:
                        seen.add(note.Id)
                        notes.append(note)
        else:
            notes = collect_text_notes(doc, scope, view,
                                       [e for e in selected if isinstance(e, TextNote)])
        result.extend(TextTarget(e, "note") for e in notes)
    if "sheet" in kinds:
        if scope == SCOPE_SHEETS:
            sheet_list = sheets
        elif scope == SCOPE_SELECTION:
            sheet_list = [e for e in selected if isinstance(e, ViewSheet)]
        elif scope == SCOPE_VIEW:
            sheet_list = [view] if isinstance(view, ViewSheet) else []
        else:
            sheet_list = FilteredElementCollector(doc).OfClass(ViewSheet)
        for sheet in sheet_list:
            p = sheet.get_Parameter(BuiltInParameter.SHEET_NAME)
            if p is not None:
                result.append(TextTarget(sheet, "sheet", p))
    for source, category in (("titleblock", BuiltInCategory.OST_TitleBlocks),
                             ("annotation", BuiltInCategory.OST_GenericAnnotation)):
        if source not in kinds:
            continue
        if scope == SCOPE_SELECTION:
            instances = [e for e in selected if isinstance(e, FamilyInstance)
                         and e.Category is not None and e.Category.Id == ElementId(category)]
        elif scope == SCOPE_SHEETS:
            instances = []
            seen = set()
            for view_id in sheet_scope_view_ids(doc, sheets):
                collector = FilteredElementCollector(doc, view_id)
                found = collector.OfCategory(category).OfClass(FamilyInstance).WhereElementIsNotElementType()
                for instance in found:
                    if instance.Id not in seen:
                        seen.add(instance.Id)
                        instances.append(instance)
        else:
            collector = (FilteredElementCollector(doc, view.Id)
                         if scope == SCOPE_VIEW and view is not None
                         else FilteredElementCollector(doc))
            instances = collector.OfCategory(category).OfClass(FamilyInstance).WhereElementIsNotElementType()
        seen = set()
        for instance in instances:
            for owner, kind in ((instance, "instance"),
                                (doc.GetElement(instance.GetTypeId()), "type")):
                if owner is None or owner.Id in seen:
                    continue
                seen.add(owner.Id)
                for p in owner.Parameters:
                    if p.StorageType == StorageType.String and not p.IsReadOnly:
                        if core.has_letters(p.AsString()):
                            result.append(TextTarget(owner, kind, p))
    if "schedule" in kinds:
        if scope == SCOPE_MODEL:
            schedules = schedule_excel.list_schedules(doc)
        else:
            if scope == SCOPE_SHEETS:
                elements = []
                for sheet in sheets:
                    elements.extend(FilteredElementCollector(doc, sheet.Id).OfClass(ScheduleSheetInstance))
            else:
                elements = selected if scope == SCOPE_SELECTION else [view]
                if scope == SCOPE_VIEW and isinstance(view, ViewSheet):
                    elements = FilteredElementCollector(doc, view.Id).OfClass(ScheduleSheetInstance)
            schedules = []
            seen = set()
            for element in elements:
                sched = (doc.GetElement(element.ScheduleId)
                         if isinstance(element, ScheduleSheetInstance) else element)
                if isinstance(sched, ViewSchedule) and sched.Id not in seen:
                    if not sched.IsTemplate and not sched.IsTitleblockRevisionSchedule:
                        schedules.append(sched)
                        seen.add(sched.Id)
        for sched in schedules:
            first_col = sched.GetTableData().GetSectionData(SectionType.Header).FirstColumnNumber
            for row, token, texts in schedule_excel.manual_header_rows(sched):
                for j, text in enumerate(texts):
                    if core.has_letters(text):
                        result.append(TextTarget(sched, "schedule", cell=(row, first_col + j, j, token)))
    return result


def plain_text(note):
    """Текст заметки так, как его видит FormattedText (с "\\r" между строками)."""
    if isinstance(note, TextTarget):
        if note.cell is not None:
            return note.element.GetCellText(SectionType.Header, note.cell[0], note.cell[1])
        if note.parameter is not None:
            return param_to_text(note.parameter)
        note = note.element
    try:
        return note.GetFormattedText().GetPlainText()
    except Exception:
        return note.Text or u""


def selected_text_notes(doc, uidoc):
    notes = []
    for element_id in uidoc.Selection.GetElementIds():
        element = doc.GetElement(element_id)
        if isinstance(element, TextNote):
            notes.append(element)
    return notes


def collect_text_notes(doc, scope, view=None, selected=None):
    """Заметки модели: выделенные, на виде или во всём документе (на всех
    видах и листах; связанные файлы не читаются)."""
    if scope == SCOPE_SELECTION:
        return list(selected or [])
    if scope == SCOPE_VIEW and view is not None:
        collector = FilteredElementCollector(doc, view.Id)
    else:
        collector = FilteredElementCollector(doc)
    return list(collector.OfClass(TextNote).WhereElementIsNotElementType())


def skip_reason(doc, note):
    """Почему заметку нельзя править (текст для отчёта) или None.

    Заметки в группах не трогаем: правка члена группы вне режима
    редактирования группы даёт предупреждение Revit о группе. В
    совместной модели чужие и устаревшие (изменены в центральной) элементы
    уронили бы при сохранении всю транзакцию — их тоже пропускаем."""
    if isinstance(note, TextTarget):
        if note.parameter is not None and note.parameter.IsReadOnly:
            return tr(u"Параметр доступен только для чтения", u"The parameter is read-only")
        note = note.element
    try:
        if note.GroupId is not None and note.GroupId != ElementId.InvalidElementId:
            return tr(u"в группе")
    except Exception:
        pass
    if not doc.IsWorkshared:
        return None
    try:
        if WorksharingUtils.GetCheckoutStatus(doc, note.Id) == CheckoutStatus.OwnedByOtherUser:
            return tr(u"занята другим пользователем")
        if WorksharingUtils.GetModelUpdatesStatus(doc, note.Id) in (
                ModelUpdatesStatus.UpdatedInCentral, ModelUpdatesStatus.DeletedInCentral):
            return tr(u"изменена в центральной модели — синхронизируйтесь")
    except Exception:
        pass
    return None


def apply_fix(note, old_plain, new_plain):
    """Пишет исправление в заметку (внутри открытой транзакции).
    Возвращает APPLIED_FORMATTED или APPLIED_PLAIN; бросает исключение, если
    текст заметки успел измениться или Revit запись не принял."""
    if plain_text(note) != old_plain:
        raise ValueError(tr(u"текст заметки изменился после проверки"))

    if isinstance(note, TextTarget):
        reason = skip_reason(note.element.Document, note)
        if reason:
            raise ValueError(reason)
        if note.cell is not None:
            result = schedule_excel.rows_to_model(note.element.Document, [
                [schedule_excel.ID_HEADER, schedule_excel.CELL_PREFIX + str(note.cell[2] + 1)],
                [note.cell[3], new_plain]])
            if result['errors'] or result['changed'] != 1:
                raise ValueError(u"; ".join(result['errors']) or tr(u"Не удалось записать параметр", u"Could not write the parameter"))
            return APPLIED_PARAMETER
        if note.parameter is not None:
            if not set_param_text(note.parameter, new_plain):
                raise ValueError(tr(u"Не удалось записать параметр", u"Could not write the parameter"))
            return APPLIED_PARAMETER
        note = note.element

    spans = core.replacement_spans(old_plain, new_plain)
    try:
        formatted = note.GetFormattedText()
        for start, length, text in sorted(spans, reverse=True):
            formatted.SetPlainText(TextRange(start, length), text)
        if formatted.GetPlainText() == new_plain:
            note.SetFormattedText(formatted)
            return APPLIED_FORMATTED
    except Exception:
        pass

    # Завершающий "\r" Revit добавляет к тексту сам
    note.Text = new_plain.rstrip(u"\r\n")
    return APPLIED_PLAIN
