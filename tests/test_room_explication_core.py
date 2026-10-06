# -*- coding: utf-8 -*-
from lowlife import room_explication_core as core


def test_natural_sort_of_numbers():
    nums = [u"1.10", u"1.2", u"10", u"2", u"Б1", u"1.1"]
    assert sorted(nums, key=core.natural_key) == [u"1.1", u"1.2", u"1.10", u"2", u"10", u"Б1"]


def test_format_area():
    assert core.format_area(12.345) == u"12,35"
    assert core.format_area(7, 1) == u"7,0"
    assert core.format_area(7.4, 0) == u"7"


def test_build_rows_sorted_and_deduplicated():
    rooms = [
        {"number": u"10", "name": u"Склад", "area_m2": 5.0, "category": u"В3"},
        {"number": u"2", "name": u" Коридор ", "area_m2": 20.126, "category": None},
        {"number": u"10", "name": u"Склад", "area_m2": 5.0, "category": u"В3"},
    ]
    assert core.build_rows(rooms) == [
        (u"2", u"Коридор", u"20,13", u""),
        (u"10", u"Склад", u"5,00", u"В3"),
    ]


def test_names_are_clean():
    assert core.schedule_name(u"План 1: [фрагмент]") == u"Экспликация - План 1 фрагмент"
    assert core.key_param_name(u"A{B}") == u"Экспликация ключ - AB"


def test_key_names():
    assert core.key_names(3) == [u"001", u"002", u"003"]
    assert core.key_names(1200)[-1] == u"1200"


def test_in_rect():
    assert core.in_rect(1, 1, (0, 0, 2, 2))
    assert not core.in_rect(3, 1, (0, 0, 2, 2))


def test_default_columns_follow_gost_form():
    assert [c[1] for c in core.COLUMNS] == [
        u"Номер помещения", u"Наименование", u"Площадь, м²", u"Кат. помещения"]
