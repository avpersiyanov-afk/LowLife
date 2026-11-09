# -*- coding: utf-8 -*-
"""Saved name masks for the local datum panel."""
from lowlife import settings_core
from lowlife.i18n import N_, tr
from lowlife import datum_filter_core as core


class MaskField(settings_core.TextField):
    def parse(self, text):
        try:
            core.compile_mask(text)
        except ValueError:
            return None, tr(u'Проверьте маски: фигурные скобки должны быть парными, названия частей — непустыми и разными.')
        return text, None

HINT = N_(u'Маска полного имени: * — любой текст, ? — один символ. Части в фигурных скобках образуют группу: {корпус}_{секция}_*. Без скобок — отдельная строка для каждого имени. Несовпавшие имена не изменяются.')

SETTINGS = settings_core.TextSettings(
    file_name='LowLifeDatumFilter_settings.json',
    button_name=N_(u'Фильтр осей и уровней'),
    heading=N_(u'Группировка осей и уровней по имени'),
    transfer_label=N_(u'фильтра осей и уровней'),
    fields=[
        MaskField('grid_mask', N_(u'Оси'), N_(u'Маска имени оси'),
                                hint=HINT, default=u'*', required=False),
        MaskField('level_mask', N_(u'Уровни'), N_(u'Маска имени уровня'),
                                hint=HINT, default=u'*', required=False),
    ], width=740, height=530)
