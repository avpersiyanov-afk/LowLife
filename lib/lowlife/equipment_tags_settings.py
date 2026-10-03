# -*- coding: utf-8 -*-
"""
Настройки кнопки «Марки оборудования» + их хранение между запусками.

Хранится в JSON-файле %APPDATA%\\pyRevit\\LowLifeEquipmentTags_settings.json —
тот же подход, что room_info_settings.py/scs_settings.py (простой файл
вместо pyrevit.script.get_config(), см. их докстринги про причину).

Все расстояния — в миллиметрах НА ЛИСТЕ: при раскладке умножаются на
масштаб вида, поэтому на 1:50 и 1:100 марки выглядят одинаково.

Обвязка (хранение, окно, проверка чисел) — общая,
settings_core.TextSettings; здесь только описание полей. Битые или
отрицательные значения в файле заменяются значениями по умолчанию.
"""

from lowlife import settings_core


def _mm(key, title, hint, default):
    return settings_core.NumberField(key, title, u"", hint=hint, default=default,
                                     min_value=0)


SETTINGS = settings_core.TextSettings(
    file_name="LowLifeEquipmentTags_settings.json",
    button_name=u"Марки оборудования",
    heading=u"Раскладка марок оборудования",
    subtitle=(
        u"Все расстояния — в мм на листе, как на распечатке: при масштабе "
        u"вида 1:100 отступ 3 мм — это 300 мм в модели. "
        u"Значения сохраняются между запусками."
    ),
    transfer_label=u"марок оборудования",
    fields=[
        _mm(
            "offset_mm",
            u"Отступ марок от оборудования, мм",
            u"На каком расстоянии от габарита оборудования встаёт колонка/"
            u"стопка марок. Если места нет, кнопка сама пробует 2× и 3× отступ.",
            3.0
        ),
        _mm(
            "gap_mm",
            u"Зазор между марками, мм",
            u"Минимальный промежуток между соседними марками в колонке/стопке.",
            1.0
        ),
        _mm(
            "shelf_mm",
            u"Длина полки выноски, мм",
            u"Короткий горизонтальный отрезок линии-выноски у самой марки "
            u"(«полочка»), от которого наклонная часть идёт к оборудованию.",
            3.0
        ),
        _mm(
            "cluster_mm",
            u"«Рядом» — если оборудование ближе, мм",
            u"Оборудование, стоящее друг от друга ближе этого расстояния, "
            u"получает марки одним блоком: рядом по горизонтали — стопкой "
            u"друг над другом, одно над другим — колонкой сбоку на одном "
            u"отступе.",
            8.0
        ),
    ],
    width=620, height=520,
)

load_settings = SETTINGS.load_saved_values
show_settings_form = SETTINGS.show_settings_form
get_settings_interactive = SETTINGS.get_settings_interactive
