# -*- coding: utf-8 -*-
"""
Настройки кнопки «Внесение изменений» (Tools.panel/ChangeClouds) +
их хранение между запусками (%APPDATA%\\pyRevit\\LowLifeChangeClouds_settings.json).

Обвязка (хранение, окно, Shift+клик/тихий режим) — общая,
settings_core.TextSettings; здесь только описание полей: семейство и маска
имени типа, параметры типа (шифр, номер, дата) и параметры экземпляра
(код, содержание, порядковый номер). Поля имён параметров (*_param) сами
получают подсказку имён параметров модели и делятся между кнопками.
"""

from lowlife import settings_core
from lowlife.change_clouds_core import DEFAULT_TEMPLATE
from lowlife.i18n import N_

_FAMILY_SECTION = N_(u"Семейство")
_TYPE_SECTION = N_(u"Параметры типа")
_INSTANCE_SECTION = N_(u"Параметры экземпляра")

_FIELDS = [
    settings_core.TextField(
        u"family_name",
        _FAMILY_SECTION,
        N_(u"Имя семейства облака изменений"),
        hint=N_(u"Загруженное в проект семейство, типы которого — изменения. "
               u"Новый тип будет создан копированием его первого типа. "
               u"Начните вводить — появится поиск по семействам модели "
               u"(↓ или Ctrl+Пробел — весь список, Enter — подставить)."),
        required=True,
    ),
    settings_core.TextField(
        u"name_template",
        _FAMILY_SECTION,
        N_(u"Маска имени типа"),
        hint=N_(u"Подстановки: {family} — имя семейства, {cipher} — шифр альбома, "
               u"{number} — номер изменения. По умолчанию: ") + DEFAULT_TEMPLATE,
        default=DEFAULT_TEMPLATE,
    ),
    settings_core.TextField(
        u"cipher_param",
        _TYPE_SECTION,
        N_(u"Параметр типа «Шифр альбома»"),
        hint=N_(u"Сюда записывается шифр альбома нового типа."),
        required=True,
    ),
    settings_core.TextField(
        u"number_param",
        _TYPE_SECTION,
        N_(u"Параметр типа «Номер изменения»"),
        hint=N_(
            u"Числовой или текстовый параметр типа. В имя типа и этот параметр "
            u"пишется номер изменения."
        ),
        required=True,
    ),
    settings_core.TextField(
        u"date_param",
        _TYPE_SECTION,
        N_(u"Параметр типа «Дата изменения»"),
        hint=N_(u"Записывается строкой «дд.мм.гг»."),
        required=True,
    ),
    settings_core.TextField(
        u"code_param",
        _INSTANCE_SECTION,
        N_(u"Параметр экземпляра «Код изменения»"),
        hint=N_(u"Выбирается из списка 1–5 при вставке облака."),
        required=True,
    ),
    settings_core.TextField(
        u"content_param",
        _INSTANCE_SECTION,
        N_(u"Параметр экземпляра «Содержание изменения»"),
        hint=N_(u"Сюда записывается текст, который вы введёте при вставке."),
        required=True,
    ),
    settings_core.TextField(
        u"order_param",
        _INSTANCE_SECTION,
        N_(u"Параметр экземпляра «Порядковый номер»"),
        hint=N_(
            u"Заполняется автоматически: количество облаков этого семейства "
            u"на текущем листе + 1."
        ),
        required=True,
    ),
]

SETTINGS = settings_core.TextSettings(
    file_name=u"LowLifeChangeClouds_settings.json",
    button_name=N_(u"Внесение изменений"),
    heading=N_(u"Облако изменений: семейство и параметры"),
    transfer_label=N_(u"кнопки «Внесение изменений»"),
    fields=_FIELDS,
    width=760, height=640,
)

load_saved_values = SETTINGS.load_saved_values
save_values = SETTINGS.save_values
require = SETTINGS.require
show_settings_form = SETTINGS.show_settings_form
get_settings_interactive = SETTINGS.get_settings_interactive
get_settings_silent = SETTINGS.get_settings_silent
