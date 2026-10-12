# -*- coding: utf-8 -*-
"""
Настройки кнопки «Секущий диапазон» (Tools.panel/AlignViewRange) — шаблон
имени уровня, по которому ищется следующий этаж (верх диапазона).

JSON-файл %APPDATA%\\pyRevit\\LowLifeViewRange_settings.json, обвязка —
settings_core.TextSettings. Шаблон — тот же формат, что у «Разреза по
семейству» (level_name_template), но свой: у видов и у разрезов он может
отличаться. Пока шаблон здесь ни разу не сохранён, берётся шаблон из
настроек «Разреза по семейству» (раньше кнопка пользовалась им), а если и
там пусто — шаблон по умолчанию.
"""

from lowlife import level_name_template, settings_core

LEVEL_TEMPLATE_KEY = "level_name_template"

# Файл настроек «Разреза по семейству» — читается только как запасной
# источник шаблона (family_section_settings тянет WPF, поэтому напрямую).
_FAMILY_SECTION_FILE = "LowLifeFamilySection_settings.json"


class LevelTemplateField(settings_core.TextField):
    """Поле шаблона имени уровня: неверный шаблон окно не пропускает."""

    def parse(self, text):
        value = (text or u"").strip()
        error = level_name_template.validate(value)
        if error:
            return None, u"{} — {}".format(self.title(), error)
        return value, None

    def coerce(self, value):
        value = value.strip() if isinstance(value, settings_core._string_types) else u""
        if level_name_template.validate(value):
            return self.default
        return value


def _migrate(saved, values):
    """Шаблон ещё не сохранялся здесь — взять из «Разреза по семейству»."""
    if (saved.get(LEVEL_TEMPLATE_KEY) or u"").strip():
        return
    other = settings_core.JsonStore(_FAMILY_SECTION_FILE, share=False).read()
    fallback = (other.get(LEVEL_TEMPLATE_KEY) or u"").strip()
    if fallback and not level_name_template.validate(fallback):
        values[LEVEL_TEMPLATE_KEY] = fallback


SETTINGS = settings_core.TextSettings(
    file_name="LowLifeViewRange_settings.json",
    button_name=u"Секущий диапазон",
    heading=u"Секущий диапазон: определение верхнего уровня",
    transfer_label=u"секущего диапазона",
    fields=[
        LevelTemplateField(
            LEVEL_TEMPLATE_KEY,
            u"Шаблон имени уровня",
            u"",
            hint=(
                u"Как в ваших именах уровней записаны корпус и этаж. {Корпус}, "
                u"{Этаж} и {Комментарий} — значимые части, любые другие имена в "
                u"скобках ({Дисциплина}, {Отметка}, ...) — пропускаемые; текст "
                u"между скобками должен совпадать буквально. {Этаж} обязателен; "
                u"без {Корпус} все уровни считаются одним корпусом; {Комментарий} "
                u"в конце необязателен.\n\n"
                u"Верх диапазона — ближайший уровень выше с тем же корпусом и "
                u"другим этажом (из уровней этого этажа — основной, без "
                u"комментария), смещение −200 мм. Если имя уровня плана не "
                u"подходит под шаблон — верх берётся по ближайшему уровню выше "
                u"из всех.\n\n"
                u"Примеры: «{Дисциплина}_{Корпус}_{Отметка}_{Этаж}_{Комментарий}» "
                u"(по умолчанию), «{Корпус}-{Этаж}», «Этаж {Этаж}», "
                u"«{Этаж}_{Комментарий}»."
            ),
            default=level_name_template.DEFAULT_TEMPLATE, required=True,
        ),
    ],
    migrate=_migrate,
    reset_button=True,
    width=620, height=440,
)

load_saved_values = SETTINGS.load_saved_values
save_values = SETTINGS.save_values
show_settings_form = SETTINGS.show_settings_form
get_settings_interactive = SETTINGS.get_settings_interactive
get_settings_silent = SETTINGS.get_settings_silent
