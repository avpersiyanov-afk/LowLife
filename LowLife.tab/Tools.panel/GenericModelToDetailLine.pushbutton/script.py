# -*- coding: utf-8 -*-

__title__ = u"Обобщённые модели\nв аннотации"
__doc__ = u"Преобразует выбранные линейные обобщённые модели в линии аннотаций активного вида."
__author__ = "Pipers"

from pyrevit import revit, forms
from lowlife.i18n import tr
from lowlife.generic_model_lines import convert_to_detail_lines

elements = list(revit.get_selection().elements)
if not elements:
    forms.alert(tr(u"Выберите линейные обобщённые модели и повторите запуск.", u"Select line-based generic models and run the button again."),
                title=tr(u"Обобщённые модели в аннотации", u"Generic models to detail lines"), exitscript=True)

try:
    with revit.Transaction(tr(u"Обобщённые модели в аннотации", u"Generic models to detail lines")):
        result = convert_to_detail_lines(revit.doc, revit.doc.ActiveView, elements)
except Exception as error:
    forms.alert(tr(u"Не удалось преобразовать линии.\n\n{}", u"Could not convert the lines.\n\n{}").format(error),
                title=tr(u"Обобщённые модели в аннотации", u"Generic models to detail lines"), exitscript=True)

message = tr(u"Преобразовано линий: {}\nПропущено элементов: {}", u"Lines converted: {}\nElements skipped: {}").format(
    result["converted"], result["skipped"])
if result["errors"]:
    message += tr(u"\n\nПричины пропуска:\n{} ", u"\n\nSkip reasons:\n{} ").format(
        u"\n".join(result["errors"][:5]))
forms.alert(message, title=tr(u"Обобщённые модели в аннотации", u"Generic models to detail lines"))

