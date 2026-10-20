# -*- coding: utf-8 -*-
"""
Настройки кнопки «Отметки парковки» (Tools.panel/ParkingMarks) + их
хранение между запусками (%APPDATA%\\pyRevit\\LowLifeParkingMarks_settings.json).

Обвязка (хранение, окно, Shift+клик/тихий режим) — общая,
settings_core.TextSettings; здесь только описание полей. Имён параметров
модели кнопка не использует: элементы берутся по категории «Парковка»,
зоны — по словам в штатном параметре «Комментарии».
"""

from lowlife import settings_core


SETTINGS = settings_core.TextSettings(
    file_name="LowLifeParkingMarks_settings.json",
    button_name=u"Отметки парковки",
    heading=u"Отметки элементов «Парковка» из связей",
    transfer_label=u"кнопки «Отметки парковки»",
    fields=[
        settings_core.TextField(
            "zone_words",
            u"① Зоны",
            u"Слова в «Комментариях» элемента парковки (через запятую)",
            hint=(
                u"Если в «Комментариях» элемента есть одно из слов (без учёта регистра), "
                u"это зона: на плане отмечаются её верх и низ, а контур заливается "
                u"штриховкой. Остальным элементам ставится только отметка верха."
            ),
            default=u"зона",
        ),
        settings_core.ChoiceField(
            "mark_mode",
            u"② Отметки",
            u"Чем отмечать",
            [("spot", u"Высотной отметкой Revit (если не выйдет — текстом)"),
             ("text", u"Текстом")],
            hint=(
                u"Высотная отметка ставится на верхнюю (низ зоны — на нижнюю) грань "
                u"элемента связи; от чего она считается — задаёт её тип "
                u"(«LowLife — отметки парковки», копия типа отметки по умолчанию). "
                u"Где Revit отметку не принял, ставится текст."
            ),
            default="spot",
        ),
        settings_core.ChoiceField(
            "elevation_base",
            u"",
            u"От чего считать отметку в тексте",
            [("project", u"От базовой точки проекта"),
             ("shared", u"Абсолютная (общая система координат)"),
             ("internal", u"От начала внутренней системы координат")],
            default="project",
        ),
        settings_core.TextField(
            "top_text_format",
            u"",
            u"Текст отметки верха машиноместа",
            hint=u"{h} — отметка («+3,150»). У высотной отметки текст вокруг {h} — префикс/суффикс.",
            default=u"{h}",
        ),
        settings_core.TextField(
            "zone_top_text_format",
            u"",
            u"Текст отметки верха зоны",
            default=u"Верх зоны {h}",
        ),
        settings_core.TextField(
            "zone_bottom_text_format",
            u"",
            u"Текст отметки низа зоны",
            default=u"Низ зоны {h}",
        ),
        settings_core.TextField(
            "zone_fill_type_name",
            u"③ Штриховка зон",
            u"Тип области заливки",
            hint=(
                u"Пусто — тип «LowLife — зона парковки» (создаётся при первом запуске: "
                u"диагональная штриховка оранжевым; потом его можно поменять в Revit)."
            ),
            default=u"",
        ),
    ],
    width=720, height=620,
)

load_saved_values = SETTINGS.load_saved_values
save_values = SETTINGS.save_values
require = SETTINGS.require
show_settings_form = SETTINGS.show_settings_form
get_settings_interactive = SETTINGS.get_settings_interactive
get_settings_silent = SETTINGS.get_settings_silent
