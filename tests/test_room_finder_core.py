# -*- coding: utf-8 -*-
"""Тесты для lowlife.room_finder_core — сравнение имён уровней хоста и
связи в «Найти помещение»."""

from lowlife import room_finder_core as core


def test_building_aliases_match():
    assert core.same_level(u"ПЧ_Этаж 01", u"0_Этаж 01")
    assert core.same_level(u"ПЧ_Этаж 01", u"00_Этаж 01")
    assert core.same_level(u"0_Этаж 01", u"00_Этаж 01")
    assert core.same_level(u"Корпус ПЧ. Этаж -1", u"Корпус 0. Этаж -1")


def test_other_parts_must_still_match():
    assert not core.same_level(u"ПЧ_Этаж 01", u"0_Этаж 02")
    assert not core.same_level(u"1_Этаж 01", u"0_Этаж 01")
    assert not core.same_level(u"ПЧ_Этаж 01", u"10_Этаж 01")


def test_alias_only_as_whole_token():
    assert not core.same_level(u"ПЧ1_Этаж 01", u"01_Этаж 01")


def test_exact_and_empty():
    assert core.same_level(u"Этаж 1", u"Этаж 1")
    assert not core.same_level(u"", u"Этаж 1")
    assert not core.same_level(None, None)
