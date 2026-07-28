# -*- coding: utf-8 -*-
"""Общие хелперы работы с выделением элементов в Revit UI."""

from pyrevit import forms


def get_single_selection(
    doc,
    uidoc,
    empty_message=u"Сначала выберите элемент в Revit, потом запустите кнопку.",
    multiple_message=u"Выберите только один элемент."
):
    """Возвращает единственный выбранный элемент либо останавливает скрипт."""
    selected_ids = uidoc.Selection.GetElementIds()

    if not selected_ids:
        forms.alert(empty_message, exitscript=True)

    if len(selected_ids) > 1:
        forms.alert(multiple_message, exitscript=True)

    el_id = list(selected_ids)[0]
    return doc.GetElement(el_id)
