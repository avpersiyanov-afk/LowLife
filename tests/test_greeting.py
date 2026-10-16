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


def _first(pool):
    return pool[0]


def test_no_warning_on_weekday_daytime():
    assert greeting.off_hours_warning(10, 2) is None
    assert greeting.off_hours_warning(22, 4) is None


def test_night_warning():
    assert greeting.off_hours_warning(23, 1, _first) == greeting.NIGHT_WARNINGS[0]
    assert greeting.off_hours_warning(3, 0, _first) == greeting.NIGHT_WARNINGS[0]


def test_weekend_warning():
    assert greeting.off_hours_warning(12, 5, _first) == greeting.WEEKEND_WARNINGS[0]
    assert greeting.off_hours_warning(12, 6, _first) == greeting.WEEKEND_WARNINGS[0]


def test_night_and_weekend_warning():
    assert greeting.off_hours_warning(2, 6, _first) == greeting.NIGHT_WEEKEND_WARNINGS[0]


def test_default_choice_picks_from_pool():
    assert greeting.off_hours_warning(2, 2) in greeting.NIGHT_WARNINGS


def test_morning_wish_on_weekdays_only():
    assert greeting.morning_wish(8, 0, _first) == greeting.MORNING_WISHES[0]
    assert greeting.morning_wish(8, 5, _first) is None
    assert greeting.morning_wish(13, 2, _first) is None


def test_extra_line_prefers_warning():
    assert greeting.extra_line(8, 2, _first) == greeting.MORNING_WISHES[0]
    assert greeting.extra_line(8, 6, _first) == greeting.WEEKEND_WARNINGS[0]
    assert greeting.extra_line(3, 2, _first) == greeting.NIGHT_WARNINGS[0]
    assert greeting.extra_line(14, 2, _first) is None
