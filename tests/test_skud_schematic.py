# -*- coding: utf-8 -*-
"""Тесты для чистых (без Revit API) функций lowlife.skud_schematic —
разбивка устройств по точкам прохода, сигнатуры состава, подбор группы,
голосование за помещение (majority_value). Модуль импортирует
lowlife.params лениво и с запасным вариантом, поэтому импортируется вне
Revit; params здесь недоступен, и _param_value читает значение из
el.params у fake-элемента (см. tests/README.md, Python 2.7)."""

import pytest

from lowlife import skud_schematic as ss


class _FakeId(object):
    def __init__(self, value):
        self.IntegerValue = value


class FakeDevice(object):
    """Минимальный фейк Revit-элемента: тип + словарь параметров."""

    def __init__(self, type_id, params=None):
        self._type_id = type_id
        self.params = params or {}
        self.Id = _FakeId(id(self))

    def GetTypeId(self):
        return _FakeId(self._type_id)


# --- category_of_from_type_map -------------------------------------------------

def test_category_of_from_type_map_resolves_and_misses():
    cat_of = ss.category_of_from_type_map({10: u"считыватель", 20: u"замок"})
    assert cat_of(FakeDevice(10)) == u"считыватель"
    assert cat_of(FakeDevice(20)) == u"замок"
    assert cat_of(FakeDevice(99)) is None


# --- invert_* ----------------------------------------------------------------

def test_invert_category_device_type_ids():
    flat = ss.invert_category_device_type_ids({u"считыватель": set([1, 2]), u"замок": set([3])})
    assert flat == {1: u"считыватель", 2: u"считыватель", 3: u"замок"}


def test_invert_category_type_id_strings_skips_blank_and_bad():
    flat = ss.invert_category_type_id_strings({u"считыватель": u"5", u"замок": u"", u"кнопка": u"x"})
    assert flat == {5: u"считыватель"}


# --- passage_points_of -----------------------------------------------------

def _dev(type_id, addr, pp=None):
    params = {u"Адрес": addr}
    if pp is not None:
        params[u"ТП"] = pp
    return FakeDevice(type_id, params)


def test_passage_points_empty_param_all_go_to_one():
    devs = [_dev(1, u"F1.2"), _dev(1, u"F1.1")]
    pps = ss.passage_points_of(devs, u"", u"Адрес")
    assert list(pps.keys()) == [u"1"]
    # внутри точки прохода — сортировка по адресу
    assert [d.params[u"Адрес"] for d in pps[u"1"]] == [u"F1.1", u"F1.2"]


def test_passage_points_split_by_param_and_blank_is_one():
    devs = [
        _dev(1, u"F1.1", u"2"),
        _dev(2, u"F1.2", u"1"),
        _dev(3, u"F1.3", u""),      # пусто -> "1"
    ]
    pps = ss.passage_points_of(devs, u"ТП", u"Адрес")
    assert set(pps.keys()) == set([u"1", u"2"])
    assert sorted(d.params[u"Адрес"] for d in pps[u"1"]) == [u"F1.2", u"F1.3"]
    assert [d.params[u"Адрес"] for d in pps[u"2"]] == [u"F1.1"]


def test_passage_points_key_order_is_first_seen():
    devs = [_dev(1, u"F1.1", u"3"), _dev(2, u"F1.2", u"1")]
    pps = ss.passage_points_of(devs, u"ТП", u"Адрес")
    assert list(pps.keys()) == [u"3", u"1"]


# --- signature_of ----------------------------------------------------------

def test_signature_of_counts_by_category_and_reports_uncategorized():
    cat_of = ss.category_of_from_type_map({1: u"считыватель", 2: u"замок"})
    devs = [FakeDevice(1), FakeDevice(1), FakeDevice(2), FakeDevice(999)]
    sig, uncat = ss.signature_of(devs, cat_of)
    assert sig == ((u"замок", 1), (u"считыватель", 2))
    assert uncat == 1


def test_signature_of_is_order_independent():
    cat_of = ss.category_of_from_type_map({1: u"a", 2: u"b"})
    s1, _ = ss.signature_of([FakeDevice(1), FakeDevice(2), FakeDevice(2)], cat_of)
    s2, _ = ss.signature_of([FakeDevice(2), FakeDevice(1), FakeDevice(2)], cat_of)
    assert s1 == s2 == ((u"a", 1), (u"b", 2))


# --- match_group_name ----------------------------------------------------

def test_match_group_name_exact_and_none():
    sigs = {
        u"односторонняя": ((u"геркон", 1), (u"замок", 1), (u"кнопка", 1), (u"считыватель", 1)),
        u"двусторонняя": ((u"геркон", 1), (u"замок", 1), (u"считыватель", 2)),
    }
    target = ((u"геркон", 1), (u"замок", 1), (u"считыватель", 2))
    assert ss.match_group_name(target, sigs) == u"двусторонняя"
    assert ss.match_group_name(((u"замок", 1),), sigs) is None


# --- majority_value ----------------------------------------------------

def test_majority_value_picks_most_common():
    assert ss.majority_value([u"Коридор", u"Тамбур", u"Тамбур"]) == u"Тамбур"


def test_majority_value_ignores_blanks():
    assert ss.majority_value([u"", None, u"Коридор", u""]) == u"Коридор"
    assert ss.majority_value([u"", None]) == u""


def test_majority_value_tie_takes_first_seen():
    assert ss.majority_value([u"Коридор", u"Тамбур"]) == u"Коридор"
    assert ss.majority_value([u"Тамбур", u"Коридор"]) == u"Тамбур"


# --- passage_point_changed --------------------------------------------

def _prev_pp(uids, group):
    return {"devices": dict((u, {}) for u in uids), "group": group}


def test_passage_point_changed_no_previous():
    assert ss.passage_point_changed(None, [u"a", u"b"], u"односторонняя") is True


def test_passage_point_changed_same_set_same_group():
    prev = _prev_pp([u"a", u"b"], u"односторонняя")
    assert ss.passage_point_changed(prev, [u"b", u"a"], u"односторонняя") is False


def test_passage_point_changed_device_added_or_removed():
    prev = _prev_pp([u"a", u"b"], u"односторонняя")
    assert ss.passage_point_changed(prev, [u"a", u"b", u"c"], u"односторонняя") is True
    assert ss.passage_point_changed(prev, [u"a"], u"односторонняя") is True


def test_passage_point_changed_group_switched():
    prev = _prev_pp([u"a", u"b"], u"односторонняя")
    assert ss.passage_point_changed(prev, [u"a", u"b"], u"двусторонняя") is True
    assert ss.passage_point_changed(prev, [u"a", u"b"], None) is True


def test_passage_point_changed_fallback_stays_fallback():
    prev = _prev_pp([u"a", u"b"], None)
    assert ss.passage_point_changed(prev, [u"a", u"b"], None) is False


# --- group_by_category_ordered ---------------------------------------

def test_group_by_category_ordered_keeps_first_seen_order():
    cat_of = ss.category_of_from_type_map({1: u"считыватель", 2: u"замок"})
    devs = [FakeDevice(2), FakeDevice(1), FakeDevice(1), FakeDevice(99)]
    grouped = ss.group_by_category_ordered(devs, cat_of)
    assert [c for c, _ in grouped] == [u"замок", u"считыватель"]
    assert [len(v) for _, v in grouped] == [1, 2]


# --- signature_text ----------------------------------------------------

def test_signature_text_formatting():
    sig = ((u"геркон", 1), (u"считыватель", 2))
    assert ss.signature_text(sig) == u"геркон + считыватель x2"
    assert ss.signature_text(()) == u"(пусто)"
