# -*- coding: utf-8 -*-
"""pyRevit output for the route quantity report."""
from lowlife.i18n import tr


def print_report(output, package, total, processed, parameter_names, sections):
    output.print_md(tr(u"# Подсчёт длин и способов прокладки", u"# Route lengths and methods"))
    output.print_md(tr(u"**Выбранный комплект:** {}", u"**Selected package:** {}").format(package))
    output.print_table(table_data=[
        [tr(u"Всего электрических цепей в проекте", u"Electrical circuits in project"), total],
        [tr(u"Цепей выбранного комплекта", u"Circuits in selected package"), processed],
    ], columns=[tr(u"Показатель", u"Metric"), tr(u"Значение", u"Value")])
    titles = [
        tr(u"1. Подсчёт по параметру «Способ прокладки»",
           u"1. Calculation using the Route method parameter"),
        tr(u"2. Подсчёт по параметру «Способ прокладки с запасом»",
           u"2. Calculation using the Route method with reserve parameter"),
    ]
    # Input sections arrive with reserve first; show the base quantities first.
    for title, index in zip(titles, (1, 0)):
        parameter_name, data = parameter_names[index], sections[index]
        output.print_md(u"## " + title)
        output.print_md(tr(u"**Параметр:** {}", u"**Parameter:** {}").format(parameter_name))
        output.print_table(table_data=[
            [tr(u"Цепей с заполненным параметром", u"Circuits with a filled parameter"), data["chains_with_route"]],
            [tr(u"Найдено обозначений", u"Notations found"), data["parsed_items"]],
            [tr(u"Количество групп материалов", u"Material groups"), data["groups_count"]],
            [tr(u"Заполненных цепей без распознанных обозначений", u"Filled circuits with no recognized notations"), data["unmatched"]],
        ], columns=[tr(u"Показатель", u"Metric"), tr(u"Значение", u"Value")])
        if data["result"]:
            output.print_table(table_data=data["result"], columns=[
                tr(u"Тип прокладки / размер", u"Route method / size"),
                tr(u"Длина, м", u"Length, m"),
            ])
        else:
            output.print_md(tr(u"**По этому параметру обозначения не найдены.**",
                               u"**No notations found in this parameter.**"))
