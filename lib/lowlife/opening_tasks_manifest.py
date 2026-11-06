# -*- coding: utf-8 -*-
"""Authoritative ribbon entry points and role-specific opening task actions."""
from lowlife.i18n import N_, tr

VERSION=2
INTERFACES={'VIS':'VISInterface','KR':'KRInterface'}
COMMON=('refresh','settings')
ACTIONS={
    'VIS': (
        ('place',N_(u'Расставить боксы')),
        ('issue',N_(u'Выдать задания')),
        ('withdraw',N_(u'Отозвать')),
        ('confirm',N_(u'Подтвердить результат')),
        ('focus',N_(u'Бокс в 3D')),
        ('control',N_(u'Виды и реестр')),
    ),
    'KR': (
        ('show',N_(u'Показать конструкцию')),
        ('accept',N_(u'Принять отдельно')),
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
