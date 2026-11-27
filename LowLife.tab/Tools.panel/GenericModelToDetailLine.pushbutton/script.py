# -*- coding: utf-8 -*-

__title__ = u"Модели в\nаннотации"
__doc__ = u"Преобразует выбранные линейные обобщённые модели в линии аннотаций активного вида с выбранным стилем линий."
__author__ = "Pipers"

from pyrevit import revit, forms
from lowlife.i18n import tr
from lowlife.generic_model_lines import convert_to_detail_lines, list_line_style_options
from lowlife import select_list

elements = list(revit.get_selection().elements)
if not elements:
    forms.alert(tr(u"Выберите линейные обобщённые модели и повторите запуск.", u"Select line-based generic models and run the button again."),
                title=tr(u"Модели в аннотации", u"Models to detail lines"), exitscript=True)

style_options = list_line_style_options(
    revit.doc,
    tr(u"Сохранить стиль исходной линии", u"Keep source line style"))
if not style_options:
    forms.alert(tr(u"В проекте не найдены стили линий.", u"No line styles were found in the project."),
                title=tr(u"Модели в аннотации", u"Models to detail lines"), exitscript=True)
target_option = select_list.SelectFromList.show(
    style_options,
    title=tr(u"Выберите стиль линий", u"Select a line style"),
    button_name=tr(u"Преобразовать", u"Convert"),
    multiselect=False)
if not target_option:
    forms.alert(tr(u"Преобразование отменено.", u"Conversion cancelled."),
                title=tr(u"Модели в аннотации", u"Models to detail lines"), exitscript=True)

try:
    with revit.Transaction(tr(u"Модели в аннотации", u"Models to detail lines")):
        result = convert_to_detail_lines(
            revit.doc, revit.doc.ActiveView, elements, target_option.style)
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

