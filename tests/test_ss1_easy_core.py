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


def test_value_matches():
    assert core.value_matches(u"СС", u"сс")
    assert core.value_matches(u" сс ", u"СС")
    assert core.value_matches(u"СБ, СС", u"СС")
    assert core.value_matches(u"СПЗ/СС", u"СС")
    assert not core.value_matches(u"СБ", u"СС")
    assert not core.value_matches(u"СПЗ", u"СС")
    assert not core.value_matches(u"ССТ", u"СС")
    assert not core.value_matches(u"СС", u"")
    assert not core.value_matches(None, u"СС")


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
