# -*- coding: utf-8 -*-
"""
Revit-часть кнопки «Проверка орфографии» (Tools.panel/SpellCheck): сбор
текстовых заметок (TextNote) и запись исправлений.

Исправление пишется точечно: в FormattedText заметки заменяются только
изменённые слова (spellcheck_core.replacement_spans), поэтому жирный /
курсив / подчёркивание, списки и размеры остального текста сохраняются.
Если точечная запись не удалась или дала не тот текст — текст заметки
записывается целиком (TextNote.Text), форматирование заметки тогда
сбрасывается; это отмечается в отчёте.
"""

from Autodesk.Revit.DB import (
    FilteredElementCollector, TextNote, TextRange, ElementId,
    WorksharingUtils, CheckoutStatus, ModelUpdatesStatus
)

from lowlife import spellcheck_core as core

SCOPE_SELECTION = "selection"
SCOPE_VIEW = "view"
SCOPE_MODEL = "model"

# Итог apply_fix
APPLIED_FORMATTED = "formatted"
APPLIED_PLAIN = "plain"


def plain_text(note):
    """Текст заметки так, как его видит FormattedText (с "\\r" между строками)."""
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
    try:
        if note.GroupId is not None and note.GroupId != ElementId.InvalidElementId:
            return u"в группе"
    except Exception:
        pass
    if not doc.IsWorkshared:
        return None
    try:
        if WorksharingUtils.GetCheckoutStatus(doc, note.Id) == CheckoutStatus.OwnedByOtherUser:
            return u"занята другим пользователем"
        if WorksharingUtils.GetModelUpdatesStatus(doc, note.Id) in (
                ModelUpdatesStatus.UpdatedInCentral, ModelUpdatesStatus.DeletedInCentral):
            return u"изменена в центральной модели — синхронизируйтесь"
    except Exception:
        pass
    return None


def apply_fix(note, old_plain, new_plain):
    """Пишет исправление в заметку (внутри открытой транзакции).
    Возвращает APPLIED_FORMATTED или APPLIED_PLAIN; бросает исключение, если
    текст заметки успел измениться или Revit запись не принял."""
    if plain_text(note) != old_plain:
        raise ValueError(u"текст заметки изменился после проверки")

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
