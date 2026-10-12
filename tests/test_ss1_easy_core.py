# -*- coding: utf-8 -*-
from lowlife import ss1_easy_core as core


def test_split_names():
    assert core.split_names(u"Коридор, Вестибюль; Холл\n") == [u"Коридор", u"Вестибюль", u"Холл"]
    assert core.split_names(u"") == []
    assert core.split_names(None) == []


def test_shaft_spans_level():
    tol = 0.3
    # шахта на всё здание 0..30
    assert core.shaft_spans_level(0.0, 30.0, 0.0, tol)
    assert core.shaft_spans_level(0.0, 30.0, 20.0, tol)
    # заканчивается ровно на уровне — его не проходит
    assert not core.shaft_spans_level(0.0, 30.0, 30.0, tol)
    # начинается выше уровня
    assert not core.shaft_spans_level(10.0, 30.0, 0.0, tol)
    # низ чуть ниже/выше уровня в пределах допуска
    assert core.shaft_spans_level(10.2, 20.0, 10.0, tol)
    # поэтажная шахта 10..20 не проходит уровни 0 и 20
    assert not core.shaft_spans_level(10.0, 20.0, 20.0, tol)


def test_door_target_side():
    neighbors = [u"Коридор", u"Вестибюль"]
    assert core.door_target_side(u"Прихожая", u"коридор", u"Прихожая", neighbors) == "from"
    assert core.door_target_side(u"Вестибюль", u"Прихожая", u"Прихожая", neighbors) == "to"
    assert core.door_target_side(u"Прихожая", u"Кухня", u"Прихожая", neighbors) is None
    assert core.door_target_side(u"", u"", u"Прихожая", neighbors) is None


def test_lowest_room_per_lot_duplex_and_empty_lot():
    rooms = [
        (1, u"Кв.1", 10.0),
        (2, u"кв.1 ", 0.0),   # тот же лот ниже — остаётся он
        (3, u"Кв.2", 0.0),
        (4, u"", 0.0),        # без лота — каждый отдельно
        (5, u"", 10.0),
        (6, u"Кв.3", None),
    ]
    keep, no_lot = core.lowest_room_per_lot(rooms)
    assert keep == {2, 3, 4, 5, 6}
    assert no_lot == [4, 5]


def test_match_level():
    levels = [("L1", 0.0), ("L2", 10.0), ("L3", 10.2)]
    assert core.match_level(10.15, levels, 0.3) == "L3"
    assert core.match_level(0.1, levels, 0.3) == "L1"
    assert core.match_level(5.0, levels, 0.3) is None


def test_dedupe_key():
    assert core.dedupe_key(1.0, 2.0, 7) == core.dedupe_key(1.01, 2.01, 7)
    assert core.dedupe_key(1.0, 2.0, 7) != core.dedupe_key(1.0, 2.0, 8)


def test_filter_names():
    names = [u"Шахта инж. коммуникаций", u"Кросс распределительный оптический", u"Подвод кабельный"]
    assert core.filter_names(names, u"") == names
    assert core.filter_names(names, u"  ") == names
    assert core.filter_names(names, u"КРОСС") == [names[1]]
    assert core.filter_names(names, u"кабельный подвод") == [names[2]]
    assert core.filter_names(names, u"опт рас") == [names[1]]
    assert core.filter_names(names, u"лоток") == []


def test_pick_shaft_by_section_then_nearest():
    shafts = [("A1", 0.0, 0.0, u"1"), ("A2", 100.0, 0.0, u"1"), ("B", 10.0, 0.0, u"2")]
    # своя секция, ближайшая из неё — даже если чужая шахта ближе
    assert core.pick_shaft(90.0, 0.0, u" 1 ", shafts) == ("A2", None)
    assert core.pick_shaft(9.0, 0.0, u"1", shafts) == ("A1", None)
    assert core.pick_shaft(9.0, 0.0, u"2", shafts) == ("B", None)
    # шахт этой секции нет
    assert core.pick_shaft(0.0, 0.0, u"3", shafts) == (None, "no_section")
    # секция помещения не заполнена — ближайшая с предупреждением
    assert core.pick_shaft(9.0, 0.0, u"", shafts) == ("B", "no_room_section")
    assert core.pick_shaft(0.0, 0.0, u"1", []) == (None, "no_shafts")


def test_face_distance_axis_and_face_location_lines():
    # линия привязки по оси: грани на ±0.5
    assert core.face_distance([0.5, -0.5], 1, 0.5) == 0.5
    assert core.face_distance([0.5, -0.5], -1, 0.5) == 0.5
    # линия привязки по грани: одна грань в точке двери, другая на -1.0
    assert core.face_distance([0.0, -1.0], 1, 0.5) == 0.0
    assert core.face_distance([0.0, -1.0], -1, 0.5) == 1.0
    # слои: берётся внешняя грань
    assert core.face_distance([0.2, 0.6, -0.4], 1, 0.5) == 0.6
    # граней нет — половина толщины
    assert core.face_distance([], 1, 0.5) == 0.5


def test_parse_letter_params():
    assert core.parse_letter_params(u"A=Этаж; B=Секция; C=Номер квартиры") == (
        [(u"A", u"Этаж"), (u"B", u"Секция"), (u"C", u"Номер квартиры")], [])
    # новая строка и двоеточие, русская буква = латинская
    assert core.parse_letter_params(u"К: Корпус\nF = Этаж") == (
        [(u"K", u"Корпус"), (u"F", u"Этаж")], [])
    assert core.parse_letter_params(u"") == ([], [])
    pairs, errors = core.parse_letter_params(u"A=Этаж; AB=Секция; C=; D; А=Ещё")
    assert pairs == [(u"A", u"Этаж")]
    assert len(errors) == 4


def test_format_address():
    values = {"A": u"3", "B": u"1", "C": u"45"}
    assert core.format_address(u"A.B.C", values) == (u"3.1.45", [])
    # русские буквы в маске
    assert core.format_address(u"А.В.С", values) == (u"3.1.45", [])
    # буквы без параметра остаются текстом
    assert core.format_address(u"Кв C (A-B)", values) == (u"Кв 45 (3-1)", [])
    assert core.format_address(u"K-F.S", {"K": u"1", "F": u"02", "S": u"3"}) == (u"1-02.3", [])
    assert core.format_address(u"A.B.C", {"A": u"3", "B": u" ", "C": None}) == (u"3..", [u"B", u"C"])
    assert core.format_address(u"", values) == (u"", [])
