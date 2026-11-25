# -*- coding: utf-8 -*-
"""Общие настройки панелей линий трассы."""

from lowlife import settings_core
from lowlife.i18n import N_

PANELS = [
    ("call", N_(u"Устройства вызова"), u"СС_Выз"),
    ("data", N_(u"Данные"), u"СС_Дан"),
    ("security", N_(u"Охранная сигнализация"), u"СС_Охр"),
    ("fire", N_(u"Пожарная сигнализация"), u"СС_Пож"),
    ("control", N_(u"Управление"), u"СС_Упр"),
]
ROLES = [
    ("tray", N_(u"Линия в лотке"), u"Линия в лотке"),
    ("pipe", N_(u"Линия в трубе"), u"Линия в трубе"),
    ("box", N_(u"Линия в коробе"), u"Линия в коробе"),
    ("pipe_open", N_(u"Линия в трубе открыто"), u"Линия в трубе_Открыто"),
]

FILE_NAME = "LowLifeRouteLines_settings.json"
WORKSET_KEY = "workset_filter"
DEFAULT_WORKSET_FILTER = u"_к1"
FAMILY_KEY = "family_{}"
TYPE_KEY = "type_{}_{}"


def family_key(panel_key):
    return FAMILY_KEY.format(panel_key)


def type_key(panel_key, role_key):
    return TYPE_KEY.format(panel_key, role_key)


FIELDS = [settings_core.TextField(
    WORKSET_KEY, N_(u"Рабочий набор"),
    N_(u"Часть имени рабочего набора"),
    hint=N_(u"В имени рабочего набора должна встречаться эта строка. По умолчанию — «_к1». "
           u"Если подходит несколько наборов, уточните фильтр."),
    default=DEFAULT_WORKSET_FILTER, required=True,
)]
for panel_key, panel_label, family_default in PANELS:
    FIELDS.append(settings_core.TextField(
        family_key(panel_key), panel_label,
        N_(u"Фильтр имени семейства"),
        hint=N_(u"Подстрока в имени семейства обобщённой модели для этой панели."),
        default=family_default, required=True,
    ))
    for role_key, role_label, type_default in ROLES:
        FIELDS.append(settings_core.TextField(
            type_key(panel_key, role_key), u"", role_label,
            hint=N_(u"Точное имя типа семейства, который запускает эта кнопка."),
            default=type_default, required=True,
        ))


SETTINGS = settings_core.TextSettings(
    file_name=FILE_NAME,
    button_name=N_(u"Настройки линий трассы"),
    heading=N_(u"Линии трассы: семейства и типы"),
    transfer_label=N_(u"Настройки линий трассы"),
    fields=FIELDS,
    intro=N_(u"Для каждой панели задайте фильтр имени семейства и точные имена четырёх типов. "
             u"Кнопки размещения используют эти соответствия."),
    reset_button=True,
    width=820,
    height=1040,
)

get_settings_interactive = SETTINGS.get_settings_interactive
get_settings_silent = SETTINGS.get_settings_silent
