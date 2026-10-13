# -*- coding: utf-8 -*-
"""
Настройки кнопки «Виды по уровням» (Tools.panel/LevelViews) — то, что
вписано в окне в прошлый раз: маска имени, значения по шаблонам видов,
отмеченные шаблоны (level_views_core.normalize_settings).

JSON-файл %APPDATA%\\pyRevit\\LowLifeLevelViews_settings.json. Шаблоны
хранятся по имени — имя переносится между проектами, Id — нет.
Шаблон имени уровня (для {Этаж}/{Корпус}/{Комментарий}) свой не
заводится — берётся из настроек «Секущего диапазона».
"""

from lowlife import level_name_template, settings_core
from lowlife import level_views_core as core

SETTINGS_FILE_NAME = "LowLifeLevelViews_settings.json"

_STORE = settings_core.JsonStore(SETTINGS_FILE_NAME, label=u"видов по уровням")


def load():
    return core.normalize_settings(_STORE.read())


def save(mask, values, checked):
    """values — {шаблон: значение} (дописываются к старым), checked — [шаблоны]."""
    saved = load()
    all_values = dict(saved[core.VALUES_KEY])
    all_values.update(values)
    return _STORE.update({
        core.MASK_KEY: mask,
        core.VALUES_KEY: all_values,
        core.CHECKED_KEY: list(checked),
    })


def level_template():
    """Шаблон имени уровня из настроек «Секущего диапазона» (или по умолчанию)."""
    from lowlife import view_range_settings
    try:
        text = view_range_settings.get_settings_silent()[view_range_settings.LEVEL_TEMPLATE_KEY]
    except Exception:
        text = level_name_template.DEFAULT_TEMPLATE
    return level_name_template.LevelNameTemplate(text)
