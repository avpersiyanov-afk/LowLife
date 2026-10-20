# -*- coding: utf-8 -*-
"""
Настройки кнопки «Отметки парковки» (Tools.panel/ParkingMarks) + их
хранение между запусками (%APPDATA%\\pyRevit\\LowLifeParkingMarks_settings.json).

Обвязка (хранение, окно, Shift+клик/тихий режим) — общая,
settings_core.TextSettings; здесь только описание полей — по три на
группу из parking_marks_core.GROUPS (слова, текст, штриховка) и текст
для прочих элементов. Имён параметров модели кнопка не использует.
"""

from lowlife import settings_core
from lowlife.parking_marks_core import GROUPS, OTHER

_NUMBERS = [u"①", u"②", u"③", u"④"]
_FILL_CHOICES = [("no", u"Не штриховать"), ("yes", u"Штриховать по контуру")]


def _group_fields(index, group):
    return [
        settings_core.TextField(
            group.key + "_words",
            u"{} {}".format(_NUMBERS[index], group.name),
            u"Слова (через запятую)",
            hint=(
                u"Ищутся без учёта регистра в «Комментариях», имени рабочего набора и "
                u"имени семейства/типа элемента. Группы проверяются по порядку — "
                u"элемент попадает в первую подошедшую. Пусто — группа выключена."
            ) if index == 0 else u"",
            default=group.words,
        ),
        settings_core.TextField(
            group.key + "_text_format",
            u"",
            u"Текст подписи",
            hint=(
                u"{top} — отметка верха, {bottom} — низа, от уровня плана («+2,450»)."
            ) if index == 0 else u"",
            default=group.text_format,
        ),
        settings_core.ChoiceField(
            group.key + "_fill",
            u"",
            u"Штриховка",
            _FILL_CHOICES,
            hint=(
                u"Тип области заливки «LowLife — {}» создаётся при первом запуске; "
                u"его штриховку и цвет можно потом поменять в Revit."
            ).format(group.name.lower()) if index == 0 else u"",
            default=group.fill,
        ),
    ]


_FIELDS = []
for _index, _group in enumerate(GROUPS):
    _FIELDS.extend(_group_fields(_index, _group))
_FIELDS.append(settings_core.TextField(
    OTHER.key + "_text_format",
    u"{} Остальные элементы «Парковки»".format(_NUMBERS[len(GROUPS)]),
    u"Текст подписи (пусто — не подписывать)",
    default=OTHER.text_format,
))

SETTINGS = settings_core.TextSettings(
    file_name="LowLifeParkingMarks_settings.json",
    button_name=u"Отметки парковки",
    heading=u"Отметки зон парковки от уровня плана",
    transfer_label=u"кнопки «Отметки парковки»",
    fields=_FIELDS,
    width=720, height=700,
)

load_saved_values = SETTINGS.load_saved_values
save_values = SETTINGS.save_values
require = SETTINGS.require
show_settings_form = SETTINGS.show_settings_form
get_settings_interactive = SETTINGS.get_settings_interactive
get_settings_silent = SETTINGS.get_settings_silent
