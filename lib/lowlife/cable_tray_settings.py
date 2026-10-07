# -*- coding: utf-8 -*-
"""
Настройки кнопок «Лоток ...» (Tray*.panel) + их хранение между запусками.

Все 20 кнопок пишут в один файл %APPDATA%\\pyRevit\\LowLifeCableTray_settings.json:
у каждой кнопки свой ключ с подстрокой имени типа лотка, а ключевое слово
рабочего набора — общее для всех кнопок (поменяли у одной — поменялось у
всех). TextSettings.save_values дописывает только свои ключи, поэтому
окна разных кнопок не затирают значения друг друга.

Умолчания — те значения, что раньше были зашиты в script.py кнопок
(тип вида «СБ_ЛЛ_1.5_СЦ», рабочий набор «КНК»).

Обвязка (хранение, окно, require, Shift+клик/тихий режим) — общая,
settings_core.TextSettings; здесь только описание полей.
"""

from lowlife import settings_core


FILE_NAME = "LowLifeCableTray_settings.json"

DEFAULT_WORKSET_FILTER = u"КНК"

WORKSET_KEY = "workset_filter"


def tray_type_key(panel_folder, button_folder):
    """Ключ подстроки типа для кнопки, например «tray_type_TrayLadder_TraySB»."""
    return "tray_type_{}_{}".format(panel_folder, button_folder)


def button_settings(panel_folder, button_folder, button_name, default_tray_type):
    """
    TextSettings одной кнопки: подстрока имени типа лотка (своя у кнопки)
    и ключевое слово рабочего набора (общее для всех кнопок лотков).

    panel_folder/button_folder — имена папок без расширения («TrayLadder»,
    «TraySB»), из них строится ключ в файле; button_name — как кнопка
    называется в сообщениях («Лоток СБ (Лестничный лоток)»).
    """
    return settings_core.TextSettings(
        file_name=FILE_NAME,
        button_name=button_name,
        heading=u"Тип лотка и рабочий набор",
        transfer_label=u"кабельных лотков",
        fields=[
            settings_core.TextField(
                tray_type_key(panel_folder, button_folder),
                u"① Тип лотка этой кнопки",
                u"Часть имени типа кабельного лотка",
                hint=(
                    u"Кнопка ищет в проекте тип кабельного лотка, в имени которого "
                    u"есть этот текст, и запускает рисование лотка этим типом. "
                    u"Тип должен уже быть в проекте, и текст должен совпадать "
                    u"ровно с одним типом. По умолчанию — «{}».".format(default_tray_type)
                ),
                default=default_tray_type, required=True,
            ),
            settings_core.TextField(
                WORKSET_KEY,
                u"② Рабочий набор (общий для всех кнопок лотков)",
                u"Часть имени рабочего набора",
                hint=(
                    u"Перед рисованием кнопка делает активным рабочий набор, в "
                    u"имени которого есть этот текст, — чтобы лоток попал в "
                    u"нужный рабочий набор. Должен совпадать ровно с одним "
                    u"рабочим набором. Значение общее для всех кнопок лотков. "
                    u"По умолчанию — «{}».".format(DEFAULT_WORKSET_FILTER)
                ),
                default=DEFAULT_WORKSET_FILTER, required=True,
            ),
        ],
        reset_button=True,
        width=720, height=440,
    )
