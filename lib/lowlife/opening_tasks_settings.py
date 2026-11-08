# -*- coding: utf-8 -*-
"""Settings for VIS/KR opening exchange. Project parameter names stay blank."""
from lowlife import settings_core as sc
from lowlife import tray_boxes_settings as trays
from lowlife import opening_tasks_manifest as manifest
from lowlife.i18n import N_, tr


def make(role, doc=None):
    manifest.validate_role(role)
    common = [
        sc.TextField('opening_project_param', u'Обмен заданиями', u'Параметр шифра объекта',
                     hint=u'Параметр в «Сведениях о проекте», содержащий шифр объекта. Пусто — стандартный «Номер проекта». Настройка независима от других инструментов.'),
        sc.TextField('opening_json_param', u'', u'JSON-параметр задания',
                     hint=(N_(u'Обязательный текстовый параметр экземпляра бокса: хранит описание задания, GUID, размеры и ревизию.') if role=='VIS' else
                           N_(u'Можно оставить пустым. Если текстовый параметр доступен у проёма, в него дополнительно записывается описание. Связь с заданием сохраняется автоматически.')), required=(role == 'VIS')),
    ]
    if role == 'VIS':
        fields = common + [sc.TextField('opening_discipline', u'', u'Дисциплина ВИС',
                     hint=u'Дисциплина для номера задания и журнала ГИПа. При установленном подключении отдел определяется по токену автоматически и используется вместо этого поля.', required=True)]
        fields += [sc.ChoiceField('opening_increase', u'', u'Дополнительно по ЗНП',
                    [('none', u'Без увеличения'), ('auto', u'Автоматически'),
                     ('50', u'+50 мм'), ('100', u'+100 мм'), ('150', u'+150 мм'), ('200', u'+200 мм')],
                    hint=u'Добавка к обоим размерам сечения: +50 мм увеличивает каждый размер на 50 мм, по 25 мм с каждой стороны. Авто: большая сторона до 300 мм — +50, свыше 300 — +100, свыше 600 до 1200 включительно — +150, свыше 1200 — +200. Толщина конструкции не увеличивается.')]
        fields += [sc.TextField(key, u'Фиксация выдачи', label, hint=hint, required=(key=='opening_status_param'))
                   for key,label,hint in [
                       ('opening_status_param',N_(u'Параметр статуса выдачи'),N_(u'Текстовый параметр экземпляра бокса для статуса: черновик, выдано, изменено после выдачи или отозвано. Можно включить в спецификации и фильтры.')),
                       ('opening_issue_param',N_(u'Параметр номера выпуска'),N_(u'Текстовый параметр экземпляра бокса для номера выпуска. Заполняется автоматически при выдаче или перевыдаче.')),
                       ('opening_revision_param',N_(u'Параметр ревизии задания'),N_(u'Текстовый параметр экземпляра бокса для ревизии. При перевыдаче изменённого задания номер ревизии увеличивается.')),
                       ('opening_date_param',N_(u'Параметр даты выдачи'),N_(u'Текстовый параметр экземпляра бокса для даты и времени выдачи в UTC. Дата отправки в Google фиксируется отдельно.'))]]
        replacements = {
            'size_extra_mm': sc.NumberField('size_extra_mm', u'③ Размеры', u'Запас по EIR с каждой стороны, мм',
                                            hint=u'Запас добавляется к габариту элемента ВИС с каждой стороны.', default=50.0, minimum=0.0),
            'max_wall_angle_deg': sc.NumberField('max_wall_angle_deg', u'', u'Максимальный угол прохода к нормали стены, градусы',
                                                hint=u'0° — проход перпендикулярно стене. Если угол к нормали больше заданного, пересечение пропускается.',
                                                default=60.0, minimum=0.0),
        }
        fields += [replacements.get(f.key,f) for f in trays._make_settings([]).fields if f.key not in ('box_source_model','max_slope_deg')]
    else:
        fields = common
    hints={
        'box_hosts':N_(u'Выберите, где создавать задания: в стенах, перекрытиях или обоих типах конструкций выбранной модели.'),
        'box_width_param':N_(u'Параметр ширины семейства бокса: в стене — вдоль стены, в перекрытии — вдоль ширины инженерного элемента.'),
        'box_depth_param':N_(u'Параметр глубины семейства бокса: в стене — по толщине стены, в перекрытии — второй размер сечения инженерного элемента.'),
        'box_height_param':N_(u'Параметр высоты семейства бокса: в стене — высота отверстия, в перекрытии — толщина конструкции. Для параметров типа создаётся отдельный типоразмер.'),
    }
    for field in fields:
        if field.key in ('opening_issue_param','opening_revision_param','opening_date_param'):
            field.hint=tr(u'Необязательно. Можно оставить пустым: данные сохраняются в JSON, интерфейсе и Google-журнале. Заполните только для отдельного столбца спецификации Revit.',
                          u'Optional. Leave blank: data remains in JSON, the interface and Google journal. Fill only for a separate Revit schedule column.')
        if field.key in hints:
            field.hint=hints[field.key]
    form=sc.TextSettings('LowLifeOpeningTasks' + role + '_settings.json',
                           N_(u'Задания ВИС') if role == 'VIS' else N_(u'Задания КР') if role=='KR' else N_(u'Задания АР'),
                           u'Задания на отверстия', u'заданий на отверстия', fields,
                           width=780, height=700)
    if role=='VIS' and doc is not None:
        form.migrate=lambda saved,values:values.update(opening_discipline=for_document(values,doc)['opening_discipline'])
    return form


def project_code(doc,settings):
    ref=settings.get('opening_project_param','').strip()
    if ref:
        from lowlife.params import read_project_parameter
        return read_project_parameter(doc,ref)
    return (doc.ProjectInformation.Number or '').strip()


def for_document(settings,doc):
    value=dict(settings)
    value['opening_project']=project_code(doc,value)
    if 'opening_discipline' in value:
        from lowlife import opening_tasks_journal as journal
        connection=journal.connection_value(value['opening_project'],'VIS',doc.ProjectInformation.UniqueId) or {}
        discipline=manifest.canonical_discipline(connection.get('discipline',''))
        if manifest.INSTALL_DISCIPLINES.get(discipline)=='VIS':
            value['opening_discipline']=discipline
    return value
