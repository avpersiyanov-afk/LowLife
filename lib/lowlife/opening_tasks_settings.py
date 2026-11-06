# -*- coding: utf-8 -*-
"""Settings for VIS/KR opening exchange. Project parameter names stay blank."""
from lowlife import settings_core as sc
from lowlife import tray_boxes_settings as trays
from lowlife import opening_tasks_manifest as manifest
from lowlife.i18n import N_


def make(role, doc=None):
    manifest.validate_role(role)
    common = [
        sc.TextField('opening_project_param', u'Обмен заданиями', u'Параметр шифра объекта',
                     hint=u'Пусто — параметр шифра из настройки «Заметок», затем стандартный «Номер проекта».'),
        sc.TextField('opening_json_param', u'', u'JSON-параметр задания',
                     hint=(N_(u'Обязательный текстовый параметр экземпляра бокса: хранит описание задания, GUID, размеры и ревизию.') if role=='VIS' else
                           N_(u'Можно оставить пустым. Если текстовый параметр доступен у проёма, в него дополнительно записывается описание. Связь с заданием сохраняется автоматически.')), required=(role == 'VIS')),
    ]
    if role == 'VIS':
        fields = common + [sc.TextField('opening_discipline', u'', u'Дисциплина ВИС',
                     hint=u'Обозначение вашей дисциплины, например ОВ, ВК или ЭОМ. Используется в номере задания и журнале ГИПа.', required=True)]
        fields += [sc.ChoiceField('opening_increase', u'', u'Дополнительно по ЗНП',
                    [('none', u'Без увеличения'), ('auto', u'Автоматически'),
                     ('50', u'+50 мм'), ('100', u'+100 мм'), ('150', u'+150 мм')],
                    hint=u'Добавка к обоим размерам сечения: +50 мм увеличивает каждый размер на 50 мм, по 25 мм с каждой стороны. Авто: большая сторона до 300 мм — +50, свыше 300 — +100, свыше 600 — +150. Толщина конструкции не увеличивается.')]
        fields += [sc.TextField(key, u'Фиксация выдачи', label, hint=hint, required=True)
                   for key,label,hint in [
                       ('opening_status_param',N_(u'Параметр статуса выдачи'),N_(u'Текстовый параметр экземпляра бокса для статуса: черновик, выдано, изменено после выдачи или отозвано. Можно включить в спецификации и фильтры.')),
                       ('opening_issue_param',N_(u'Параметр номера выпуска'),N_(u'Текстовый параметр экземпляра бокса для номера выпуска. Заполняется автоматически при выдаче или перевыдаче.')),
                       ('opening_revision_param',N_(u'Параметр ревизии задания'),N_(u'Текстовый параметр экземпляра бокса для ревизии. При перевыдаче изменённого задания номер ревизии увеличивается.')),
                       ('opening_date_param',N_(u'Параметр даты выдачи'),N_(u'Текстовый параметр экземпляра бокса для даты и времени выдачи в UTC. Дата отправки в Google фиксируется отдельно.'))]]
        replacements = {
            'size_extra_mm': sc.NumberField('size_extra_mm', u'③ Размеры', u'Запас по EIR с каждой стороны, мм',
                                            hint=u'Запас добавляется к габариту элемента ВИС с каждой стороны.', default=50.0, minimum=0.0),
            'max_slope_deg': sc.NumberField('max_slope_deg', u'', u'Допуск наклона участка ВИС, градусы',
                                            hint=u'Через стены — горизонтальные участки, через перекрытия — вертикальные.', default=1.0, minimum=0.0),
            'max_wall_angle_deg': sc.NumberField('max_wall_angle_deg', u'', u'Максимальный угол прохода к нормали стены, градусы',
                                                hint=u'0° — проход перпендикулярно стене. Если угол к нормали больше заданного, пересечение пропускается.',
                                                default=60.0, minimum=0.0),
        }
        fields += [replacements.get(f.key,f) for f in trays._make_settings([]).fields if f.key != 'box_source_model']
    else:
        fields = common
    hints={
        'box_hosts':N_(u'Выберите, где создавать задания: в стенах, перекрытиях или обоих типах конструкций выбранной модели.'),
        'box_width_param':N_(u'Параметр ширины семейства бокса: в стене — вдоль стены, в перекрытии — вдоль ширины инженерного элемента.'),
        'box_depth_param':N_(u'Параметр глубины семейства бокса: в стене — по толщине стены, в перекрытии — второй размер сечения инженерного элемента.'),
        'box_height_param':N_(u'Параметр высоты семейства бокса: в стене — высота отверстия, в перекрытии — толщина конструкции. Для параметров типа создаётся отдельный типоразмер.'),
    }
    for field in fields:
        if field.key in hints:
            field.hint=hints[field.key]
    return sc.TextSettings('LowLifeOpeningTasks' + role + '_settings.json',
                           N_(u'Задания ВИС') if role == 'VIS' else N_(u'Задания КР') if role=='KR' else N_(u'Задания АР'),
                           u'Задания на отверстия', u'заданий на отверстия', fields,
                           width=780, height=700)


def project_code(doc,settings):
    # Reuse Notes references: custom parameter names and built-ins [BIP_NAME].
    # Reading the Notes cache is local and must never initiate a network request.
    from pnotes import core as notes
    ref=settings.get('opening_project_param','').strip()
    if not ref:
        ref=notes.get_settings(online=False)[0].get('key_param','')
    if ref and ref!=notes.FILE_KEY:
        return notes.read_param(doc,ref)
    return (doc.ProjectInformation.Number or '').strip()


def for_document(settings,doc):
    value=dict(settings)
    value['opening_project']=project_code(doc,value)
    return value
