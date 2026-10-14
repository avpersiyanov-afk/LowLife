# -*- coding: utf-8 -*-
import math

import pytest

from lowlife.view_rotate import (
    align_angle, camera_plan_direction, plan_angle, rotate_camera,
    rotate_point, rotate_vector,
)


def _close(a, b, tol=1e-9):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def test_plan_angle():
    assert plan_angle((0, 1, 0)) == pytest.approx(math.pi / 2)
    assert plan_angle((0, 0, -1)) is None


@pytest.mark.parametrize("axis_deg, expected_deg", [
    (0, 0), (10, 10), (-10, -10), (80, -10), (100, 10),
    (180, 0), (270, 0), (30, 30), (60, -30), (45, 45), (-45, 45),
])
def test_align_angle_picks_nearest_quarter(axis_deg, expected_deg):
    a = math.radians(axis_deg)
    got = align_angle((1, 0, 0), (math.cos(a), math.sin(a), 0))
    assert math.degrees(got) == pytest.approx(expected_deg)


def test_align_angle_result_is_aligned():
    current = (0.3, -0.8, -0.5)
    axis = (math.cos(1.1), math.sin(1.1), 0.2)
    rot = rotate_vector(current, (0, 0, 1), align_angle(current, axis))
    cross_z = rot[0] * axis[1] - rot[1] * axis[0]
    dot = rot[0] * axis[0] + rot[1] * axis[1]
    assert abs(cross_z) < 1e-9 or abs(dot) < 1e-9


def test_align_angle_rejects_vertical():
    with pytest.raises(ValueError):
        align_angle((1, 0, 0), (0, 0, 1))


def test_rotate_vector_right_hand():
    assert _close(rotate_vector((1, 0, 0), (0, 0, 1), math.pi / 2), (0, 1, 0))
    assert _close(rotate_vector((1, 0, 0), (0, 0, 5), math.pi), (-1, 0, 0))


def test_rotate_point_about_offset_line():
    assert _close(rotate_point((2, 1, 7), (1, 1, 0), (0, 0, 1), math.pi / 2), (1, 2, 7))


def test_camera_plan_direction_top_view_uses_up():
    assert camera_plan_direction((0, 1, 0), (0, 0, -1)) == (0, 1, 0)
    assert camera_plan_direction((0, 0, 1), (1, 0, 0)) == (1, 0, 0)


def test_rotate_camera_keeps_pitch_and_orthogonality():
    up0 = (-0.408248290463863, -0.408248290463863, 0.816496580927726)
    fwd0 = (0.577350269189626, 0.577350269189626, 0.577350269189626)
    eye, up, fwd = rotate_camera((-5, -5, 5), up0, fwd0, (1, 2, 3), 0.7)
    assert fwd[2] == pytest.approx(fwd0[2])
    assert up[2] == pytest.approx(up0[2])
    assert eye[2] == pytest.approx(5)
    assert abs(sum(u * f for u, f in zip(up, fwd))) < 1e-9
