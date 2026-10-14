# -*- coding: utf-8 -*-
from lowlife import room_explication_core as core


def test_natural_sort_of_numbers():
    nums = [u"1.10", u"1.2", u"10", u"2", u"Б1", u"1.1"]
    assert sorted(nums, key=core.natural_key) == [u"1.1", u"1.2", u"1.10", u"2", u"10", u"Б1"]


def test_format_area():
    assert core.format_area(12.345) == u"12,35"
    assert core.format_area(7, 1) == u"7,0"
    assert core.format_area(7.4, 0) == u"7"


def test_area_text_from_number_or_parameter_text():
    assert core.area_text(12.345) == u"12,35"
    assert core.area_text(u"12.5") == u"12,50"
    assert core.area_text(u" 7,1 ") == u"7,10"
    assert core.area_text(u"12,5 м²") == u"12,5 м²"
    assert core.area_text(None) == u""
    assert core.area_text(u"") == u""


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


def test_key_names_and_key_param_name():
    assert core.key_names(3) == [u"001", u"002", u"003"]
    assert core.key_names(1200)[-1] == u"1200"
    assert core.key_param_name(u"Экспликация - A{B}") == u"Ключ - Экспликация - AB"


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


def _room(number, group=None, sort=None, name=u"П"):
    r = {"number": number, "name": name, "area_m2": 1.0, "category": u""}
    if group is not None:
        r["group"] = group
    if sort is not None:
        r["sort"] = sort
    return r


def test_build_table_groups_with_headers_and_number_order_inside():
    rooms = [_room(u"2.10", u"Секция 2"), _room(u"1.2", u"Секция 1"),
             _room(u"2.9", u"Секция 2"), _room(u"5", u""), _room(u"1.10", u"Секция 1")]
    table = core.build_table(rooms, grouped=True)
    assert [(k, v if k == "group" else v[0]) for k, v in table] == [
        ("group", u"Секция 1"), ("row", u"1.2"), ("row", u"1.10"),
        ("group", u"Секция 2"), ("row", u"2.9"), ("row", u"2.10"),
        ("group", core.NO_GROUP), ("row", u"5"),
    ]
    assert len(core.table_rows(table)) == 5


def test_build_table_without_grouping_is_rows_only():
    table = core.build_table([_room(u"2"), _room(u"1")])
    assert [k for k, _ in table] == ["row", "row"]
    assert core.table_rows(table)[0][0] == u"1"


def test_sort_parameter_inside_group_then_number():
    rooms = [_room(u"1", u"А", sort=u"б"), _room(u"2", u"А", sort=u"а"),
             _room(u"3", u"А", sort=u"а")]
    rows = core.table_rows(core.build_table(rooms, grouped=True))
    assert [r[0] for r in rows] == [u"2", u"3", u"1"]
