# -*- coding: utf-8 -*-
"""
Настройки кнопки «DWG → чертёжный вид» (Tools.panel/DwgToDrafting) —
Shift+клик по кнопке. Хранятся в %APPDATA%\\pyRevit\\LowLifeDwgTransfer_settings.json
(settings_core.TextSettings, как room_lots_settings.py).
"""

from lowlife import settings_core


SETTINGS = settings_core.TextSettings(
    file_name="LowLifeDwgTransfer_settings.json",
    button_name=u"DWG → чертёжный вид",
    heading=u"Перенос DWG в линии детализации и текст",
    transfer_label=u"переноса DWG",
    fields=[
        settings_core.TextField(
            "line_style",
            u"① Линии",
            u"Стиль линий для всех линий",
            hint=(
                u"Имя существующего стиля линий (например, «<Тонкие линии>»). "
                u"Пусто — по слоям DWG: на каждый слой создаётся свой стиль "
                u"линий с префиксом ниже, цвет и вес берутся у слоя импорта."
            ),
            default=u"",
        ),
        settings_core.TextField(
            "layer_style_prefix",
            u"",
            u"Префикс стилей по слоям",
            hint=u"Стиль слоя «Стены» будет называться «DWG_Стены».",
            default=u"DWG_",
        ),
        settings_core.TextField(
            "base_text_type",
            u"② Текст",
            u"Исходный типоразмер текста",
            hint=(
                u"Имя типоразмера текста, с которого копируются новые типы "
                u"нужной высоты (шрифт, цвет, вес). Пусто — типоразмер текста "
                u"по умолчанию."
            ),
            default=u"",
        ),
        settings_core.TextField(
            "text_type_prefix",
            u"",
            u"Префикс типов текста",
            hint=u"Тип высотой 2,5 мм будет называться «DWG 2.5 мм».",
            default=u"DWG ",
        ),
        settings_core.TextField(
            "oda_converter",
            u"③ Конвертер",
            u"Путь к ODAFileConverter.exe",
            hint=(
                u"Текст читается из DXF. Если рядом с DWG нет DXF с тем же "
                u"именем, DWG конвертируется бесплатной программой ODA File "
                u"Converter. Пусто — ищется в C:\\Program Files\\ODA\\."
            ),
            default=u"",
        ),
    ],
    width=760, height=560,
)

load_saved_values = SETTINGS.load_saved_values
save_values = SETTINGS.save_values
require = SETTINGS.require
show_settings_form = SETTINGS.show_settings_form
get_settings_interactive = SETTINGS.get_settings_interactive
get_settings_silent = SETTINGS.get_settings_silent
