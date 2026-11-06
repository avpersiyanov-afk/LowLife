# -*- coding: utf-8 -*-
import copy
import math

import pytest

from lowlife import fire_boxes_core as core, fire_boxes_settings as cfg


@pytest.mark.parametrize('product,rating,extra', [
    ('FIREBOX', 90, (100, 100)), ('FIREBOX', 150, (150, 150)),
    ('FIREBOX', 180, (180, 180)), ('FIREBOX', 240, (240, 240)),
    ('OSK', 90, (260, 290)), ('OSK', 180, (280, 290)), ('OSK', 240, (310, 270)),
])
def test_manufacturer_calculator_reference_cases(product, rating, extra):
    values = cfg.defaults()
    values.update(product=product, rating=rating, trays=[dict(width_mm=600, height_mm=200)])
    section = core.layout(values)
    assert (section['width'], section['height']) == (600 + extra[0], 200 + extra[1])


def test_osks_150_minutes_cannot_use_firebox_rule():
    with pytest.raises(ValueError):
        core.allowances('OSK', 150)
    with pytest.raises(ValueError):
        core.allowances('other', 90)


def test_vertical_mixed_sizes_clear_gaps_and_centers():
    values = cfg.defaults()
    values.update(clearance_mm=20, gap_mm=80,
                  trays=[dict(width_mm=300, height_mm=100), dict(width_mm=200, height_mm=50)])
    section = core.layout(values)
    first, second = section['trays']
    assert (section['inner_width'], section['inner_height']) == (340, 270)
    assert first['z'] == -65
    assert second['z'] == 90
    assert second['z'] - second['height']/2 - (first['z'] + first['height']/2) == 80
    assert first['x'] == second['x'] == 0


def test_horizontal_sizes_bottom_aligned_not_centered():
    values = cfg.defaults()
    values.update(arrangement='horizontal', gap_mm=50,
                  trays=[dict(width_mm=300, height_mm=100), dict(width_mm=200, height_mm=50)])
    section = core.layout(values)
    a, b = section['trays']
    assert (section['inner_width'], section['inner_height']) == (550, 100)
    assert a['z'] - a['height']/2 == b['z'] - b['height']/2
    assert b['x'] - b['width']/2 - (a['x'] + a['width']/2) == 50
    assert core.fits(section['width'], section['height'], values)
    assert not core.fits(section['width'] - 1, section['height'], values)


@pytest.mark.parametrize('bad', ['nan', 'inf', '-inf', -1, 0, 'bad'])
def test_invalid_tray_size_is_rejected(bad):
    values = cfg.defaults()
    values['trays'][0]['width_mm'] = bad
    with pytest.raises(ValueError):
        core.layout(values)


def test_decimal_comma_and_no_mutation():
    values = cfg.defaults()
    values['trays'][0]['width_mm'] = '300,5'
    before = copy.deepcopy(values)
    assert core.layout(values)['inner_width'] == 300.5
    assert values == before


def test_note_preserves_user_text_and_replaces_only_own_record():
    values = cfg.defaults()
    values['trays'] *= 2
    text = core.merge_note(u'Project note', core.description(values))
    assert u'2 шт. 300×100 мм' in text
    values['rating'] = 90
    text = core.merge_note(text, core.description(values))
    assert text.startswith('Project note\n')
    assert text.count('[LowLife OKK]') == 1
    assert 'EI 180' not in text
    assert 'EI 90' in text


def test_3d_corner_shifted_routes_meet_and_skew_routes_fail():
    assert core.line_intersection((1, 0, 3), (0, 1, 0), (0, 2, 3), (1, 0, 0)) == (1, 2, 3)
    with pytest.raises(ValueError):
        core.line_intersection((1, 0, 3), (0, 1, 0), (0, 2, 5), (1, 0, 0), tolerance=0.1)


@pytest.mark.parametrize('end', [(10,0,0), (0,10,0), (0,0,10), (-5,2,10)])
def test_cross_section_axes_are_orthonormal(end):
    right, up = core.frame((0,0,0), end)
    tangent = core.unit(end)
    assert abs(core.dot(right, up)) < 1e-8
    assert abs(core.dot(right, tangent)) < 1e-8
    assert abs(core.dot(up, tangent)) < 1e-8
    assert core.dot(right, right) == pytest.approx(1)
    assert core.dot(up, up) == pytest.approx(1)


def test_settings_roundtrip_and_no_project_parameter_names(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    values = cfg.defaults()
    assert values['inside_flag_param'] == values['enclosure_note_param'] == ''
    values['box_type_uid'] = 'example-type-uid'
    cfg.save(values)
    assert cfg.load() == values


def test_rolled_enclosure_cannot_hide_out_of_bounds_tray():
    row = dict(x=0,z=0,width=300,height=100)
    assert core.section_fits_axes(row, (1,0,0),(0,1,0),(1,0,0),(0,1,0),300,200)
    assert not core.section_fits_axes(row, (1,0,0),(0,1,0),(0,1,0),(1,0,0),300,200)
