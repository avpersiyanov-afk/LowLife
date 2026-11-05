# -*- coding: utf-8 -*-
"""Saved user criterion for hiding elements of selected Revit links."""
from lowlife import settings_core
from lowlife.i18n import N_

SETTINGS = settings_core.TextSettings(
    file_name="LowLifeLinkHide_settings.json",
    button_name=N_(u"Скрыть в связи"),
    heading=N_(u"Условие скрытия элементов связи"),
    transfer_label=N_(u"скрытия элементов связи"),
    intro=N_(u"Условие применяется при запуске к текущему виду. Связи и категории выбираются отдельно. Это разовое скрытие, а не автоматически обновляемый фильтр."),
    fields=[
        settings_core.ChoiceField("field", u"", N_(u"Проверять"), [
            ("family", N_(u"Имя семейства")),
            ("type", N_(u"Имя типа")),
            ("parameter", N_(u"Значение параметра")),
            ("workset", N_(u"Имя рабочего набора")),
        ]),
        settings_core.TextField("filter_param_name", u"", N_(u"Имя параметра для условия"),
            hint=N_(u"Только для проверки значения параметра. Имена доступны из основной модели и загруженных связей.")),
        settings_core.ChoiceField("scope", u"", N_(u"Где искать параметр"), [
            ("instance_or_type", N_(u"Экземпляр, иначе тип")),
            ("instance", N_(u"Только экземпляр")),
            ("type", N_(u"Только тип")),
        ], hint=N_(u"Переход к типу — только если параметра нет у экземпляра. Пустое значение экземпляра не заменяется значением типа.")),
        settings_core.ChoiceField("operator", u"", N_(u"Условие"), [
            ("contains", N_(u"Содержит")),
            ("equals", N_(u"Равно")),
            ("not_contains", N_(u"Не содержит")),
            ("not_equals", N_(u"Не равно")),
            ("starts_with", N_(u"Начинается с")),
            ("empty", N_(u"Пусто")),
            ("not_empty", N_(u"Не пусто")),
        ]),
        settings_core.TextField("value", u"", N_(u"Значение для сравнения"),
            hint=N_(u"Текст без учёта регистра и пробелов по краям. Числа сравниваются как текст в единицах Revit. Для «Пусто» и «Не пусто» значение не нужно. Отсутствующий параметр не считается совпадением.")),
    ], width=780, height=760,
)
