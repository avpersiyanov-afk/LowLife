# -*- coding: utf-8 -*-
"""Тесты для lowlife.spellcheck_core — чистая логика кнопки «Проверка
орфографии»: склейка одинаковых текстов, пачки, разбор ответа ИИ, отсев
плохих исправлений и минимальные замены для FormattedText заметки."""

import json
import random

import pytest

from lowlife import spellcheck_core as sc


def test_split_and_full_text_keep_revit_line_breaks():
    plain = u"  Щит освещения\rЩО-1\r"
    head, body, tail = sc.split_text(plain)
    assert (head, body, tail) == (u"  ", u"Щит освещения\nЩО-1", u"\r")
    assert sc.full_text(plain, u"Щит освещения\nЩО-1") == plain
    # Ответ ИИ с \r\n — всё равно разделитель Revit
    assert sc.full_text(plain, u"Щит  освещения\r\nЩО-1") == u"  Щит  освещения\rЩО-1\r"


def test_collect_items_merges_same_text_and_skips_numbers():
    notes = [(1, u"Кабельный лоток\r"), (2, u"12-34\r"), (3, u"Кабельный лоток"), (4, u"Розетка")]
    items = sc.collect_items(notes)
    assert [i["text"] for i in items] == [u"Кабельный лоток", u"Розетка"]
    assert [i["id"] for i in items] == [1, 2]
    assert [k for k, _ in items[0]["notes"]] == [1, 3]


def test_make_batches_by_size():
    items = [{"id": n, "text": u"х" * 100} for n in range(1, 11)]
    batches = sc.make_batches(items, batch_chars=400)
    assert [len(b) for b in batches] == [3, 3, 3, 1]
    assert sc.make_batches([], 400) == []


def test_build_request_contains_prompt_and_items():
    request = sc.build_request(u"Исправь ошибки.\n", [{"id": 7, "text": u"тескт"}])
    assert request.startswith(u"Исправь ошибки.\n\nТексты (JSON):\n")
    payload = json.loads(request.split(u"\n", 3)[3])
    assert payload == {"items": [{"id": 7, "text": u"тескт"}]}


def test_parse_fixes_variants():
    assert sc.parse_fixes(u'{"fixes":[{"id":1,"text":"текст"}]}') == {1: u"текст"}
    fenced = u'Вот:\n```json\n{"fixes": [{"id": "2", "text": "щит"}, {"id": "x"}]}\n```'
    assert sc.parse_fixes(fenced) == {2: u"щит"}
    assert sc.parse_fixes(u'[{"id": 3, "text": "a"}]') == {3: u"a"}
    assert sc.parse_fixes(u'{"fixes": []}') == {}
    with pytest.raises(sc.ParseError):
        sc.parse_fixes(u"ошибок нет")
    with pytest.raises(sc.ParseError):
        sc.parse_fixes(u"  ")


def test_review_fix():
    assert sc.review_fix(u"Кабельный лоток", u"Кабельный лоток") == (sc.FIX_SAME, u"Кабельный лоток")
    assert sc.review_fix(u"Кабельный лоток", u"  ")[0] == sc.FIX_EMPTY
    assert sc.review_fix(u"Кабелный лоток", u"Кабельный лоток") == (sc.FIX_OK, u"Кабельный лоток")
    assert sc.review_fix(u"Щит ЩО-1", u"Совершенно другой текст про иное")[0] == sc.FIX_REWRITE


@pytest.mark.parametrize("old,new", [
    (u"Кабелный лоток", u"Кабельный лоток"),
    (u"Щит освещения ЩО-1", u"Щит освещения, ЩО-1"),       # вставка
    (u"Щит  освещения", u"Щит освещения"),                 # удаление пробела
    (u"установить розетку", u"Установить розетку."),       # начало и конец
    (u"а б в", u"а б в г"),
    (u"трасса\rкабеля\r", u"трасса\rкабелей\r"),
    (u"x", u"y"),
    (u"привет", u", привет"),                              # вставка в самое начало
])
def test_replacement_spans_rebuild_new_text(old, new):
    spans = sc.replacement_spans(old, new)
    assert sc.apply_spans(old, spans) == new
    for start, length, _text in spans:
        assert length >= 1
    starts = [s for s, _l, _t in spans]
    assert starts == sorted(starts)
    for (s1, l1, _a), (s2, _l2, _b) in zip(spans, spans[1:]):
        assert s1 + l1 <= s2


def test_replacement_spans_touch_only_changed_words():
    old = u"Кабелный лоток по стене, высота монтажа 2,5 м"
    new = u"Кабельный лоток по стене, высота монтажа 2,5 м"
    assert sc.replacement_spans(old, new) == [(0, 8, u"Кабельный")]
    assert sc.replacement_spans(old, old) == []


def test_replacement_spans_random_edits():
    rnd = random.Random(1)
    words = [u"щит", u"лоток", u"кабель", u",", u" ", u"  ", u".", u"ВК-1", u"\r", u"2,5"]
    for _ in range(300):
        old = u"".join(rnd.choice(words) for _ in range(rnd.randint(1, 12)))
        new = u"".join(rnd.choice(words) for _ in range(rnd.randint(0, 12)))
        if not new:
            continue
        spans = sc.replacement_spans(old, new)
        assert sc.apply_spans(old, spans) == new
        assert all(length >= 1 for _s, length, _t in spans)


def test_describe_changes():
    assert sc.describe_changes(u"Кабелный лоток", u"Кабельный лоток") == u"Кабелный → Кабельный"
    text = sc.describe_changes(u"Щит  освещения", u"Щит освещения")
    assert u"→" in text
