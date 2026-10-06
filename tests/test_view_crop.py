# -*- coding: utf-8 -*-
import pytest

from lowlife.view_crop import crop_rect


def test_corners_in_any_order():
    assert crop_rect((10, 2), (1, 8)) == (1.0, 2.0, 10.0, 8.0)
    assert crop_rect((1, 8), (10, 2)) == (1.0, 2.0, 10.0, 8.0)


def test_degenerate_rect_rejected():
    with pytest.raises(ValueError):
        crop_rect((0, 0), (5, 0.001))
    with pytest.raises(ValueError):
        crop_rect((3, 3), (3, 3))


def test_min_size_override():
    assert crop_rect((0, 0), (0.5, 0.5), min_size=0.1) == (0.0, 0.0, 0.5, 0.5)
