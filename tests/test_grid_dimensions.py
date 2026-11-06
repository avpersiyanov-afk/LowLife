# -*- coding: utf-8 -*-
import math

import pytest

from lowlife import grid_dimensions as gd
from lowlife import grid_dimensions_settings as settings


@pytest.mark.parametrize("name, mask, expected", [
    (u"А/10", u"а/*", True), (u"10", u"[0-9]*;[А-Я]", True),
    (u"Б", u"[0-9]*;[А-Я]", True), (u"Б/1", u"[0-9]*;[А-Я]", False),
    (u"А/1", u"А/?", True), (u"А/10", u"А/?", False),
    (u"Ось1", u"1", False), (u"1", u"  1 ; 2  ", True),
    (u"A", u"*", True), (u"A", u"; ;", False),
])
def test_mask(name, mask, expected):
    assert gd.matches_mask(name, mask) is expected


def vertical(name, x, reverse=False):
    points = [(x, 0), (x, 20)]
    if reverse:
        points.reverse()
    return gd.GridLine(None, name, *points)


def test_extremes_use_markings_while_chain_uses_geometry():
    group, = gd.group_lines([vertical(u"10", 5), vertical(u"2", 10, True),
                             vertical(u"3", 0)])
    assert [l.name for l in group.extremes()] == [u"2", u"10"]
    assert [l.name for l in group.chain()] == [u"3", u"10", u"2"]
    assert group.dimension_points(group.chain(), 2) == ((0, -2), (10, -2))
    assert group.dimension_points(group.extremes(), 3) == ((5, -3), (10, -3))


def test_letter_and_fractional_markings():
    names = [u"Б", u"А/10", u"А/2", u"А", u"10", u"2"]
    assert sorted(names, key=gd.marking_key) == [u"2", u"10", u"А", u"А/2", u"А/10", u"Б"]


def test_parallel_groups_separate_directions_and_ignore_single_and_zero():
    lines = [vertical(u"1", 0), vertical(u"2", 5, True),
             gd.GridLine(None, u"А", (0, 0), (20, 0)),
             gd.GridLine(None, u"Б", (20, 5), (0, 5)),
             gd.GridLine(None, u"К", (0, 0), (20, 10)),
             gd.GridLine(None, u"0", (0, 0), (0, 0))]
    groups = gd.group_lines(lines)
    assert [len(g.lines) for g in groups] == [2, 2]
    assert groups[1].dimension_points(groups[1].chain(), 2) == ((-2, 0), (-2, 5))


def test_rotated_plan_dimension_stays_perpendicular_to_grids():
    angle = 0.4
    def rotate(p):
        x, y = p
        return (x * math.cos(angle) - y * math.sin(angle),
                x * math.sin(angle) + y * math.cos(angle))
    lines = [vertical(u"1", 0), vertical(u"2", 5, True)]
    for line in lines:
        line.start, line.end = rotate(line.start), rotate(line.end)
    group, = gd.group_lines(lines)
    start, end = group.dimension_points(group.chain(), 2)
    assert start == pytest.approx(rotate((0, -2)))
    assert end == pytest.approx(rotate((5, -2)))
    assert sum((b - a) * d for a, b, d in zip(start, end, group.direction)) == pytest.approx(0)


def test_coincident_axes_do_not_make_zero_length_dimension():
    group, = gd.group_lines([vertical(u"1", 0), vertical(u"2", 0)])
    assert group.dimension_points(group.chain(), 2) is None


def test_settings_defaults_and_validation(monkeypatch):
    monkeypatch.setattr(settings.SETTINGS.store, "read", lambda: {})
    assert settings.get_settings_silent() == {
        "grid_name_mask": u"*", "offset_mm": 1400.0, "total_gap_mm": 700.0}
    values, errors = settings.SETTINGS.parse_form({
        "grid_name_mask": u"А/*", "offset_mm": "1200,5", "total_gap_mm": "500"})
    assert not errors
    assert values["offset_mm"] == 1200.5
    _, errors = settings.SETTINGS.parse_form({
        "grid_name_mask": "", "offset_mm": "-1", "total_gap_mm": "0"})
    assert len(errors) == 2
    assert settings.SETTINGS.missing({"grid_name_mask": ""}, ["grid_name_mask"])
