# -*- coding: utf-8 -*-
"""Settings data for the three enclosure tools; no Revit dependency."""
import copy
from lowlife.settings_core import JsonStore
from lowlife import fire_boxes_core as core
from lowlife.i18n import tr

STORE = JsonStore('LowLifeFireBoxes_settings.json', u'Огнезащитные короба')


def defaults():
    return dict(product='OSK', rating=180, arrangement='vertical', gap_mm=100.0,
                clearance_mm=0.0, elevation_mm=3000.0, box_type_uid='',
                system_type_uid='', tray_type_uid='', inside_flag_param='',
                enclosure_note_param='', support_bottom_mm=0.0,
                rod_inset_mm=25.0, ceiling_gap_mm=200.0,
                box_workset_name='', tray_workset_name='',
                wall_configuration='closed',
                rod_to_tray_mm=None,
                top_clearance_mm=None,
                trays=[dict(width_mm=300.0, height_mm=100.0, tray_type_uid='')])


def normalize(values):
    """Migrate the old single tray type without replacing explicit row types."""
    result = defaults()
    result.update(copy.deepcopy(values))
    for row in result['trays']:
        if not row.get('tray_type_uid'):
            row['tray_type_uid'] = result.get('tray_type_uid', '')
    return result


def load():
    saved = STORE.read()
    values = defaults()
    for key in values:
        values[key] = copy.deepcopy(saved.get(key, values[key]))
    return normalize(values)


def validate(values):
    core.mounting_section(values)
    core.number(values['elevation_mm'], minimum=-1000000)
    if not values.get('box_type_uid'):
        raise ValueError(tr(u'Выберите тип короба.', u'Select enclosure type.'))


def save(values):
    validate(values)
    if not STORE.write(values):
        raise IOError(tr(u'Не удалось сохранить настройки короба.', u'Could not save enclosure settings.'))
