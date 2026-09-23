# -*- coding: utf-8 -*-
"""Тесты для lowlife.skud_door_layout — места мнемосхемы двери, пересчёт
места в точку и состав типа точки доступа по местам, количество у замка/геркона (кнопка «Точки
доступа на двери», SKUD.panel/PlaceDoorAccessPoints)."""

import pytest

from lowlife import skud_door_layout as layout


def _slot(anchor, offset, height, depth=0, families=None):
    return {"anchor": anchor, "offset_mm": offset, "height_mm": height,
            "depth_mm": depth, "families": families or []}


# --- slot_local_position -----------------------------------------------------

def test_local_position_left_right_top():
    assert layout.slot_local_position(_slot("right", 150, 1000), 900, 2100) == (600, 1000, 0)
    assert layout.slot_local_position(_slot("left", 150, 1000), 900, 2100) == (-600, 1000, 0)
    assert layout.slot_local_position(_slot("top", -300, 50, 20), 900, 2100) == (-300, 2150, 20)


def test_local_position_parses_text_with_comma():
    assert layout.slot_local_position(_slot("right", u"100,5", u"", u"x"), 1000, 2000) == (600.5, 0.0, 0.0)


# --- viewer_right / world_point ----------------------------------------------

def test_viewer_right_is_right_hand_of_viewer():
    # Наблюдатель на юге (normal смотрит на юг), глядит на север — право = восток.
    assert layout.viewer_right((0.0, -1.0, 0.0)) == pytest.approx((1.0, 0.0, 0.0))
    # С другой стороны двери право — наоборот.
    assert layout.viewer_right((0.0, 1.0, 0.0)) == pytest.approx((-1.0, 0.0, 0.0))


def test_world_point_combines_right_normal_face_and_height():
    point = layout.world_point((10.0, 20.0, 3.0), (0.0, -1.0, 0.0), 0.5, (600.0, 1000.0, 20.0), 0.001)
    assert point == pytest.approx((10.6, 20.0 - 0.52, 4.0))


# --- default slots / active slots ---------------------------------------------

def test_all_slot_keys_outer_first_and_unique():
    keys = layout.all_slot_keys()
    assert len(keys) == len(set(keys)) == len(layout.SIDES) * len(layout.ROLES)
    assert keys[0].startswith("outer_")
    assert keys[-1].startswith("inner_")
    assert layout.split_slot_key(u"inner_reader") == (u"inner", u"reader")


def test_active_slots_skips_empty_and_keeps_order():
    slots = {key: _slot("right", 0, 0) for key in layout.all_slot_keys()}
    slots["inner_lock"]["families"] = [u"Замок"]
    slots["outer_reader"]["families"] = [u"Считыватель"]
    assert [key for key, _s in layout.active_slots(slots)] == ["outer_reader", "inner_lock"]


# --- slot_count / slot_local_positions ---------------------------------------

def test_count_only_for_lock_and_reed_and_clamped():
    assert layout.slot_count("inner_lock", {"count": u"2"}) == 2
    assert layout.slot_count("outer_reed", {"count": u"5"}) == layout.MAX_COUNT
    assert layout.slot_count("inner_lock", {"count": u""}) == 1
    assert layout.slot_count("outer_reader", {"count": u"2"}) == 1


def test_second_lock_is_mirrored_about_door_axis():
    slot = _slot("top", 300, 0, 10)
    slot["count"] = u"2"
    assert layout.slot_local_positions("inner_lock", slot, 1800, 2100) == [(300, 2100, 10), (-300, 2100, 10)]
    slot["count"] = u"1"
    assert layout.slot_local_positions("inner_lock", slot, 1800, 2100) == [(300, 2100, 10)]


# --- composition_items ----------------------------------------------------------

def _slots(**families_by_key):
    slots = {key: _slot("right", 0, 0) for key in layout.all_slot_keys()}
    for key, families in families_by_key.items():
        slots[key]["families"] = families
    return slots


def test_composition_items_in_mnemonic_order_and_stale_detected():
    slots = _slots(outer_reader=[u"Считыватель"], inner_lock=[u"Замок ЭМ"])
    access_type = {"name": u"ТД-1", "composition": {
        "inner_lock": {"family": u"замок эм", "type": u"ML-300"},
        "outer_reader": {"family": u"Считыватель", "type": u"EM"},
        "inner_exit": {"family": u"Кнопка", "type": u"К1"},
        "outer_closer": {"family": u"", "type": u""},
    }}
    items, stale = layout.composition_items(access_type, slots)
    assert [(k, f, t) for k, _s, f, t in items] == [
        ("outer_reader", u"Считыватель", u"EM"), ("inner_lock", u"замок эм", u"ML-300")]
    assert stale == [("inner_exit", u"Кнопка", u"К1")]


def test_composition_items_empty_type():
    assert layout.composition_items(None, _slots()) == ([], [])
    assert layout.composition_items({"name": u"x"}, _slots()) == ([], [])


def test_find_access_type():
    types = [{"name": u"A", "composition": {}}, {"name": u"B", "composition": {}}]
    assert layout.find_access_type(types, u"B") is types[1]
    assert layout.find_access_type(types, u"C") is None
