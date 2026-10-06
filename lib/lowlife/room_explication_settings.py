# -*- coding: utf-8 -*-
"""
Настройки кнопок «Экспликация фрагмента» / «Обновить экспликацию»
(ToolsRooms.panel): название таблицы, заголовки и ширины граф, высота строк,
параметр категории помещения, знаки площади.

Хранятся в %APPDATA%\\pyRevit\\LowLifeRoomExplication_settings.json через
settings_core.TextSettings (Shift+клик по кнопке). Умолчания заголовков и
ширин — из room_explication_core.COLUMNS (форма 2 ГОСТ 21.501).
"""

from lowlife import settings_core
from lowlife.room_explication_core import (
    COLUMNS, HEADER_HEIGHT_MM, OLD_DEFAULT_WIDTHS, ROW_HEIGHT_MM, TITLE)

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


def _migrate(saved, values):
    """Ширины, сохранённые со старыми умолчаниями (60/15), — на форму ГОСТ."""
    old = all(_num(saved.get("width_" + k)) == w for k, w in OLD_DEFAULT_WIDTHS.items())
    if old:
        for key, _heading, width in COLUMNS:
            if key in OLD_DEFAULT_WIDTHS:
                values["width_" + key] = width


def _num(value):
    try:
        return float(value)
    except Exception:
        return None


def title(settings):
    return (settings.get("title") or u"").strip() or TITLE


def heights(settings):
    """(высота шапки, высота строки) в мм."""
    return (float(settings.get("header_height") or HEADER_HEIGHT_MM),
            float(settings.get("row_height") or ROW_HEIGHT_MM))


SETTINGS = settings_core.TextSettings(
    file_name="LowLifeRoomExplication_settings.json",
    button_name=u"Экспликация фрагмента",
    heading=u"Экспликация фрагмента: столбцы таблицы",
    transfer_label=u"экспликации фрагмента",
    fields=[
        settings_core.TextField(
            "title", u"Таблица", u"Название над таблицей",
            hint=u"Пусто — «{}».".format(TITLE),
            default=TITLE, required=False,
        ),
    ] + _column_fields() + [
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
        settings_core.NumberField(
            "header_height", u"⑥ Высота строк", u"Шапка таблицы, мм",
            hint=u"По умолчанию 20 мм (форма 2 ГОСТ 21.501).",
            default=HEADER_HEIGHT_MM, minimum=3.0,
        ),
        settings_core.NumberField(
            "row_height", u"", u"Строка помещения, мм",
            hint=u"По умолчанию 8 мм (форма 2 ГОСТ 21.501).",
            default=ROW_HEIGHT_MM, minimum=3.0,
        ),
    ],
    migrate=_migrate,
    reset_button=True,
    width=720, height=760,
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
