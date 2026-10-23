# -*- coding: utf-8 -*-
"""Тесты для lowlife.name_mask — имя по маске из двух параметров
(«Имя нагрузки» / «Имя панели»)."""

from lowlife.name_mask import mask_tokens, validate_mask, missing_tokens, render_mask, DEFAULT_MASK


def test_default_mask_uses_both_params():
    assert mask_tokens(DEFAULT_MASK) == [1, 2]
    assert render_mask(DEFAULT_MASK, {1: u"Р1", 2: u"101"}) == u"Р1-101"


def test_literal_text_and_repeated_tokens():
    assert render_mask(u"Щ{1} (эт. {2}) {1}", {1: u"А", 2: u"3"}) == u"ЩА (эт. 3) А"


def test_single_token_mask():
    assert mask_tokens(u"{2}") == [2]
    assert render_mask(u"{2}", {1: u"x", 2: u"y"}) == u"y"


def test_unknown_braces_kept():
    assert mask_tokens(u"{3}-{a}") == []
    assert render_mask(u"{1}{3}", {1: u"a"}) == u"a{3}"


def test_missing_value_becomes_empty_and_result_stripped():
    assert render_mask(u" {1} {2} ", {1: u"a"}) == u"a"


def test_validate_mask():
    assert validate_mask(u"{1}-{2}") is None
    assert validate_mask(u"") is not None
    assert validate_mask(u"   ") is not None
    assert validate_mask(u"без маркеров") is not None


def test_missing_tokens():
    assert missing_tokens(u"{1}-{2}", {1: u"a", 2: u"  "}) == [2]
    assert missing_tokens(u"{1}", {2: u"b"}) == [1]
    assert missing_tokens(u"{1}", {1: u"a"}) == []
