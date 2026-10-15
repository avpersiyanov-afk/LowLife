# -*- coding: utf-8 -*-
from lowlife import greeting


def test_part_of_day_boundaries():
    assert greeting.part_of_day(4) == u"Доброй ночи"
    assert greeting.part_of_day(5) == u"Доброе утро"
    assert greeting.part_of_day(12) == u"Добрый день"
    assert greeting.part_of_day(17) == u"Добрый вечер"
    assert greeting.part_of_day(23) == u"Доброй ночи"


def test_lines_with_name_are_upper_case():
    assert greeting.greeting_lines(9, u" Анна ") == (u"ДОБРОЕ УТРО,", u"АННА!")


def test_lines_without_name():
    assert greeting.greeting_lines(13, u"") == (u"ДОБРЫЙ ДЕНЬ!", u"")
    assert greeting.greeting_lines(13, None) == (u"ДОБРЫЙ ДЕНЬ!", u"")
