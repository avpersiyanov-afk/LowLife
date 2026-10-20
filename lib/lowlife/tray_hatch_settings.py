# -*- coding: utf-8 -*-
"""
Настройки кнопки «Лючки на уровнях» (ToolsTraySection.panel/TrayHatches) +
их хранение между запусками (%APPDATA%\\pyRevit\\LowLifeTrayHatch_settings.json).

Имена параметров размеров — параметры семейства лючка конкретного проекта,
поэтому умолчаний нет. Слово в имени типа («лючок») — общая лексика, у него
умолчание есть.

Обвязка (хранение, окно, Shift+клик/тихий режим) — общая,
settings_core.TextSettings; здесь только описание полей.
"""

from lowlife import settings_core


DEFAULT_TYPE_FILTER = u"лючок"
DEFAULT_MARGIN_MM = 50.0

SETTINGS = settings_core.TextSettings(
    file_name="LowLifeTrayHatch_settings.json",
    button_name=u"Лючки на уровнях",
    heading=u"Лючки в местах пересечения лотков с уровнями",
    transfer_label=u"кнопки «Лючки на уровнях»",
    fields=[
        settings_core.TextField(
            "hatch_type_filter",
            u"① Семейство лючка",
            u"Часть имени типа",
            hint=(
                u"Ставится загруженное семейство, в имени типа которого есть этот "
                u"текст (без учёта регистра). Несколько подходящих типов — кнопка "
                u"спросит, какой взять. Семейство — на основе уровня или рабочей "
                u"плоскости (не на грани). По умолчанию — «{}».".format(DEFAULT_TYPE_FILTER)
            ),
            default=DEFAULT_TYPE_FILTER, required=True,
        ),
        settings_core.TextField(
            "hatch_width_param",
            u"② Размеры лючка",
            u"Параметр ширины (вдоль ширины лотка)",
            hint=(
                u"Параметр длины семейства лючка, в который пишется ширина лотка плюс "
                u"запас. Направление этого размера в семействе — по его оси X: лючок "
                u"поворачивается так, чтобы она шла вдоль ширины лотка."
            ),
            default=u"", required=True,
        ),
        settings_core.TextField(
            "hatch_length_param",
            u"",
            u"Параметр длины (вдоль высоты лотка)",
            hint=(
                u"Сюда пишется высота лотка плюс запас (у наклонного лотка — длина его "
                u"косого сечения уровнем). Параметры экземпляра пишутся в сам лючок; "
                u"если это параметры типа — кнопка берёт или создаёт тип с нужным "
                u"размером («<тип> 300×200»)."
            ),
            default=u"", required=True,
        ),
        settings_core.NumberField(
            "hatch_margin_mm",
            u"",
            u"Запас к размерам лотка, мм",
            hint=u"На сколько лючок больше лотка по каждому размеру (всего, не с каждой стороны).",
            default=DEFAULT_MARGIN_MM, minimum=0.0,
        ),
        settings_core.NumberField(
            "hatch_offset_mm",
            u"③ Высота",
            u"Смещение лючка от уровня, мм",
            hint=(
                u"0 — лючок на отметке уровня. Положительное — выше уровня (например, "
                u"верх чистого пола). Точка пересечения с наклонным лотком берётся "
                u"на этой же высоте."
            ),
            default=0.0,
        ),
    ],
    intro=(
        u"Кнопка находит, где кабельные лотки (выделенные, иначе все в модели) "
        u"проходят через уровни, и ставит там лючок с размерами лотка плюс запас. "
        u"Повторный запуск не плодит копии: лючок того же семейства на этом уровне "
        u"в той же точке обновляется (размер, поворот)."
    ),
    width=720, height=560,
)

load_saved_values = SETTINGS.load_saved_values
save_values = SETTINGS.save_values
require = SETTINGS.require
get_settings_interactive = SETTINGS.get_settings_interactive
get_settings_silent = SETTINGS.get_settings_silent
