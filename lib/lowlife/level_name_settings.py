# -*- coding: utf-8 -*-
"""
Окно настроек для кнопки «Обновить имя уровня» (LOI.panel/UpdateLevelName)
+ их хранение между запусками.

Хранится в JSON-файле %APPDATA%\\pyRevit\\LowLifeLevelName_settings.json —
тот же подход, что floor_settings.py/room_lots_settings.py (простой файл
вместо pyrevit.script.get_config()).

Имя параметра — соглашение конкретного проекта/ФОП, поэтому не зашито
константой в коде, только через это окно.
"""

from lowlife import settings_core


PARAM_KEY = "target_param_name"

SETTINGS = settings_core.TextSettings(
    file_name="LowLifeLevelName_settings.json",
    button_name=u"Обновить имя уровня",
    heading=u"Параметр, в который пишется имя уровня",
    transfer_label=u"обновления имени уровня",
    fields=[
        settings_core.TextField(
            PARAM_KEY,
            u"① Параметр «Уровень»",
            u"Имя текстового параметра элемента",
            hint=(
                u"В него записывается имя уровня элемента: уровень из свойств "
                u"элемента, а если его нет (например, семейство на грани связи) — "
                u"ближайший уровень не выше элемента по высоте. Существующее "
                u"значение перезаписывается."
            ),
            default=u"", required=True,
        ),
    ],
    width=640, height=340,
)

load_saved_values = SETTINGS.load_saved_values
save_values = SETTINGS.save_values
require = SETTINGS.require
show_settings_form = SETTINGS.show_settings_form
get_settings_interactive = SETTINGS.get_settings_interactive
get_settings_silent = SETTINGS.get_settings_silent
