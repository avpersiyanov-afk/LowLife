# -*- coding: utf-8 -*-
"""Тесты для lowlife.level_name_template — разбор имени уровня по шаблону
(корпус/этаж/комментарий для «Разреза по семейству», чистая логика)."""

from lowlife.level_name_template import LevelNameTemplate, DEFAULT_TEMPLATE, validate


def _parse(name, template=DEFAULT_TEMPLATE):
    return LevelNameTemplate(template).parse(name)


def test_default_template_without_comment():
    assert _parse(u"АР_К1_+0.000_01") == (u"к1", u"01", u"")


def test_default_template_with_comment():
    assert _parse(u"АР_К1_+0.000_01_низ перекрытия") == (u"к1", u"01", u"низ перекрытия")


def test_default_template_comment_may_contain_separator():
    assert _parse(u"АР_К1_+3.300_02_низ_плиты") == (u"к1", u"02", u"низ_плиты")


def test_default_template_strips_and_lowercases():
    assert _parse(u"АР_ К1 _+0.000_ Эт01 ") == (u"к1", u"эт01", u"")


def test_default_template_too_few_fields_is_none():
    assert _parse(u"Уровень 1") is None
    assert _parse(u"АР_К1_+0.000") is None


def test_default_template_empty_floor_or_building_is_none():
    assert _parse(u"АР__+0.000_01") is None
    assert _parse(u"АР_К1_+0.000_") is None


def test_custom_template_with_dash():
    assert _parse(u"К2-Этаж 03", u"{Корпус}-{Этаж}") == (u"к2", u"этаж 03", u"")


def test_custom_template_literal_text_and_special_chars():
    tpl = u"Уровень {Этаж} (корпус {Корпус})"
    assert _parse(u"Уровень 5 (корпус 1)", tpl) == (u"1", u"5", u"")
    assert _parse(u"Уровень 5 корпус 1", tpl) is None


def test_template_without_building_puts_everything_in_one_building():
    assert _parse(u"Этаж 07", u"Этаж {Этаж}") == (u"", u"07", u"")


def test_comment_in_the_middle_is_required():
    tpl = u"{Корпус}.{Комментарий}.{Этаж}"
    assert _parse(u"К1.низ.02", tpl) == (u"к1", u"02", u"низ")
    assert _parse(u"К1.02", tpl) is None


def test_validate_errors():
    assert validate(DEFAULT_TEMPLATE) is None
    assert validate(u"") is not None
    assert validate(u"{Корпус}_{Отметка}") is not None          # нет {Этаж}
    assert validate(u"{Этаж}_{Этаж}") is not None               # дважды
    assert validate(u"{Корпус}_{Этаж") is not None              # незакрытая скобка
    assert validate(u"{}_{Этаж}") is not None                   # пустые скобки


def test_invalid_template_never_parses():
    assert LevelNameTemplate(u"{Корпус}").parse(u"К1") is None
