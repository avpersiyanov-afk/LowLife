# -*- coding: utf-8 -*-
"""
Окно настроек параметров для кнопки «Найти помещение» (ToolsRooms.panel) +
их хранение между запусками.

Хранится в JSON-файле %APPDATA%\\pyRevit\\LowLifeFindRoom_settings.json —
тот же подход, что room_info_settings.py/scs_settings.py (простой файл
вместо pyrevit.script.get_config(), см. их докстринги про причину).

Имя параметра — соглашение конкретного проекта/ФОП, поэтому не зашито
константой в коде, только через это окно.

Обвязка (хранение, окно, require, Shift+клик/тихий режим) — общая,
settings_core.TextSettings; здесь только описание полей.
"""

from lowlife import settings_core


SETTINGS = settings_core.TextSettings(
    file_name="LowLifeFindRoom_settings.json",
    button_name=u"Найти помещение",
    heading=u"Параметры номера и группировки списка помещений",
    transfer_label=u"поиска помещений",
    fields=[
        settings_core.TextField(
            "room_number_param_name",
            u"① Номер помещения — по какому параметру искать/сортировать",
            u"Параметр номера (в связи АР)",
            hint=(
                u"Имя параметра Room, который считается «номером помещения» — по "
                u"нему строится и сортируется список, по нему же работает поиск в "
                u"строке фильтра. Пусто — используется встроенный параметр «Номер» "
                u"(ROOM_NUMBER). Если у конкретного помещения этот параметр пуст, "
                u"для него тоже подставляется встроенный номер."
            ),
            default=u"", required=False,
        ),
        settings_core.TextField(
            "room_type_param_name",
            u"② Группировка списка помещений",
            u"Параметр помещения (в связи АР)",
            hint=(
                u"Имя параметра Room, по значению которого группируется список для "
                u"выбора — например «Тип помещения», «Назначение» или встроенный "
                u"«Департамент». Пусто — список просто сортируется по номеру, без "
                u"группировки."
            ),
            default=u"", required=False,
        ),
    ],
    width=720, height=480,
)

load_saved_values = SETTINGS.load_saved_values
save_values = SETTINGS.save_values
require = SETTINGS.require
show_settings_form = SETTINGS.show_settings_form
get_settings_interactive = SETTINGS.get_settings_interactive
get_settings_silent = SETTINGS.get_settings_silent
