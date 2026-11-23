# -*- coding: utf-8 -*-

import math

import pytest

from lowlife.tray_connection_core import plan_points, slope_angle_deg, parse_angle


def test_plan_points_uses_one_segment_when_horizontal_run_matches_angle():
    points = plan_points((0, 0, 0), (1000, 0, 1000), 45)
    assert points == ((0.0, 0.0, 0.0), (1000.0, 0.0, 1000.0))


def test_plan_points_adds_horizontal_tail_for_steeper_requested_slope():
    points = plan_points((0, 0, 0), (2000, 0, 1000), 45)
    assert len(points) == 3
    assert points[1] == pytest.approx((1000, 0, 1000))
    assert slope_angle_deg(points[0], points[1]) == pytest.approx(45)
    assert points[1][2] == points[2][2]


def test_plan_points_rejects_impossible_angle_and_same_level():
    with pytest.raises(ValueError):
        plan_points((0, 0, 0), (1000, 0, 1000), 30)
    with pytest.raises(ValueError):
        plan_points((0, 0, 0), (1000, 0, 0), 45)


def test_plan_points_can_route_vertically_aligned_ends_using_a_tray_direction():
    points = plan_points((0, 0, 0), (0, 0, 1000), 45, direction=(0, 1))
    assert points[1] == pytest.approx((0, 1000, 1000))
    assert points[2] == pytest.approx((0, 0, 1000))


def test_slope_angle_handles_vertical_segment():
    assert slope_angle_deg((1, 2, 0), (1, 2, 1)) == 90.0
    assert slope_angle_deg((0, 0, 0), (1, 0, 0)) == 0.0


def test_parse_angle_accepts_comma_decimal():
    assert parse_angle("22,5") == pytest.approx(22.5)
    with pytest.raises(ValueError):
        parse_angle("1")
