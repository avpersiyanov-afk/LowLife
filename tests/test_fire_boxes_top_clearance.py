# -*- coding: utf-8 -*-
import copy

import pytest
from lowlife import fire_boxes_core as core, fire_boxes_settings as cfg


@pytest.mark.parametrize('rating,wall,bottom', [(90,25,80), (180,70,50)])
@pytest.mark.parametrize('configuration', core.WALL_CONFIGURATIONS)
@pytest.mark.parametrize('arrangement,group_height', [('vertical',250), ('horizontal',100)])
@pytest.mark.parametrize('top', [0,50,150])
def test_top_gap_drives_height_and_preserves_bottom(rating,wall,bottom,configuration,arrangement,group_height,top):
    settings = cfg.defaults()
    settings.update(rating=rating,wall_configuration=configuration,arrangement=arrangement,
                    top_clearance_mm=top,
                    trays=[dict(width_mm=300,height_mm=100),dict(width_mm=200,height_mm=50)])
    before = copy.deepcopy(settings)
    section = core.mounting_section(settings)
    panels = wall if configuration == 'no_top' else 2*wall
    assert section['height'] == group_height+bottom+top+panels
    assert section['top_clear'] == top
    assert section['bottom_clear'] == bottom
    assert section['cavity_z']+section['cavity_height']/2-section['tray_top'] == top
    assert section['tray_bottom']-(section['cavity_z']-section['cavity_height']/2) == bottom
    assert section['custom_top_clearance']
    assert core.fits(section['width'],section['height'],settings)
    assert not core.fits(section['width'],section['height']-1,settings)
    assert settings == before


def test_changing_top_gap_keeps_width_and_bottom_mounting_independent():
    settings = cfg.defaults()
    settings.update(rod_inset_mm=15,rod_to_tray_mm=20,top_clearance_mm=150,support_bottom_mm=300)
    first = core.mounting_section(settings)
    settings['top_clearance_mm'] = 20
    second = core.mounting_section(settings)
    assert first['height']-second['height'] == 130
    assert first['width'] == second['width'] == 510
    assert first['bottom_clear'] == second['bottom_clear'] == 300
    assert first['rods'] == second['rods']


def test_empty_auto_migration_keeps_previous_height_and_centre_offsets():
    settings = cfg.defaults()
    settings.pop('top_clearance_mm')
    before = core.layout(settings)
    migrated = cfg.normalize(settings)
    assert migrated['top_clearance_mm'] is None
    assert core.layout(migrated) == before
    migrated['top_clearance_mm'] = 0
    assert core.layout(migrated)['height'] < before['height']
    migrated['top_clearance_mm'] = None
    assert core.layout(migrated) == before


def test_explicit_top_preserves_legacy_bottom_without_support_setting():
    settings = cfg.defaults()
    settings.pop('support_bottom_mm')
    bottom = core.layout(settings)['bottom_clear']
    settings['top_clearance_mm'] = 20
    section = core.layout(settings)
    assert section['bottom_clear'] == bottom
    assert section['top_clear'] == 20


@pytest.mark.parametrize('value', [-1,'nan','inf','bad'])
def test_invalid_top_gap_is_rejected(value):
    settings = cfg.defaults()
    settings['top_clearance_mm'] = value
    with pytest.raises(ValueError):
        core.layout(settings)


def test_top_cannot_discard_minimum_extra_clearance():
    settings = cfg.defaults()
    settings.update(top_clearance_mm=10,clearance_mm=20)
    with pytest.raises(ValueError):
        core.layout(settings)
    settings['top_clearance_mm'] = 20
    assert core.layout(settings)['top_clear'] == 20


def test_top_setting_roundtrip_with_zero(tmp_path,monkeypatch):
    monkeypatch.setenv('APPDATA',str(tmp_path))
    settings = cfg.defaults()
    settings.update(box_type_uid='example',top_clearance_mm=0)
    cfg.save(settings)
    assert cfg.load() == settings


@pytest.mark.parametrize('product,rating', [('FIREBOX',180), ('OSK',240)])
def test_unsupported_product_keeps_its_previous_height(product,rating):
    settings = cfg.defaults()
    settings.update(product=product,rating=rating)
    before = core.layout(settings)
    settings['top_clearance_mm'] = 150
    assert core.layout(settings) == before
