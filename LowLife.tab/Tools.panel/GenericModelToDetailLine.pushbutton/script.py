# -*- coding: utf-8 -*-

__title__ = u"Модели в\nаннотации"
__doc__ = u"Преобразует выбранные линейные обобщённые модели в линии аннотаций активного вида."
__author__ = "Pipers"

from pyrevit import revit, forms
from lowlife.i18n import tr
from lowlife.generic_model_lines import convert_to_detail_lines

elements = list(revit.get_selection().elements)
if not elements:
    forms.alert(tr(u"Выберите линейные обобщённые модели и повторите запуск.", u"Select line-based generic models and run the button again."),
                title=tr(u"Модели в аннотации", u"Models to detail lines"), exitscript=True)

try:
    with revit.Transaction(tr(u"Модели в аннотации", u"Models to detail lines")):
        result = convert_to_detail_lines(revit.doc, revit.doc.ActiveView, elements)
except Exception as error:
    forms.alert(tr(u"Не удалось преобразовать линии.\n\n{}", u"Could not convert the lines.\n\n{}").format(error),
                title=tr(u"Модели в аннотации", u"Models to detail lines"), exitscript=True)

message = tr(u"Преобразовано линий: {}\nПропущено элементов: {}", u"Lines converted: {}\nElements skipped: {}").format(
    result["converted"], result["skipped"])
if result["skipped_details"]:
    report_lines = [tr(u"\n\nОтчёт по пропущенным элементам:",
                       u"\n\nReport for skipped elements:")]
    for detail in result["skipped_details"][:50]:
        report_lines.append(u"• {} — {}".format(detail["element"], detail["reason"]))
    remaining = len(result["skipped_details"]) - 50
    if remaining > 0:
        report_lines.append(tr(u"Ещё пропущено элементов: {}", u"More elements skipped: {}").format(remaining))
    message += u"".join(report_lines)
forms.alert(message, title=tr(u"Модели в аннотации", u"Models to detail lines"))

