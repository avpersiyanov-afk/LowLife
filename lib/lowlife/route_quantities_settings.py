# -*- coding: utf-8 -*-
"""Project parameter names for the route quantity report."""
from lowlife import settings_core
from lowlife.i18n import N_


KEYS = ["package_param", "route_method_reserve_param", "route_method_param"]
SETTINGS = settings_core.TextSettings(
    file_name="LowLifeRouteQuantities_settings.json",
    button_name=N_(u"Подсчёт прокладки"),
    heading=N_(u"Текстовые параметры электрических цепей"),
    transfer_label=N_(u"подсчёта прокладки"),
    fields=[
        settings_core.TextField("package_param", u"", N_(u"Параметр комплекта"), required=True,
            hint=N_(
                u"Имя текстового параметра электрической цепи, содержащего название комплекта. По его "
                u"значениям выбирается комплект для отчёта; введите имя параметра, а не название "
                u"комплекта.")),
        settings_core.TextField("route_method_reserve_param", u"",
                                N_(u"Параметр способа прокладки с запасом"), required=True,
            hint=N_(
                u"Имя текстового параметра электрической цепи с описанием прокладки и длинами с запасом. "
                u"Кнопка читает записи вида «Лоток-12,5» и суммирует длины для выбранного комплекта.")),
        settings_core.TextField("route_method_param", u"",
                                N_(u"Параметр способа прокладки без запаса"), required=True,
            hint=N_(
                u"Имя текстового параметра электрической цепи с описанием прокладки и длинами без "
                u"запаса. Используется для отдельного итога исходных длин в отчёте.")),
    ],
    width=720, height=440,
)
