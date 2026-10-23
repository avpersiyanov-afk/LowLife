# -*- coding: utf-8 -*-
"""
Настройки кнопок «Имя нагрузки» и «Имя панели» (CircuitsGeneric.panel) +
их хранение между запусками.

У каждой кнопки свой JSON-файл в %APPDATA%\\pyRevit
(LowLifeLoadNameMask_settings.json / LowLifePanelNameMask_settings.json):
два параметра-источника и маска (name_mask: {1} — первый параметр, {2} —
второй). «Имя нагрузки» дополнительно спрашивает, в какой параметр цепи
писать (пусто — штатное «Имя нагрузки»); «Имя панели» всегда пишет в
штатное «Имя панели» электрооборудования (circuit_builtins).

Обвязка (хранение, окно, require, Shift+клик/тихий режим) — общая,
settings_core.TextSettings; здесь только описание полей.
"""

from lowlife import settings_core
from lowlife.name_mask import DEFAULT_MASK, validate_mask


class MaskField(settings_core.TextField):
    """Поле маски: «Сохранить» не закроет окно с маской без {1}/{2}."""

    param_spec = None

    def parse(self, text):
        error = validate_mask(text)
        if error:
            return None, u"{} — {}".format(self.title(), error)
        return text, None


_MASK_HINT = (
    u"Текст, в котором {1} заменяется значением первого параметра, {2} — "
    u"второго, остальное переносится как есть: «{1}-{2}», «Щ{1} (эт. {2})», "
    u"«{1}»."
)
_SOURCE_HINT = u"Для имени сначала берётся параметр экземпляра, если его нет — параметр типа."


LOAD_NAME = settings_core.TextSettings(
    file_name="LowLifeLoadNameMask_settings.json",
    button_name=u"Имя нагрузки",
    heading=u"Имя нагрузки цепи по маске",
    transfer_label=u"записи имени нагрузки",
    fields=[
        settings_core.TextField(
            "load_name_first_param",
            u"① Параметры семейства",
            u"Первый параметр — {1}",
            hint=_SOURCE_HINT,
            default=u"", required=True,
        ),
        settings_core.TextField(
            "load_name_second_param",
            u"",
            u"Второй параметр — {2}",
            hint=u"Необязательно, если в маске нет {2}.",
            default=u"", required=False,
        ),
        MaskField(
            "load_name_mask",
            u"② Маска",
            u"",
            hint=_MASK_HINT,
            default=DEFAULT_MASK, required=True,
        ),
        settings_core.TextField(
            "load_name_target_param",
            u"③ Куда писать",
            u"Параметр электрической цепи",
            hint=(
                u"Имя параметра цепи, в который записывается результат. "
                u"Пусто — штатный параметр «Имя нагрузки»."
            ),
            default=u"", required=False,
        ),
    ],
    width=720, height=560,
)


PANEL_NAME = settings_core.TextSettings(
    file_name="LowLifePanelNameMask_settings.json",
    button_name=u"Имя панели",
    heading=u"Имя панели по маске",
    transfer_label=u"записи имени панели",
    intro=(
        u"Результат пишется в штатный параметр электрооборудования «Имя "
        u"панели». Значения сохраняются между запусками."
    ),
    fields=[
        settings_core.TextField(
            "panel_name_first_param",
            u"① Параметры электрооборудования",
            u"Первый параметр — {1}",
            hint=_SOURCE_HINT,
            default=u"", required=True,
        ),
        settings_core.TextField(
            "panel_name_second_param",
            u"",
            u"Второй параметр — {2}",
            hint=u"Необязательно, если в маске нет {2}.",
            default=u"", required=False,
        ),
        MaskField(
            "panel_name_mask",
            u"② Маска",
            u"",
            hint=_MASK_HINT,
            default=DEFAULT_MASK, required=True,
        ),
    ],
    width=720, height=480,
)
