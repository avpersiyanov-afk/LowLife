# -*- coding: utf-8 -*-
"""Authoritative ribbon entry points and role-specific opening task actions."""
from lowlife.i18n import N_, tr

VERSION=7
INTERFACES={'VIS':'VISInterface','KR':'KRInterface','AR':'ARInterface'}
COMMON=('refresh','settings','journal_setup','journal_open')
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
