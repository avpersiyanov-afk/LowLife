# -*- coding: utf-8 -*-
"""
Логика кнопки «Заполнение этажа» (LOI.panel/FillFloor.pushbutton):
записывает в параметр target_param_name каждого элемента модели значение,
настроенное для уровня этого элемента (settings.level_values, см.
floor_settings.py). «Этаж» элемента определяется его Level
(lowlife.geometry.get_element_level — через Element.LevelId), а не
геометрией/положением на плане.

Элементы без уровня (get_element_level вернул None) и элементы, чей
уровень не настроен в level_values (в таблице настроек для него оставили
пустое значение), пропускаются — это осознанный пропуск, а не ошибка,
поэтому считается отдельно от неудачных записей параметра (см. FillResult).

Проходит по ВСЕМ элементам модели документа (selection.
collect_model_elements_in_document), не по активному виду — тот же довод,
что для «Формы» в loi_fill.py: этаж должен заполняться независимо от
того, что сейчас видно/скрыто на текущем виде.
"""

from lowlife import geometry, params as params_mod, selection


class FillResult(object):
    def __init__(self):
        self.written = 0
        self.no_level = 0
        self.unmapped_levels = set()
        self.failed = []  # (element, param_name) — параметр не найден/нередактируемый


def fill_floors(doc, target_param_name, level_values):
    """
    level_values — {имя уровня: значение} (см. floor_settings.get_level_values).
    Вызывать внутри revit.Transaction. Возвращает FillResult.
    """
    result = FillResult()

    for el in selection.collect_model_elements_in_document(doc):
        level = geometry.get_element_level(doc, el)
        if level is None:
            result.no_level += 1
            continue

        value = level_values.get(geometry.level_name(level))
        if not value:
            result.unmapped_levels.add(geometry.level_name(level))
            continue

        if params_mod.set_param_any(el, target_param_name, value):
            result.written += 1
        else:
            result.failed.append((el, target_param_name))

    return result
