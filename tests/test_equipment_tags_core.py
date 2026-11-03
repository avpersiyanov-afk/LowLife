# -*- coding: utf-8 -*-
from lowlife.equipment_tags_core import merge_existing_entries


class Tag(object):
    def __init__(self, key, pinned=False):
        self.Id = key
        self.Pinned = pinned


def test_new_and_existing_tags_from_multiple_models_are_combined():
    a, b = object(), object()
    old = Tag(10)
    entries = [(a, None, 5), (b, None, 6)]
    assert merge_existing_entries(entries, [(a, old)], int) == entries + [(a, old, None)]
    assert len(entries) == 2


def test_existing_tag_is_included_only_once():
    el, tag = object(), Tag(10)
    entries = [(el, tag, None)]
    assert merge_existing_entries(entries, [(el, tag), (el, tag)], int) == entries


def test_different_tags_of_one_element_are_preserved():
    el, a, b = object(), Tag(10), Tag(11)
    assert merge_existing_entries([], [(el, a), (el, b)], int) == [(el, a, None), (el, b, None)]


def test_pinned_tags_remain_obstacles():
    assert merge_existing_entries([], [(object(), Tag(10, pinned=True))], int) == []


def test_existing_tags_are_arranged_when_nothing_new_is_needed():
    el, tag = object(), Tag(10)
    assert merge_existing_entries([], [(el, tag)], int) == [(el, tag, None)]
