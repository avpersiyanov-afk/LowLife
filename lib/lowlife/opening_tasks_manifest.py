# -*- coding: utf-8 -*-
"""Authoritative ribbon entry points and role-specific opening task actions."""
from lowlife.i18n import N_, tr

VERSION=21
INTERFACES={'VIS':'VISInterface','KR':'KRInterface','AR':'ARInterface'}
INSTALL_DISCIPLINES={u'ОВиК':'VIS',u'ВК':'VIS',u'ЭОМ':'VIS',u'СС':'VIS',u'АК':'VIS',u'КР':'KR',u'АР':'AR'}
COMMON=('highlight','refresh','settings','journal_setup','journal_open','parts_refresh')
ACTIONS={
    'VIS': (
        ('place',N_(u'Расставить боксы')),
        ('issue',N_(u'Выдать задания ВИС-КР')),
        ('place_ar',N_(u'Боксы для АР')),
        ('issue_ar',N_(u'Выдать задания ВИС-АР')),
        ('confirm_ar',N_(u'Подтвердить результат АР')),
        ('withdraw',N_(u'Отозвать')),
        ('confirm',N_(u'Подтвердить результат')),
        ('focus',N_(u'Бокс в 3D')),
        ('control',N_(u'Виды и реестр')),
    ),
    'AR': (
        ('ar_show',N_(u'Показать конструкцию АР')),
        ('ar_accept',N_(u'Принять задания АР')),
        ('ar_merge',N_(u'Объединить АР')),
        ('ar_reject',N_(u'Замечание АР')),
        ('ar_remove',N_(u'Отработать отзыв АР')),
    ),
    'KR': (
        ('show',N_(u'Показать конструкцию')),
        ('accept',N_(u'Принять задания КР')),
        ('merge',N_(u'Объединить')),
        ('reject',N_(u'Замечание')),
        ('remove',N_(u'Отработать отзыв')),
        ('structures',N_(u'Вид конструкций')),
        ('kr_plans',N_(u'Планы плит')),
        ('kr_sections',N_(u'Разрезы стен')),
    ),
}


# Ordered workflow groups; action identities and role permissions stay unchanged.
ACTION_GROUPS={
    'VIS': ((N_(u'Задания КР'),('place','issue','confirm')),
            (N_(u'Задания АР'),('place_ar','issue_ar','confirm_ar')),
            (N_(u'Контроль'),('highlight','focus','control','withdraw'))),
    'KR': ((N_(u'Принятие'),('show','accept','merge','reject','remove')),
           (N_(u'Виды'),('highlight','structures','kr_plans','kr_sections'))),
    'AR': ((N_(u'Принятие'),('highlight','ar_show','ar_accept','ar_merge','ar_reject','ar_remove')),),
}


def action_groups(role):
    return ACTION_GROUPS[validate_role(role)]+(
        (N_(u'Обмен'),('refresh','journal_open')),
        (N_(u'Настройки'),('settings','parts_refresh','journal_setup')))


def validate_role(role):
    if role not in INTERFACES:
        raise ValueError(tr(u'Неизвестная роль интерфейса: {}',u'Unknown interface role: {}').format(role))
    return role


def actions(role):
    return ACTIONS[validate_role(role)]


def validate_action(role,action):
    allowed=set(key for key,label in actions(role))|set(COMMON)
    if action not in allowed:
        raise ValueError(tr(u'Действие «{}» недоступно роли {}.',u'Action {} is not available to role {}.').format(action,role))
    return action


def action_hint(action):
    return {
        'highlight':tr(u'Открыть ранее созданный вид контроля и выделить выбранные боксы или проёмы. Если подходящих видов несколько, предложить выбор.',
                       u'Open an existing control view and select the chosen boxes or openings. Choose a view when several are suitable.'),
        'refresh':tr(u'Перечитать задания и ответы из уже загруженных связей. Перед этим обновите связи штатной командой Revit.',
                     u'Read tasks and responses from the currently loaded links. Reload links in Revit first.'),
        'settings':tr(u'Настройки текущей роли. Под каждым полем есть пояснение; имена параметров выбираются с подсказками.',
                      u'Settings for the current role. Each field has an explanation; parameter names have suggestions.'),
        'journal_setup':tr(u'Подключение Google-журнала: адрес Apps Script и токен отдела. Каждый пользователь настраивает один раз для всех своих моделей. Внутри есть инструкция.',
                           u'Google journal connection: Apps Script URL and department token. Each user configures it once for all their models. Includes a setup guide.'),
        'journal_open':tr(u'Открыть Google-журнал в браузере. Задания отправляются автоматически; для просмотра нужен доступ к таблице.',
                          u'Open the Google journal in your browser. Tasks are sent automatically; viewing requires sheet access.'),
        'parts_refresh':tr(u'Загрузить из Google НЧ/ПЧ и номера корпусов или секций текущего объекта. Без сети используется сохранённый список.',
                           u'Load the current project parts and building or section numbers from Google. Cached choices are used offline.'),
    }.get(action,'')


def canonical_discipline(value):
    value=(value or '').strip()
    return u'ОВиК' if value.upper() in (u'ОВИК',u'ОК') else value
