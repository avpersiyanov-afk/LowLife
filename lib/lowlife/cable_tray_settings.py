# -*- coding: utf-8 -*-
"""
Настройки кнопок «Лоток ...» (Tray*.panel) + их хранение между запусками.

Одно окно на все 20 кнопок: Shift+клик по любой кнопке лотка открывает
его целиком — рабочий набор (общий) и подстроки имён типов лотков всех
кнопок, сгруппированные по панелям. Хранится в
%APPDATA%\\pyRevit\\LowLifeCableTray_settings.json.

Умолчания — те значения, что раньше были зашиты в script.py кнопок
(тип вида «СБ_ЛЛ_1.5_СЦ», рабочий набор «КНК»); список кнопок и их
умолчаний — PANELS × SYSTEMS ниже.

Обвязка (хранение, окно, Shift+клик/тихий режим) — общая,
settings_core.TextSettings; здесь только описание полей.
"""

from lowlife import settings_core


FILE_NAME = "LowLifeCableTray_settings.json"

DEFAULT_WORKSET_FILTER = u"КНК"

WORKSET_KEY = "workset_filter"

# (папка панели без .panel, заголовок панели на ленте, хвост имени типа)
PANELS = [
    ("TrayLadder", u"Лестничный лоток", u"ЛЛ_1.5_СЦ"),
    ("TrayUnperforated", u"Неперфорированный лоток", u"ЛН_1.5_СЦ"),
    ("TrayPerforated", u"Перфорированный лоток", u"ЛП_1.5_СЦ"),
    ("TrayWire", u"Проволочный лоток", u"ЛВ_1.5_СЦ"),
    ("TrayRoof", u"Лотки на кровле", u"ЛП_1.5_ГЦ"),
]

# (папка кнопки без .pushbutton, система — начало имени типа и подпись кнопки)
SYSTEMS = [
    ("TraySPZo", u"СПЗо"),
    ("TraySPZp", u"СПЗп"),
    ("TraySB", u"СБ"),
    ("TraySS", u"СС"),
]


def tray_type_key(panel_folder, button_folder):
    """Ключ подстроки типа для кнопки, например «tray_type_TrayLadder_TraySB»."""
    return "tray_type_{}_{}".format(panel_folder, button_folder)


def _panel(panel_folder):
    for panel in PANELS:
        if panel[0] == panel_folder:
            return panel
    raise KeyError(panel_folder)


def _system(button_folder):
    for system in SYSTEMS:
        if system[0] == button_folder:
            return system
    raise KeyError(button_folder)


def default_tray_type(panel_folder, button_folder):
    """Подстрока типа по умолчанию, например «СБ_ЛЛ_1.5_СЦ»."""
    return u"{}_{}".format(_system(button_folder)[1], _panel(panel_folder)[2])


def button_title(panel_folder, button_folder):
    """Как кнопка называется в сообщениях: «Лоток СБ (Лестничный лоток)»."""
    return u"Лоток {} ({})".format(_system(button_folder)[1], _panel(panel_folder)[1])


def _fields():
    fields = [
        settings_core.TextField(
            WORKSET_KEY,
            u"Рабочий набор",
            u"Часть имени рабочего набора",
            hint=(
                u"Перед рисованием кнопка делает активным рабочий набор, в имени "
                u"которого есть этот текст, — чтобы лоток попал в нужный рабочий "
                u"набор. Должен совпадать ровно с одним рабочим набором. "
                u"По умолчанию — «{}».".format(DEFAULT_WORKSET_FILTER)
            ),
            default=DEFAULT_WORKSET_FILTER, required=True,
        ),
    ]
    for panel_folder, panel_title, _suffix in PANELS:
        for i, (button_folder, system) in enumerate(SYSTEMS):
            fields.append(settings_core.TextField(
                tray_type_key(panel_folder, button_folder),
                # заголовок панели — над первым полем её группы
                panel_title if i == 0 else u"",
                u"Лоток {} — часть имени типа".format(system),
                default=default_tray_type(panel_folder, button_folder),
                required=True,
            ))
    return fields


SETTINGS = settings_core.TextSettings(
    file_name=FILE_NAME,
    button_name=u"кабельные лотки",
    heading=u"Рабочий набор и типы кабельных лотков",
    transfer_label=u"кабельных лотков",
    fields=_fields(),
    intro=(
        u"Общие настройки всех кнопок лотков. Кнопка ищет в проекте тип "
        u"кабельного лотка, в имени которого есть указанный текст (ровно один "
        u"тип), и запускает рисование лотка этим типом. Типы должны уже быть "
        u"в проекте. «Сбросить» возвращает значения по умолчанию."
    ),
    reset_button=True,
    width=640, height=760,
)

load_saved_values = SETTINGS.load_saved_values
save_values = SETTINGS.save_values
missing = SETTINGS.missing
get_settings_interactive = SETTINGS.get_settings_interactive
get_settings_silent = SETTINGS.get_settings_silent
