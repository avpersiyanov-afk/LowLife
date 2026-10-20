# -*- coding: utf-8 -*-
"""Тесты для lowlife.tray_hatch_core — где лоток проходит через уровень и
какого размера там лючок; и для настроек кнопки «Лючки на уровнях»."""

import math

import pytest

from lowlife import tray_hatch_core as core
from lowlife import tray_hatch_settings as ths


def test_vertical_tray_crosses_levels_strictly_between_ends():
    found = core.crossings((1.0, 2.0, -5.0), (1.0, 2.0, 25.0), [0.0, 10.0, 30.0], 0.01)
    assert found == [(0, (1.0, 2.0, 0.0)), (1, (1.0, 2.0, 10.0))]


def test_end_on_level_counts_only_when_connected():
    p0, p1 = (0.0, 0.0, 0.0), (0.0, 0.0, 10.0)
    assert core.crossings(p0, p1, [0.0, 10.0], 0.01) == []
    assert core.crossings(p0, p1, [0.0, 10.0], 0.01, connected=(True, False)) == \
        [(0, (0.0, 0.0, 0.0))]
    assert core.crossings(p0, p1, [0.0, 10.0], 0.01, connected=(False, True)) == \
        [(1, (0.0, 0.0, 10.0))]


def test_flat_and_gentle_trays_are_ignored():
    assert core.crossings((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), [0.0], 0.01) == []
    # 20° к горизонту — положе порога
    dz = 10.0 * math.tan(math.radians(20.0))
    assert core.crossings((0.0, 0.0, -dz / 2), (10.0, 0.0, dz / 2), [0.0], 0.01) == []


def test_sloped_tray_crossing_point_is_interpolated():
    found = core.crossings((0.0, 0.0, 0.0), (4.0, 0.0, 8.0), [2.0], 0.01)
    assert found == [(0, (1.0, 0.0, 2.0))]


def test_footprint_of_vertical_tray_is_width_by_height():
    angle, along_width, across = core.footprint(
        (0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0), 0.3, 0.1)
    assert angle == pytest.approx(math.pi / 2)
    assert along_width == pytest.approx(0.3)
    assert across == pytest.approx(0.1)


def test_footprint_of_sloped_tray_stretches_height_along_slope():
    # 60° к горизонту в плоскости XZ, ширина по Y
    a = math.radians(60.0)
    axis = (math.cos(a), 0.0, math.sin(a))
    height_dir = (-math.sin(a), 0.0, math.cos(a))
    angle, along_width, across = core.footprint(axis, (0.0, 1.0, 0.0), height_dir, 0.3, 0.1)
    assert along_width == pytest.approx(0.3)
    assert across == pytest.approx(0.1 / math.sin(a))


def test_footprint_of_horizontal_tray_is_none():
    assert core.footprint((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), 0.3, 0.1) is None


def test_dedupe_keeps_first_per_level_and_point():
    items = [(0, (0.0, 0.0, 0.0), "a"), (0, (0.05, 0.0, 0.0), "b"),
             (1, (0.0, 0.0, 3.0), "c"), (0, (1.0, 0.0, 0.0), "d")]
    assert [i[2] for i in core.dedupe(items, 0.1)] == ["a", "c", "d"]


def test_rotation_delta_ignores_half_turns():
    assert core.rotation_delta(0.0, math.pi) == pytest.approx(0.0)
    assert core.rotation_delta(0.0, math.pi / 2) == pytest.approx(math.pi / 2)
    assert core.rotation_delta(0.1, math.pi - 0.1) == pytest.approx(-0.2)


def test_size_label():
    assert core.size_label(350.0004, 149.6) == u"350×150"


@pytest.fixture
def appdata(tmpdir, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmpdir))
    return str(tmpdir)


def test_settings_defaults(appdata):
    values = ths.get_settings_silent()
    assert values["hatch_type_filter"] == u"лючок"
    assert values["hatch_margin_mm"] == 50.0
    assert values["hatch_offset_mm"] == 0.0
    assert values["hatch_width_param"] == u""
