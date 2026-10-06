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


def test_unique_name():
    assert core.unique_name(u"Э", set()) == u"Э"
    assert core.unique_name(u"Э", {u"Э", u"Э (2)"}) == u"Э (3)"


def test_in_rect():
    assert core.in_rect(1, 1, (0, 0, 2, 2))
    assert not core.in_rect(3, 1, (0, 0, 2, 2))


def test_default_columns_follow_gost_form():
    assert [c[1] for c in core.COLUMNS] == [
        u"Номер помещения", u"Наименование", u"Площадь, м²", u"Кат. помещения"]


def test_default_sizes_match_gost_form_2():
    assert [c[2] for c in core.COLUMNS] == [15.0, 80.0, 20.0, 10.0]
    assert sum(c[2] for c in core.COLUMNS) == 125.0
    assert (core.HEADER_HEIGHT_MM, core.ROW_HEIGHT_MM) == (20.0, 8.0)


def test_old_default_widths_migrate_to_gost():
    from lowlife import room_explication_settings as rs
    values = {"width_name": 60.0, "width_category": 15.0}
    rs._migrate({"width_name": 60, "width_category": u"15"}, values)
    assert values == {"width_name": 80.0, "width_category": 10.0}
    custom = {"width_name": 70.0, "width_category": 15.0}
    rs._migrate({"width_name": 70, "width_category": 15}, custom)
    assert custom == {"width_name": 70.0, "width_category": 15.0}
