# -*- coding: utf-8 -*-
"""Тесты для lowlife.level_views_core — кнопка «Виды по уровням»: имя вида
по маске (уровень, значение шаблона, части имени уровня), проверка маски,
настройки окна."""

import pytest

from lowlife import level_name_template
from lowlife import level_views_core as core


def test_build_view_name_level_and_value():
    values = core.level_tokens(u"Этаж 02", 3300.0, None)
    assert core.build_view_name(u"{Уровень}_{Значение}", values, u"ЭОМ_Свет", u"Освещение") \
        == u"Этаж 02_Освещение"
    assert core.build_view_name(u"{Значение} ({Шаблон}) {Отметка}", values, u"ЭОМ_Свет", u"Свет") \
        == u"Свет (ЭОМ_Свет) +3.300"


def test_build_view_name_with_level_template_parts():
    tpl = level_name_template.LevelNameTemplate(u"{Дисциплина}_{Корпус}_{Отметка}_{Этаж}_{Комментарий}")
    name = u"АР_К1_+3.300_02"
    values = core.level_tokens(name, 3300.0, tpl.parse(name))
    assert core.build_view_name(u"{Корпус} {Этаж} этаж. {Значение}", values, u"T", u"Силовое") \
        == u"К1 02 этаж. Силовое"


def test_build_view_name_cleans_empty_parts_and_bad_chars():
    values = core.level_tokens(u"Уровень 1", 0.0, None)
    # {Этаж} пустой (имя не по шаблону) — двойной «_» схлопывается.
    assert core.build_view_name(u"{Уровень}_{Этаж}_{Значение}", values, u"T", u"Свет") \
        == u"Уровень 1_Свет"
    assert core.build_view_name(u"{Уровень}: [{Значение}]", values, u"T", u"") == u"Уровень 1"
    minus = core.level_tokens(u"П1", -2700.0, None)
    assert core.build_view_name(u"{Отметка}_{Значение}", minus, u"T", u"Свет") == u"-2.700_Свет"


@pytest.mark.parametrize("mm, text", [
    (0.0, u"±0.000"), (3300.0, u"+3.300"), (-2700.4, u"-2.700"),
])
def test_format_elevation(mm, text):
    assert core.format_elevation(mm) == text


def test_validate_mask():
    assert core.validate_mask(u"{Уровень}_{Значение}") is None
    assert u"неизвестные" in core.validate_mask(u"{Уровень}_{Марка}")
    assert u"скобка" in core.validate_mask(u"{Уровень")
    assert core.validate_mask(u"  ") == u"маска пустая"


def test_mask_warning():
    assert core.mask_warning(u"{Уровень}_{Значение}", 3) is None
    assert u"{Уровень}" in core.mask_warning(u"{Значение}", 1)
    assert u"{Значение}" in core.mask_warning(u"{Уровень}", 2)
    assert core.mask_warning(u"{Уровень}", 1) is None


def test_normalize_settings():
    s = core.normalize_settings(None)
    assert s == {core.MASK_KEY: core.DEFAULT_MASK, core.VALUES_KEY: {}, core.CHECKED_KEY: []}
    s = core.normalize_settings({core.MASK_KEY: u"{Марка}", core.VALUES_KEY: {u"T": u"v", u"X": 5},
                                 core.CHECKED_KEY: [u"T", 3]})
    assert s[core.MASK_KEY] == core.DEFAULT_MASK
    assert s[core.VALUES_KEY] == {u"T": u"v"}
    assert s[core.CHECKED_KEY] == [u"T"]
