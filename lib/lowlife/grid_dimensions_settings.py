# -*- coding: utf-8 -*-
"""Настройки автоматического образмеривания осей."""

from lowlife import settings_core
from lowlife.i18n import N_


SETTINGS = settings_core.TextSettings(
    file_name="LowLifeGridDimensions_settings.json",
    button_name=N_(u"Размеры осей"),
    heading=N_(u"Поиск осей на плане и отступы размеров"),
    transfer_label=N_(u"размеров осей"),
    fields=[
        settings_core.TextField(
            "grid_name_mask", N_(u"Поиск осей"), N_(u"Маска маркировки осей"),
            hint=N_(u"* — любые символы, ? — один символ, [0-9] — цифра, [А-Я] — русская буква. "
                    u"Несколько масок через ;, например [0-9]*;[А-Я]*. * — все оси. "
                    u"Первая и последняя ось определяются по маркировке отдельно для каждого направления: 2 раньше 10."),
            default=u"*", required=True),
        settings_core.NumberField(
            "offset_mm", N_(u"Отступы"), N_(u"Отступ цепочки от концов осей, мм"),
            default=1400.0, minimum=0.0),
        settings_core.NumberField(
            "total_gap_mm", N_(u"Отступы"), N_(u"Отступ общего размера от цепочки, мм"),
            default=700.0, minimum=1.0),
    ], height=520,
)

get_settings_interactive = SETTINGS.get_settings_interactive
get_settings_silent = SETTINGS.get_settings_silent
require = SETTINGS.require
