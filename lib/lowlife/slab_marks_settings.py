# -*- coding: utf-8 -*-
"""
Настройки кнопки «Извещатели на перекрытие» (SPS.panel/DetectorsToSlab) +
их хранение между запусками (%APPDATA%\\pyRevit\\LowLifeSlabMarks_settings.json).

Обвязка (хранение, окно, Shift+клик/тихий режим) — общая,
settings_core.TextSettings; здесь только описание полей. Имён параметров
модели кнопка не использует: извещатели отбираются по словам в имени
семейства/типа, перекрытия и потолки — по категориям Revit.
"""

from lowlife import settings_core


SETTINGS = settings_core.TextSettings(
    file_name="LowLifeSlabMarks_settings.json",
    button_name=u"Извещатели на перекрытие",
    heading=u"Извещатели на перекрытие и отметки перекрытий",
    transfer_label=u"кнопки «Извещатели на перекрытие»",
    fields=[
        settings_core.TextField(
            "detector_include_words",
            u"① Какие устройства перемещать",
            u"Слова в имени семейства или типа (через запятую)",
            hint=(
                u"Берутся элементы категории «Пожарная сигнализация», в имени семейства "
                u"или типа которых есть хотя бы одно слово (без учёта регистра). Пусто — "
                u"все устройства категории."
            ),
            default=u"дым, тепл, пламен, газ, ИП 212, ИП212, ИП 101, ИП101",
        ),
        settings_core.TextField(
            "detector_exclude_words",
            u"",
            u"Исключить, если в имени есть (через запятую)",
            hint=u"Ручные извещатели, оповещатели, модули и т. п. — их на перекрытие не переносить.",
            default=u"ручн, ИПР, ИП 535, ИП535, оповещ, модул, изолятор",
        ),
        settings_core.TextField(
            "ceiling_mount_words",
            u"",
            u"Встраиваемые — ставить на подвесной потолок, если в имени есть (через запятую)",
            hint=(
                u"Такие извещатели ставятся на низ подвесного потолка, а не на перекрытие. "
                u"Если потолка над ним нет — не переносится и попадает в отчёт. Пусто — "
                u"все на перекрытие."
            ),
            default=u"встраив",
        ),
        settings_core.NumberField(
            "mount_offset_mm",
            u"② Установка",
            u"Отступ точки вставки от низа перекрытия, мм",
            hint=(
                u"0 — точка вставки семейства ровно на низ перекрытия. Положительное "
                u"значение опускает извещатель ниже перекрытия."
            ),
            default=0.0,
        ),
        settings_core.NumberField(
            "probe_height_mm",
            u"",
            u"Высота точки проверки над уровнем, мм",
            hint=(
                u"Из этой точки (над уровнем этажа) луч идёт вверх до перекрытия/потолка "
                u"и вниз до пола. Должна быть выше пола и ниже подвесного потолка."
            ),
            default=1500.0, minimum=1.0,
        ),
        settings_core.NumberField(
            "level_tolerance_mm",
            u"",
            u"Допуск сопоставления уровня помещения связи с уровнем вида, мм",
            default=300.0, minimum=0.0,
        ),
        settings_core.NumberField(
            "round_mm",
            u"③ Подписи на видах",
            u"Округление высот, мм",
            hint=u"Высоты, отличающиеся меньше чем на этот шаг, считаются одной отметкой.",
            default=10.0, minimum=1.0,
        ),
        settings_core.TextField(
            "slab_text_format",
            u"",
            u"Подпись высоты перекрытия от пола ({h} — отметка)",
            default=u"Пер. {h}",
        ),
        settings_core.TextField(
            "delta_text_format",
            u"",
            u"Подпись изменения высоты перекрытия ({d} — разница с типовой)",
            hint=(
                u"Добавляется в помещениях, где перекрытие выше/ниже типовой (самой частой) "
                u"высоты на этом виде."
            ),
            default=u"Δ {d}",
        ),
        settings_core.TextField(
            "ceiling_text_format",
            u"",
            u"Подпись подвесного потолка ({h} — отметка от пола)",
            default=u"ПП {h}",
        ),
        settings_core.NumberField(
            "step_line_weight",
            u"④ Перепад плиты",
            u"Толщина красной линии перепада (1–16)",
            hint=(
                u"Линия рисуется стилем «LowLife — перепад плиты» (красный); толщина "
                u"обновляется на каждом запуске."
            ),
            default=10, minimum=1, integer=True,
        ),
        settings_core.NumberField(
            "step_search_mm",
            u"",
            u"Наибольший зазор в плане между краями соседних плит, мм",
            hint=(
                u"Края нижних граней плит с разной отметкой, лежащие не дальше этого друг "
                u"от друга, считаются перепадом (линия — посередине). Больше — найдутся "
                u"плиты, разделённые стеной или балкой."
            ),
            default=300.0, minimum=1.0,
        ),
        settings_core.TextField(
            "filled_region_type_name",
            u"",
            u"Тип области заливки для помещений с подвесным потолком",
            hint=u"Пусто — первый тип области заливки проекта (не маскирующий).",
            default=u"",
        ),
    ],
    width=760, height=700,
)

load_saved_values = SETTINGS.load_saved_values
get_settings_interactive = SETTINGS.get_settings_interactive
get_settings_silent = SETTINGS.get_settings_silent
