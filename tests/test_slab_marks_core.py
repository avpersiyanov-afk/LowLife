# -*- coding: utf-8 -*-
from lowlife import slab_marks_core as core


def test_probe_slab_and_floor():
    # точка на 1500 над уровнем 0: перекрытие в 1800 выше, пол 50 ниже уровня точки отсчёта
    up = [(1800.0, core.SLAB), (2000.0, core.SLAB), (5000.0, core.SLAB)]
    down = [(1550.0, core.SLAB)]
    found = core.probe(1500.0, up, down, 0.0)
    assert found.slab_z_mm == 3300.0
    assert found.floor_z_mm == -50.0
    assert found.slab_mm == 3350.0
    assert found.ceiling_mm is None


def test_probe_ceiling_below_slab():
    up = [(1200.0, core.CEILING), (1800.0, core.SLAB), (1210.0, core.CEILING)]
    found = core.probe(1500.0, up, [], 0.0)
    assert found.floor_z_mm == 0.0           # пола нет — уровень
    assert found.ceiling_mm == 2700.0
    assert found.slab_mm == 3300.0


def test_probe_ceiling_above_slab_ignored_and_no_slab():
    found = core.probe(1500.0, [(1800.0, core.SLAB), (2500.0, core.CEILING)], [], 0.0)
    assert found.ceiling_mm is None
    assert core.probe(1500.0, [(1000.0, core.CEILING), (500.0, None)], [], 0.0) is None


def test_format_height():
    assert core.format_height(3300) == u"+3,300"
    assert core.format_height(-450) == u"-0,450"
    assert core.format_height(0) == u"±0,000"
    assert core.format_height(3300, signed=False) == u"3,300"


def test_heights_rounding_and_range():
    assert core.height_range_text([3301.0, 3299.0], 10) == u"+3,300"
    assert core.height_range_text([3300.0, 3750.0, None], 10) == u"+3,300…+3,750"
    assert core.height_range_text([None], 10) == u""


def test_main_and_typical_height():
    assert core.main_height([3300, 3300, 3750], 10) == 3300
    assert core.main_height([3750, 3300], 10) == 3300   # при равенстве — меньшая
    assert core.main_height([None], 10) is None
    assert core.typical_height([3300, 3300, 3600, None], 10) == 3300


def test_room_label():
    text = core.room_label([3750.0], [2700.0], 3300.0, 10,
                           u"Пер. {h}", u"ПП {h}", u"Δ {d}")
    assert text == u"Пер. +3,750\nΔ +0,450\nПП +2,700"
    same = core.room_label([3300.0], [None], 3300.0, 10, u"Пер. {h}", u"ПП {h}", u"Δ {d}")
    assert same == u"Пер. +3,300"
    lower = core.room_label([3000.0], [], 3300.0, 10, u"{h}", u"ПП {h}", u"Δ {d}")
    assert lower == u"+3,000\nΔ -0,300"


def test_room_label_bad_template_falls_back():
    assert core.room_label([3300.0], [], None, 10, u"Пер. {x}", u"", u"") == u"Пер. {x} +3,300"


def test_is_detector():
    include = core.split_words(u"дым, тепл; ИП 212")
    exclude = core.split_words(u"ручн, ИПР")
    assert core.is_detector([u"Извещатель пожарный дымовой", u"ИП 212-64"], include, exclude)
    assert not core.is_detector([u"Извещатель пожарный ручной", u"ИПР 513"], include, exclude)
    assert not core.is_detector([u"Оповещатель", u"Табло"], include, exclude)
    assert core.is_detector([u"Что угодно"], [], exclude)
    assert core.is_detector([u"Извещатель тепловой (Ё)"], core.split_words(u"тЕпл"), [])


def test_move_delta_and_grid():
    assert core.move_delta(2500.0, 3300.0, 0) == 800.0
    assert core.move_delta(3400.0, 3300.0, 50) == -150.0
    assert core.grid_steps(2000) == 1
    assert core.grid_steps(7000) == 3
    assert core.grid_steps(50000) == 3
