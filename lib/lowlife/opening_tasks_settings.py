# -*- coding: utf-8 -*-
"""Settings for VIS/KR opening exchange. Project parameter names stay blank."""
from lowlife import settings_core as sc
from lowlife import tray_boxes_settings as trays
from lowlife import opening_tasks_manifest as manifest


def make(role, doc=None):
    manifest.validate_role(role)
    common = [
        sc.TextField('opening_project', u'Обмен заданиями', u'Код проекта', required=True),
        sc.TextField('opening_json_param', u'', u'JSON-параметр задания',
                     hint=u'Текстовый параметр экземпляра бокса. Имя задаётся для проекта.', required=(role == 'VIS')),
    ]
    if role == 'VIS':
        fields = common + [sc.TextField('opening_discipline', u'', u'Дисциплина ВИС', required=True)]
        fields += [sc.ChoiceField('opening_increase', u'', u'Дополнительно по ЗНП',
                    [('none', u'Без увеличения'), ('auto', u'Автоматически'),
                     ('50', u'+50 мм'), ('100', u'+100 мм'), ('150', u'+150 мм')])]
        fields += [sc.TextField(key, u'Фиксация выдачи', label, required=True)
                   for key,label in [
                       ('opening_status_param',u'Параметр статуса выдачи'),
                       ('opening_issue_param',u'Параметр номера выпуска'),
                       ('opening_revision_param',u'Параметр ревизии задания'),
                       ('opening_date_param',u'Параметр даты выдачи')]]
        replacements = {
            'size_extra_mm': sc.NumberField('size_extra_mm', u'③ Размеры', u'Запас по EIR с каждой стороны, мм',
                                            hint=u'Запас добавляется к габариту элемента ВИС с каждой стороны.', default=50.0, minimum=0.0),
            'max_slope_deg': sc.NumberField('max_slope_deg', u'', u'Допуск наклона участка ВИС, градусы',
                                            hint=u'Через стены — горизонтальные участки, через перекрытия — вертикальные.', default=1.0, minimum=0.0),
            'max_wall_angle_deg': sc.NumberField('max_wall_angle_deg', u'', u'Максимальный угол прохода к нормали стены, градусы',
                                                default=60.0, minimum=0.0),
        }
        fields += [replacements.get(f.key,f) for f in trays._make_settings([]).fields if f.key != 'box_source_model']
    else:
        fields = common
    return sc.TextSettings('LowLifeOpeningTasks' + role + '_settings.json',
                           u'Задания ВИС' if role == 'VIS' else u'Задания КР' if role=='KR' else u'Задания АР',
                           u'Задания на отверстия', u'заданий на отверстия', fields,
                           width=780, height=700)
