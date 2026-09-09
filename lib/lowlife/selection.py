# -*- coding: utf-8 -*-
"""Общие хелперы работы с выделением элементов в Revit UI."""

from pyrevit import forms

from Autodesk.Revit.DB import BuiltInCategory, CategoryType
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException


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


def _bic_ids(*names):
    """Множество int-id встроенных категорий по именам; несуществующее имя
    в этой версии Revit молча пропускается."""
    ids = set()
    for name in names:
        try:
            ids.add(int(getattr(BuiltInCategory, name)))
        except Exception:
            pass
    return ids


# То, что обычно случайно попадает в рамку выбора, но оборудованием
# модели не является. Аннотацию в целом отсекает проверка
# CategoryType.Annotation ниже; здесь — модельные/служебные категории,
# которые под неё не подпадают.
_JUNK_PICK_CATEGORY_IDS = _bic_ids(
    "OST_Grids", "OST_Levels", "OST_Lines", "OST_CLines", "OST_SketchLines",
    "OST_TextNotes", "OST_GenericAnnotation", "OST_RvtLinks",
    "OST_GenericModel",
    "OST_Rooms", "OST_MEPSpaces", "OST_Areas",
    "OST_SectionBox", "OST_Cameras", "OST_Viewers", "OST_ScopeBoxes",
)


class ModelElementSelectionFilter(ISelectionFilter):
    """
    Пропускает только элементы текущей модели, не являющиеся аннотацией
    или служебной геометрией: отсекает элементы связанных файлов, всю
    аннотацию (CategoryType.Annotation — марки, размеры, текст), оси,
    уровни, линии, опорные плоскости, обобщённые модели, вставки связей,
    помещения/зоны/площади, рамки подрезки, виды/камеры. Тот же смысл,
    что и manual_circuits._CircuitTargetSelectionFilter.
    """

    def AllowElement(self, elem):
        try:
            if elem.Document.IsLinked:
                return False
        except Exception:
            pass

        try:
            cat = elem.Category
        except Exception:
            cat = None

        if cat is None:
            return False

        try:
            if cat.Id.IntegerValue in _JUNK_PICK_CATEGORY_IDS:
                return False
        except Exception:
            pass

        try:
            if cat.CategoryType == CategoryType.Annotation:
                return False
        except Exception:
            pass

        return True

    def AllowReference(self, reference, position):
        return True


def pick_model_elements(
    uidoc,
    doc,
    prompt=u"Выберите элементы (рамкой и/или кликами), подтвердите Enter",
    cancel_message=u"Выбор отменён.",
    empty_message=u"Не выбрано ни одного элемента.",
):
    """
    Интерактивный выбор элементов модели: PickObjects с фильтром
    ModelElementSelectionFilter, поэтому рамкой не захватываются элементы
    связей, аннотация, оси/уровни/линии и прочая служебка. Останавливает
    скрипт (forms.alert exitscript) при отмене (Esc) или пустом выборе.
    Возвращает список Element.
    """
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, ModelElementSelectionFilter(), prompt
        )
    except OperationCanceledException:
        forms.alert(cancel_message, exitscript=True)
        return []

    els = [doc.GetElement(r) for r in refs]
    els = [el for el in els if el is not None]

    if not els:
        forms.alert(empty_message, exitscript=True)

    return els
