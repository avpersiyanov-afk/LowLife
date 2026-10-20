# -*- coding: utf-8 -*-
"""Тесты для lowlife.text_search — общий поиск полей «Поиск»."""

from lowlife import text_search


def test_matches_part_of_name_case_and_yo():
    assert text_search.matches(u"Счётчик импульсов", u"ЧЕТЧ")
    assert text_search.matches(u"Счётчик импульсов", u"имп счет")  # слова в любом порядке
    assert not text_search.matches(u"Счётчик импульсов", u"имп щит")
    assert text_search.matches(u"что угодно", u"   ")


def test_matches_wrong_layout_both_ways():
    assert text_search.matches(u"Розетка RJ45", u"hjpt")  # «розе» в английской раскладке
    assert text_search.matches(u"Розетка RJ45", u"ко45")  # «rj45» в русской раскладке
    assert text_search.matches(u"Этаж", u"'nf")


def test_query_variants():
    assert text_search.query_variants(u"  Wtgb  ") == [u"wtgb", u"цепи"]
    assert text_search.query_variants(u"цепи") == [u"цепи", u"wtgb"]
    assert text_search.query_variants(u"") == []


def test_rank_order():
    items = [u"Подпись цепи", u"Цепь", u"Номер цепи", u"Длина"]
    # точное → начало → начало слова; при равенстве — исходный порядок
    assert text_search.rank(items, u"цеп") == [u"Цепь", u"Подпись цепи", u"Номер цепи"]
    assert text_search.rank(items, u"цеп", alphabetical=True) == [u"Цепь", u"Номер цепи", u"Подпись цепи"]
    assert text_search.rank(items, u"wtg") == [u"Цепь", u"Подпись цепи", u"Номер цепи"]
    assert text_search.rank(items, u"") == items
    assert text_search.rank(items, u"", limit=2) == items[:2]


def test_rank_key():
    items = [(1, u"Альфа"), (2, u"Бета")]
    assert text_search.rank(items, u"ета", key=lambda x: x[1]) == [(2, u"Бета")]
