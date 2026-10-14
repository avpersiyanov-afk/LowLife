# -*- coding: utf-8 -*-
import math

import pytest

from lowlife.view_rotate import (
    AXES, AXIS_GRID, DEFAULT_AXIS, parse_angle, rotate_orientation,
    rotate_point, rotate_vector,
)


def _close(a, b, tol=1e-9):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def test_parse_angle():
    assert parse_angle(u"90") == 90.0
    assert parse_angle(u" -45 ") == -45.0
    assert parse_angle(u"12,5°") == 12.5
    assert parse_angle(u"450") == 90.0
    assert parse_angle(u"-370") == -10.0


@pytest.mark.parametrize("text", [u"", u"abc", u"0", u"360", u"-720", u"nan"])
def test_parse_angle_rejects(text):
    with pytest.raises(ValueError):
        parse_angle(text)


def test_rotate_vector_right_hand():
    assert _close(rotate_vector((1, 0, 0), (0, 0, 1), math.pi / 2), (0, 1, 0))
    assert _close(rotate_vector((0, 1, 0), (1, 0, 0), math.pi / 2), (0, 0, 1))
    # Длина оси не важна.
    assert _close(rotate_vector((1, 0, 0), (0, 0, 5), math.pi), (-1, 0, 0))


def test_rotate_point_about_offset_line():
    assert _close(rotate_point((2, 1, 7), (1, 1, 0), (0, 0, 1), math.pi / 2), (1, 2, 7))


def test_orientation_rotates_camera_opposite_to_model():
    # Вид сверху: модель против часовой на 90° -> камера по часовой.
    eye, up, fwd = rotate_orientation((0, 0, 10), (0, 1, 0), (0, 0, -1),
                                      (0, 0, 0), (0, 0, 1), 90)
    assert _close(eye, (0, 0, 10))
    assert _close(up, (1, 0, 0))
    assert _close(fwd, (0, 0, -1))


def test_orientation_stays_orthonormal():
    up0 = (-0.408248290463863, -0.408248290463863, 0.816496580927726)
    fwd0 = (0.577350269189626, 0.577350269189626, 0.577350269189626)
    eye, up, fwd = rotate_orientation((-5, -5, -5), up0, fwd0, (1, 2, 3), (1, 1, 0), 37.5)
    dot = sum(u * f for u, f in zip(up, fwd))
    assert abs(dot) < 1e-9
    assert abs(sum(u * u for u in up) - 1) < 1e-9
    assert abs(sum(f * f for f in fwd) - 1) < 1e-9
    # Расстояние глаза до оси сохраняется: поворот обратим.
    back = rotate_orientation(eye, up, fwd, (1, 2, 3), (1, 1, 0), -37.5)
    assert _close(back[0], (-5, -5, -5))
    assert _close(back[1], up0)


def test_axes():
    keys = [a[0] for a in AXES]
    assert DEFAULT_AXIS in keys and AXIS_GRID in keys
