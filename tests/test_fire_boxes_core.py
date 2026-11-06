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
    assert first['z'] == -90
    assert second['z'] == 65
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


@pytest.mark.parametrize('tangent', [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0)])
@pytest.mark.parametrize('sign', [-1, 1])
def test_horizontal_tray_connector_sign_never_causes_a_half_turn(tangent, sign):
    assert core.section_roll_angle(tangent, (0,0,sign), (0,0,1)) == pytest.approx(0)


def test_vertical_tray_still_aligns_a_genuinely_rotated_section():
    assert abs(core.section_roll_angle((0,0,1), (1,0,0), (0,1,0))) == pytest.approx(math.pi/2)
    assert abs(core.section_roll_angle((0,0,1), (-1,0,0), (0,1,0))) == pytest.approx(math.pi/2)


def test_section_roll_uses_the_small_angle_near_a_half_turn():
    angle = core.section_roll_angle((1,0,0), (0,math.sin(0.001),-math.cos(0.001)), (0,0,1))
    assert abs(angle) == pytest.approx(0.001)


def test_single_type_settings_migrate_to_rows_without_overwriting_types():
    old = dict(tray_type_uid='legacy', trays=[dict(width_mm=300,height_mm=100),
               dict(width_mm=200,height_mm=50,tray_type_uid='explicit')])
    migrated = cfg.normalize(old)
    assert [r['tray_type_uid'] for r in migrated['trays']] == ['legacy','explicit']
    assert 'tray_type_uid' not in old['trays'][0]


def test_mixed_type_ids_survive_layout_and_storage(tmp_path,monkeypatch):
    monkeypatch.setenv('APPDATA',str(tmp_path))
    values = cfg.defaults()
    values['box_type_uid'] = 'box'
    values['trays'] = [dict(width_mm=300,height_mm=100,tray_type_uid='perforated'),
                       dict(width_mm=200,height_mm=50,tray_type_uid='ladder')]
    cfg.save(values)
    loaded = cfg.load()
    assert [r['tray_type_uid'] for r in core.layout(loaded)['trays']] == ['perforated','ladder']


@pytest.mark.parametrize('rating,wall,bottom,top',[(90,25,80,160),(180,70,50,100)])
def test_physical_panels_and_mounting_clearances(rating,wall,bottom,top):
    values = cfg.defaults()
    values['rating'] = rating
    section = core.mounting_section(values)
    assert section['wall'] == wall
    assert section['cavity_width'] == section['width']-2*wall
    assert section['cavity_height'] == section['height']-2*wall
    assert section['bottom_clear'] == bottom
    assert section['top_clear'] == top
    assert section['trays'][0]['z']-section['trays'][0]['height']/2 == -section['height']/2+wall+bottom
    assert len(section['rods']) == 2


def test_legacy_box_metadata_keeps_original_centered_offsets():
    values = cfg.defaults()
    values.pop('support_bottom_mm')
    values['trays'] = [dict(width_mm=300,height_mm=100),dict(width_mm=200,height_mm=50)]
    assert [r['z'] for r in core.layout(values)['trays']] == [-75,100]


def test_additional_rod_goes_in_free_gap_instead_of_through_tray():
    values = cfg.defaults()
    values['arrangement'] = 'horizontal'
    values['trays'] = [dict(width_mm=800,height_mm=100)]*2
    section = core.mounting_section(values)
    assert section['middle_rod_required']
    assert not section['middle_rod_missing']
    assert section['rods'][1] == 0


def test_wide_single_tray_needs_designed_extra_suspension():
    values = cfg.defaults()
    values['trays'][0]['width_mm'] = 1500
    section = core.mounting_section(values)
    assert section['middle_rod_missing']
    assert len(section['rods']) == 2


def test_crossbar_cannot_overlap_lower_tray():
    values = cfg.defaults()
    values['trays'] *= 2
    values['gap_mm'] = 10
    with pytest.raises(ValueError):
        core.mounting_section(values)


def test_rod_collision_and_excessive_bottom_offset_are_rejected():
    values = cfg.defaults()
    values['rod_inset_mm'] = 100
    with pytest.raises(ValueError):
        core.mounting_section(values)
    values = cfg.defaults()
    values['support_bottom_mm'] = 300
    with pytest.raises(ValueError):
        core.layout(values)


def test_no_osk240_mounting_details_are_invented():
    values = cfg.defaults()
    values['rating'] = 240
    section = core.mounting_section(values)
    assert section['wall'] is None
    assert not section['mounting_supported']
    assert section['rods'] == section['crossbars'] == []
