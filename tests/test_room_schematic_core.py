# -*- coding: utf-8 -*-
"""Тесты для lowlife.room_schematic_core — подписи помещений «Рыбы
структурной схемы» (Schematic.panel/BuildRoomSchematic): типовые этажи,
копирование подписей по имени, сборка боксов."""

from lowlife import room_schematic_core as core


class Row(object):
    def __init__(self, name, number, label=u"", room_id=None):
        self.name = name
        self.number = number
        self.label = label
        self.room_id = room_id


def _floor(names, labels=None, start_id=0):
    labels = labels or [u""] * len(names)
    return [Row(n, str(i + 1), l, start_id + i) for i, (n, l) in enumerate(zip(names, labels))]


def test_signature_ignores_numbers_case_and_spaces():
    a = _floor([u"Кухня", u"Комната", u"Комната"])
    b = [Row(u"комната ", "205"), Row(u"Кухня", "201"), Row(u"Комната", "203")]
    assert core.floor_signature(a) == core.floor_signature(b)
    assert core.floor_signature(a) != core.floor_signature(_floor([u"Кухня", u"Комната"]))


def test_copy_labels_by_name_keeps_order_within_same_name():
    src = _floor([u"Квартира", u"Квартира", u"Лифт"], [u"Кв. 1", u"Кв. 2", u"МОП"])
    dst = _floor([u"Квартира", u"Лифт", u"Квартира", u"Тамбур"])
    assert core.copy_labels_by_name(src, dst) == 3
    assert [r.label for r in dst] == [u"Кв. 1", u"МОП", u"Кв. 2", u""]


def test_find_typical_source_prefers_nearest_filled_floor_with_same_rooms():
    order = ["L5", "L4", "L3", "L2", "L1"]
    rows = {
        "L5": _floor([u"А", u"Б"]),
        "L4": _floor([u"А", u"Б"], [u"x", u""]),
        "L3": _floor([u"А", u"Б"]),
        "L2": _floor([u"А", u"Б"], [u"y", u""]),
        "L1": _floor([u"Вестибюль"], [u"z"]),
    }
    assert core.find_typical_source(order, rows, "L3") in ("L4", "L2")
    assert core.find_typical_source(order, rows, "L5") == "L4"
    assert core.find_typical_source(order, rows, "L1") is None


def test_find_typical_source_skips_unfilled_floors():
    order = ["L2", "L1"]
    rows = {"L2": _floor([u"А"]), "L1": _floor([u"А"])}
    assert core.find_typical_source(order, rows, "L2") is None


def test_boxes_merge_same_label_and_skip_empty():
    rows = _floor([u"Кв", u"Лифт", u"Кв", u"Кладовая"], [u"Квартиры", u"МОП", u" Квартиры ", u""])
    boxes = core.boxes_for_floor(rows)
    assert [(b["label"], b["kind"], b["room_ids"]) for b in boxes] == [
        (u"Квартиры", "group", [0, 2]),
        (u"МОП", "room", [1]),
    ]


def test_build_boxes_drops_empty_floors_and_keeps_order():
    order = ["L2", "L1"]
    rows = {"L1": _floor([u"А"], [u"a"]), "L2": _floor([u"Б"])}
    assert list(core.build_boxes(order, rows).keys()) == ["L1"]
