# -*- coding: utf-8 -*-
"""Тесты для lowlife.sot_sections — деление структурной схемы СОТ на блоки
«Корпус → Секция» (чистая логика, без Revit API)."""

from lowlife import sot_sections
from lowlife.sot_sections import split_into_groups, group_label, NO_BUILDING, NO_SECTION


def _split(items, use_building=True, use_section=True):
    return split_into_groups(
        items,
        (lambda it: it[0]) if use_building else (lambda it: None),
        (lambda it: it[1]) if use_section else (lambda it: None),
    )


def test_without_params_single_group_without_label():
    items = [(u"1", u"1"), (u"2", u"3")]
    groups = _split(items, use_building=False, use_section=False)
    assert len(groups) == 1
    assert groups[0]["key"] == u""
    assert groups[0]["label"] == u""
    assert groups[0]["items"] == items


def test_sections_are_scoped_inside_building():
    # Секция 1 корпуса 1 и секция 1 корпуса 2 — разные блоки.
    items = [(u"1", u"1"), (u"2", u"1"), (u"1", u"2"), (u"1", u"1")]
    groups = _split(items)
    assert [g["label"] for g in groups] == [
        u"Корпус 1, секция 1", u"Корпус 1, секция 2", u"Корпус 2, секция 1"
    ]
    assert groups[0]["items"] == [(u"1", u"1"), (u"1", u"1")]


def test_natural_order_of_buildings_and_sections():
    items = [(u"10", u"2"), (u"2", u"10"), (u"2", u"9")]
    groups = _split(items)
    assert [(g["building"], g["section"]) for g in groups] == [
        (u"2", u"9"), (u"2", u"10"), (u"10", u"2")
    ]


def test_empty_values_go_to_placeholder_group_last():
    items = [(u"", u"1"), (u"1", u" "), (u"1", u"1")]
    groups = _split(items)
    assert [(g["building"], g["section"]) for g in groups] == [
        (u"1", u"1"), (u"1", NO_SECTION), (NO_BUILDING, u"1")
    ]


def test_only_section_param():
    groups = _split([(u"x", u"2"), (u"y", u"1")], use_building=False)
    assert [g["label"] for g in groups] == [u"Секция 1", u"Секция 2"]


def test_label_does_not_duplicate_words():
    assert group_label(u"Корпус А", u"Секция 3") == u"Корпус А, секция 3"
    assert group_label(u"К1", None) == u"Корпус К1"
    assert group_label(NO_BUILDING, NO_SECTION) == u"(без корпуса), (без секции)"


def test_keys_unique_per_pair():
    assert sot_sections.group_key(u"1", u"12") != sot_sections.group_key(u"11", u"2")
    assert sot_sections.group_key(None, None) == u""
