# -*- coding: utf-8 -*-
import copy

import pytest
from lowlife import fire_boxes_core as core, fire_boxes_settings as cfg


@pytest.mark.parametrize('rating,wall', [(90,25), (180,70)])
@pytest.mark.parametrize('arrangement', ['vertical','horizontal'])
@pytest.mark.parametrize('configuration', core.WALL_CONFIGURATIONS)
def test_independent_diagram_dimensions_drive_width_and_rod_positions(rating,wall,arrangement,configuration):
    settings = cfg.defaults()
    settings.update(rating=rating, arrangement=arrangement, wall_configuration=configuration,
                    rod_inset_mm=15, rod_to_tray_mm=20,
                    trays=[dict(width_mm=300,height_mm=100),dict(width_mm=200,height_mm=50)])
    before = copy.deepcopy(settings)
    section = core.mounting_section(settings)
    group = 300 if arrangement == 'vertical' else 600
    assert section['width'] == group+2*(15+20)+2*wall-(wall if configuration in ('no_left','no_right') else 0)
    assert section['rods'][0]-(section['cavity_x']-section['cavity_width']/2) == 15
    assert min(row['x']-row['width']/2 for row in section['trays'])-section['rods'][0] == 20
    assert section['rods'][-1]-max(row['x']+row['width']/2 for row in section['trays']) == 20
    assert section['custom_side_spacing']
    assert settings == before


def test_changing_wall_to_rod_does_not_change_rod_to_tray():
    settings = cfg.defaults()
    settings.update(rod_to_tray_mm=20,rod_inset_mm=25)
    first = core.mounting_section(settings)
    settings['rod_inset_mm'] = 15
    second = core.mounting_section(settings)
    assert second['width'] == first['width']-20
    assert second['rod_to_tray'] == first['rod_to_tray'] == 20


def test_legacy_auto_width_stays_unchanged_until_a_diagram_edit():
    settings = cfg.defaults()
    settings.pop('rod_to_tray_mm')
    expected = core.mounting_section(settings)
    assert expected['width'] == 580
    assert expected['rod_to_tray'] == 45
    settings.update(rod_inset_mm=15,rod_to_tray_mm=20)
    assert core.layout(settings)['width'] == 510
    settings['rod_to_tray_mm'] = None
    assert core.layout(settings)['width'] == expected['width']


@pytest.mark.parametrize('key,value', [('rod_inset_mm',4),('rod_to_tray_mm',4),('rod_to_tray_mm',0),('rod_to_tray_mm',-1),('rod_to_tray_mm','nan')])
def test_rod_cannot_intersect_wall_or_tray(key,value):
    settings = cfg.defaults()
    settings.update(rod_to_tray_mm=20,rod_inset_mm=15)
    settings[key] = value
    with pytest.raises(ValueError):
        core.mounting_section(settings)


def test_explicit_side_dimensions_cannot_discard_required_extra_clearance():
    settings = cfg.defaults()
    settings.update(rod_to_tray_mm=20,rod_inset_mm=15,clearance_mm=40)
    with pytest.raises(ValueError):
        core.layout(settings)


def test_manual_spacing_roundtrip(tmp_path,monkeypatch):
    monkeypatch.setenv('APPDATA',str(tmp_path))
    settings = cfg.defaults()
    settings.update(box_type_uid='example',rod_to_tray_mm=20,rod_inset_mm=15)
    cfg.save(settings)
    assert cfg.load() == settings
