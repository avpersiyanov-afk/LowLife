# -*- coding: utf-8 -*-
import copy

import pytest
from lowlife import fire_boxes_core as core, fire_boxes_settings as cfg


@pytest.mark.parametrize('rating,wall', [(90,25), (180,70)])
@pytest.mark.parametrize('configuration,dx,dz,dw,dh', [
    ('no_top',0,0.5,0,1), ('no_left',-0.5,0,1,0), ('no_right',0.5,0,1,0)])
def test_open_osk_reduces_external_envelope_and_keeps_clear_interior(rating,wall,configuration,dx,dz,dw,dh):
    settings = cfg.defaults()
    settings.update(rating=rating, trays=[dict(width_mm=300,height_mm=100),dict(width_mm=200,height_mm=50)])
    closed = core.mounting_section(settings)
    settings['wall_configuration'] = configuration
    before = copy.deepcopy(settings)
    opened = core.mounting_section(settings)
    assert settings == before
    assert opened['width'] == closed['width']-dw*wall
    assert opened['height'] == closed['height']-dh*wall
    for key in ('cavity_width','cavity_height','bottom_clear','top_clear','side_clear'):
        assert opened[key] == closed[key]
    assert opened['cavity_x'] == dx*wall
    assert opened['cavity_z'] == dz*wall
    for old,new in zip(closed['trays'],opened['trays']):
        assert new['x'] == old['x']+dx*wall
        assert new['z'] == old['z']+dz*wall
        assert core.section_fits_axes(new,(1,0,0),(0,1,0),(1,0,0),(0,1,0),
                                     opened['cavity_width'],opened['cavity_height'],
                                     cavity_center=(opened['cavity_x'],opened['cavity_z']))
    assert opened['rods'] == [x+dx*wall for x in closed['rods']]
    assert opened['crossbars'] == [z+dz*wall for z in closed['crossbars']]
    assert opened['ceiling_gap'] == (0 if configuration == 'no_top' else closed['ceiling_gap'])
    assert core.fits(opened['width'],opened['height'],settings)
    assert not core.fits(opened['width']-1,opened['height'],settings)


@pytest.mark.parametrize('configuration', ['no_top','no_left','no_right'])
@pytest.mark.parametrize('product,rating', [('FIREBOX',180),('OSK',240)])
def test_unsupported_open_configuration_is_not_invented(product,rating,configuration):
    settings = cfg.defaults()
    settings.update(product=product,rating=rating,wall_configuration=configuration)
    with pytest.raises(ValueError):
        core.layout(settings)


def test_unknown_configuration_is_rejected():
    settings = cfg.defaults()
    settings['wall_configuration'] = 'no_bottom'
    with pytest.raises(ValueError):
        core.layout(settings)


def test_legacy_settings_keep_closed_envelope():
    settings = cfg.defaults()
    expected = core.layout(settings)
    settings.pop('wall_configuration')
    assert core.layout(settings) == expected
    assert cfg.normalize(settings)['wall_configuration'] == 'closed'


@pytest.mark.parametrize('configuration,phrase', [('no_top',u'без верхней'),('no_left',u'без левой'),('no_right',u'без правой')])
def test_configuration_survives_save_and_note(tmp_path,monkeypatch,configuration,phrase):
    monkeypatch.setenv('APPDATA',str(tmp_path))
    settings = cfg.defaults()
    settings.update(box_type_uid='example',wall_configuration=configuration)
    cfg.save(settings)
    loaded = cfg.load()
    assert loaded == settings
    assert phrase in core.description(loaded)
    assert 'EI 180' in core.description(loaded)
