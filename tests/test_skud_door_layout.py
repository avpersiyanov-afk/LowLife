# -*- coding: utf-8 -*-
"""Тесты для lowlife.skud_door_layout — места мнемосхемы двери, пересчёт
места в точку и раскладка состава группы по местам (кнопка «Точки
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


# --- match_members_to_slots ----------------------------------------------------

def _active(**families_by_key):
    slots = {key: _slot("right", 0, 0) for key in layout.all_slot_keys()}
    for key, families in families_by_key.items():
        slots[key]["families"] = families
    return layout.active_slots(slots)


def test_two_readers_go_outside_then_inside():
    slots = _active(outer_reader=[u"Считыватель"], inner_reader=[u"Считыватель"])
    assigned, unmatched = layout.match_members_to_slots(
        [(u"Считыватель", 1), (u"Считыватель", 2)], slots)
    assert [(key, payload) for key, _s, payload in assigned] == [("outer_reader", 1), ("inner_reader", 2)]
    assert unmatched == []


def test_single_reader_only_outside_and_extra_is_unmatched():
    slots = _active(outer_reader=[u"Считыватель"], inner_lock=[u"Замок ЭМ"])
    assigned, unmatched = layout.match_members_to_slots(
        [(u"считыватель ", 1), (u"Замок ЭМ", 2), (u"Замок ЭМ", 3), (u"Геркон", 4)], slots)
    assert [(key, payload) for key, _s, payload in assigned] == [("outer_reader", 1), ("inner_lock", 2)]
    assert unmatched == [(u"Замок ЭМ", 3), (u"Геркон", 4)]


def test_family_allowed_in_several_places_takes_first_free():
    slots = _active(outer_intercom=[u"Панель"], inner_exit=[u"Кнопка", u"Панель"])
    assigned, _unmatched = layout.match_members_to_slots([(u"Панель", 1), (u"Панель", 2)], slots)
    assert [key for key, _s, _p in assigned] == ["outer_intercom", "inner_exit"]
