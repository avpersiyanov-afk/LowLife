# -*- coding: utf-8 -*-
"""
Настройки кнопки «Экспликация фрагмента» (ToolsRooms.panel): заголовки и
ширины столбцов, параметр категории помещения, знаки площади.

Хранятся в %APPDATA%\\pyRevit\\LowLifeRoomExplication_settings.json через
settings_core.TextSettings (Shift+клик по кнопке). Умолчания заголовков и
ширин — из room_explication_core.COLUMNS (форма 2 ГОСТ 21.501).
"""

from lowlife import settings_core
from lowlife.room_explication_core import COLUMNS

_LABELS = {
    "number": u"Номер помещения",
    "name": u"Наименование",
    "area": u"Площадь",
    "category": u"Категория",
}


def _column_fields():
    fields = []
    for i, (key, heading, width) in enumerate(COLUMNS):
        section = u"{} Столбец «{}»".format(u"①②③④"[i], _LABELS[key])
        fields.append(settings_core.TextField(
            "header_" + key, section, u"Заголовок",
            hint=u"Текст в шапке таблицы. Пусто — по умолчанию: «{}».".format(heading),
            default=heading, required=False,
        ))
        fields.append(settings_core.NumberField(
            "width_" + key, u"", u"Ширина, мм",
            hint=u"Ширина графы на листе. По умолчанию {:g} мм.".format(width),
            default=width, minimum=3.0,
        ))
    return fields


SETTINGS = settings_core.TextSettings(
    file_name="LowLifeRoomExplication_settings.json",
    button_name=u"Экспликация фрагмента",
    heading=u"Экспликация фрагмента: столбцы таблицы",
    transfer_label=u"экспликации фрагмента",
    fields=_column_fields() + [
        settings_core.TextField(
            "category_param", u"⑤ Данные", u"Параметр категории помещения",
            hint=(
                u"Имя параметра помещения с категорией по взрывопожарной и "
                u"пожарной опасности (в модели или связи АР). Пусто — графа "
                u"«Категория» остаётся незаполненной."
            ),
            default=u"", required=False,
        ),
        settings_core.NumberField(
            "area_decimals", u"", u"Знаков после запятой в площади",
            hint=u"По умолчанию 2 (12,35).",
            default=2, minimum=0, integer=True,
        ),
    ],
    reset_button=True,
    width=720, height=640,
)

load_saved_values = SETTINGS.load_saved_values
save_values = SETTINGS.save_values
get_settings_interactive = SETTINGS.get_settings_interactive
get_settings_silent = SETTINGS.get_settings_silent


def columns(settings):
    """[(ключ, заголовок, ширина мм)] с учётом настроек (пустой заголовок — умолчание)."""
    result = []
    for key, heading, width in COLUMNS:
        text = (settings.get("header_" + key) or u"").strip() or heading
        result.append((key, text, float(settings.get("width_" + key) or width)))
    return result
