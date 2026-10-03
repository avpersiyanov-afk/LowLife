# -*- coding: utf-8 -*-
"""
Окно настроек параметров для кнопки «Запись номера помещения» + их хранение
между запусками.

Хранится в JSON-файле %APPDATA%\\pyRevit\\LowLifeRoomInfo_settings.json —
тот же подход, что scs_settings.py/skud_settings.py (простой файл вместо
pyrevit.script.get_config(), см. их докстринги про причину).

Значения — имена параметров, специфичные для конкретного проекта/ФОП,
поэтому никогда не задаются константами в коде, только через это окно.

Обвязка (хранение, окно, require, Shift+клик/тихий режим) — общая,
settings_core.TextSettings; здесь только описание полей.
"""

from lowlife import settings_core

# Два поля легко перепутать, т.к. оба про «параметр помещения» — но
# относятся к РАЗНЫМ документам: первое пишет в текущую модель, второе
# читает из модели-связи. Поэтому в окне разнесены по разделам с ①/②,
# а не просто друг под другом.

def _migrate(saved, values):
    # Миграция со старого поля room_number_param_name (имя параметра
    # номера помещения в связи) на маску: если маска ещё не сохранена, а
    # старое поле есть — воспроизводим прежний формат «Имя (Номер-параметр)».
    if not saved.get("room_mask") and saved.get("room_number_param_name"):
        values["room_mask"] = u"Имя ({})".format(saved["room_number_param_name"])


SETTINGS = settings_core.TextSettings(
    file_name="LowLifeRoomInfo_settings.json",
    button_name=u"Запись номера помещения",
    heading=u"Параметры для переноса помещения из связи",
    transfer_label=u"помещений",
    fields=[
        settings_core.TextField(
            "target_param_name",
            u"① Куда записывать — в этой модели",
            u"Параметр элемента",
            hint=(
                u"Имя параметра ваших элементов (в этой модели), в который будет "
                u"записано помещение, где элемент стоит. Параметр должен быть "
                u"общим и добавленным к нужным категориям. Например «Помещение»."
            ),
            default=u"", required=True,
        ),
        settings_core.TextField(
            "room_mask",
            u"② Что записывать — маска из параметров связи",
            u"Маска записи параметров из смежной модели",
            hint=(
                u"Из каких параметров помещения (Room) связанной модели собрать "
                u"текст — имена параметров через запятую и/или в скобках. «Имя» и "
                u"«Номер» — это имя и номер помещения, любое другое слово "
                u"считается именем параметра помещения. Примеры: «Имя, Номер» → "
                u"«Офис, 212»; «Имя (Номер)» → «Офис (212)». Если какой-то параметр "
                u"пуст, он просто пропускается вместе с лишними скобками/запятыми."
            ),
            default=u"Имя (Номер)", required=True,
        ),
        settings_core.TextField(
            "view_name_prefixes",
            u"③ Пакетный прогон по видам (Shift+клик → «Прогон по видам»)",
            u"Префиксы имён видов для списка",
            hint=(
                u"В списке видов показываются только те, чьё имя начинается с "
                u"одного из этих значений (через запятую). Например «1, 2, 20, 30, "
                u"60». Пусто — показывать все виды. Не влияет на обычный запуск "
                u"кнопки (там выбор элементов вручную)."
            ),
            default=u"1, 2, 20, 30, 60", required=False,
        ),
    ],
    migrate=_migrate,
    width=780, height=520,
)

load_saved_values = SETTINGS.load_saved_values
save_values = SETTINGS.save_values
require = SETTINGS.require
show_settings_form = SETTINGS.show_settings_form
get_settings_interactive = SETTINGS.get_settings_interactive
get_settings_silent = SETTINGS.get_settings_silent
