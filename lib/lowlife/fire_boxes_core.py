# -*- coding: utf-8 -*-
"""Fire enclosure sizing and cross-section geometry, without Revit.

Allowances reproduce 2fpro.com/d3dcont/calc-{fire,osk}.js (2026-11-06).
OSK values are TOTAL allowances, not panel thicknesses. Clearances are
explicit project inputs and are never represented as manufacturer's minima.
"""
import math
from collections import OrderedDict
from lowlife.i18n import tr

try:
    unicode
except NameError:
    unicode = str

FIREBOX_WALLS = {90: 50, 150: 75, 180: 90, 240: 120}
OSK_ALLOWANCES = {90: (260, 290), 180: (280, 290), 240: (310, 270)}
# Attached ATR A2-OSK90 sheets 2-4,10; A1-OSK180 sheets 2-3,8.
OSK_PANELS = {90: 25.0, 180: 70.0}


def number(value, minimum=0, positive=False):
    result = float(unicode(value).replace(',', '.'))
    if math.isnan(result) or math.isinf(result) or result < minimum or (positive and result <= 0):
        raise ValueError(tr(u'Укажите положительный конечный размер.', u'Enter a positive finite dimension.') if positive else tr(u'Недопустимый размер.', u'Invalid dimension.'))
    return result


def ratings(product):
    if product not in ('FIREBOX', 'OSK'):
        raise ValueError(tr(u'Неизвестная конструкция короба.', u'Unknown enclosure system.'))
    return sorted(FIREBOX_WALLS if product == 'FIREBOX' else OSK_ALLOWANCES)


def allowances(product, rating):
    if int(rating) not in ratings(product):
        raise ValueError(tr(u'Огнестойкость не поддерживается выбранной конструкцией.', u'Fire resistance is not supported by this enclosure system.'))
    if product == 'FIREBOX':
        wall = FIREBOX_WALLS[int(rating)]
        return (2 * wall, 2 * wall)
    return OSK_ALLOWANCES[int(rating)]


def layout(settings):
    rows = settings.get('trays') or []
    if not rows or len(rows) > 32:
        raise ValueError(tr(u'Укажите от 1 до 32 лотков.', u'Specify 1 to 32 trays.'))
    direction = settings.get('arrangement', 'vertical')
    if direction not in ('vertical', 'horizontal'):
        raise ValueError(tr(u'Выберите расположение лотков.', u'Select a tray arrangement.'))
    gap = number(settings.get('gap_mm', 100))
    clearance = number(settings.get('clearance_mm', 0))
    sizes = [(number(r['width_mm'], positive=True), number(r['height_mm'], positive=True)) for r in rows]
    if direction == 'vertical':
        width = max(w for w, h in sizes)
        height = sum(h for w, h in sizes) + gap * (len(sizes) - 1)
    else:
        width = sum(w for w, h in sizes) + gap * (len(sizes) - 1)
        height = max(h for w, h in sizes)
    placements, cursor = [], 0.0
    for index, (w, h) in enumerate(sizes):
        x = cursor + w / 2 - width / 2 if direction == 'horizontal' else 0
        z = cursor + h / 2 - height / 2 if direction == 'vertical' else (h - height) / 2
        placements.append(dict(index=index, x=x, z=z, width=w, height=h,
                               tray_type_uid=rows[index].get('tray_type_uid') or settings.get('tray_type_uid', '')))
        cursor += (w if direction == 'horizontal' else h) + gap
    inner_w, inner_h = width + 2 * clearance, height + 2 * clearance
    dw, dh = allowances(settings['product'], int(settings['rating']))
    section = dict(trays=placements, inner_width=inner_w, inner_height=inner_h,
                width=inner_w + dw, height=inner_h + dh,
                allowance_width=dw, allowance_height=dh)
    wall = (OSK_PANELS.get(int(settings['rating'])) if settings['product'] == 'OSK'
            else float(FIREBOX_WALLS[int(settings['rating'])]))
    section['wall'] = wall
    section['cavity_width'] = section['width'] - 2*wall if wall is not None else inner_w
    section['cavity_height'] = section['height'] - 2*wall if wall is not None else inner_h
    if settings['product'] == 'OSK' and wall is not None and 'support_bottom_mm' in settings:
        bottom = number(settings['support_bottom_mm'])
        if bottom == 0:
            bottom = 80.0 if int(settings['rating']) == 90 else 50.0
        minimum = 80.0 if int(settings['rating']) == 90 else 30.0
        if bottom < minimum:
            raise ValueError(tr(u'Под лотком нужно место для траверсы и каркаса: не менее {} мм.',
                                u'Allow at least {} mm below the tray for the crossbar and frame.').format(minimum))
        offset_z = -section['height']/2 + wall + bottom + clearance + height/2
        for row in placements:
            row['z'] += offset_z
    section['tray_bottom'] = min(r['z'] - r['height']/2 for r in placements)
    section['tray_top'] = max(r['z'] + r['height']/2 for r in placements)
    section['bottom_clear'] = section['tray_bottom'] + section['cavity_height']/2
    section['top_clear'] = section['cavity_height']/2 - section['tray_top']
    section['side_clear'] = (section['cavity_width'] - width)/2
    if section['top_clear'] < -0.001:
        raise ValueError(tr(u'Лотки выходят за крышку короба: уменьшите нижний отступ.',
                            u'Trays exceed the enclosure lid: reduce the bottom clearance.'))
    return section


def mounting_section(settings, section=None):
    """Physical section used by BOTH preview and routing (millimetres).

    Rod inset and ceiling gap are project choices; starred ATR dimensions are
    not mandatory constants. No construction details are inferred for OSK240.
    """
    section = section or layout(settings)
    supported = settings['product'] == 'OSK' and int(settings['rating']) in OSK_PANELS
    result = dict(section, rods=[], crossbars=[], middle_rod_required=False,
                  middle_rod_missing=False, mounting_supported=supported,
                  ceiling_gap=number(settings.get('ceiling_gap_mm', 200)))
    if not supported:
        return result
    if settings['arrangement'] == 'vertical' and len(section['trays']) > 1 and number(settings.get('gap_mm', 100)) < 30:
        raise ValueError(tr(u'Между ярусами нужно не менее 30 мм для траверсы.',
                            u'Allow at least 30 mm between tiers for a crossbar.'))
    inset = number(settings.get('rod_inset_mm', 25), positive=True)
    half_cavity = section['cavity_width']/2
    left, right = -half_cavity + inset, half_cavity - inset
    radius = 5.0  # M8/M10 envelope: use the larger diameter for clearance checks.
    if left >= right:
        raise ValueError(tr(u'Шпильки не помещаются в сечении.', u'The rods do not fit the cross-section.'))
    def clear(x):
        return all(x+radius <= r['x']-r['width']/2 or x-radius >= r['x']+r['width']/2
                   for r in section['trays'])
    if not clear(left) or not clear(right):
        raise ValueError(tr(u'Шпилька пересекает лоток: измените отступ шпильки или компоновку.',
                            u'A rod intersects a tray: change the rod inset or layout.'))
    rods = [left, right]
    threshold = 1200 if int(settings['rating']) == 90 else 1500
    if section['width'] > threshold:
        result['middle_rod_required'] = True
        candidates = [0.0]
        ordered = sorted(section['trays'], key=lambda row: row['x'])
        candidates += [(a['x']+a['width']/2+b['x']-b['width']/2)/2 for a,b in zip(ordered,ordered[1:])]
        candidates = [x for x in candidates if left+radius*2 < x < right-radius*2 and clear(x)]
        if candidates:
            rods.append(min(candidates, key=abs))
        else:
            result['middle_rod_missing'] = True
    result['rods'] = sorted(rods)
    result['crossbars'] = sorted(set(r['z']-r['height']/2 for r in section['trays']))
    result['profile_height'] = 50.0 if int(settings['rating']) == 90 else 0.0
    result['crossbar_height'] = 30.0
    result['source_sheet'] = 10 if int(settings['rating']) == 90 else 8
    result['rod_inset'] = inset
    return result


def fits(actual_width, actual_height, settings, tolerance=0.5):
    section = layout(settings)
    return actual_width + tolerance >= section['width'] and actual_height + tolerance >= section['height']


def description(settings):
    """Model data, deliberately independent of interface language."""
    groups = OrderedDict()
    for row in layout(settings)['trays']:
        key = u'{:g}\u00d7{:g}'.format(float(row['width']), float(row['height']))
        groups[key] = groups.get(key, 0) + 1
    sizes = u'; '.join(u'{} \u0448\u0442. {} \u043c\u043c'.format(n, size) for size, n in groups.items())
    product_name = u'\u041e\u0421\u041a' if settings['product'] == 'OSK' else 'FIREBOX'
    return u'{}; EI {}; \u043b\u043e\u0442\u043a\u0438: {}'.format(product_name, settings['rating'], sizes)


def merge_note(existing, note):
    """Replace our own line; preserve the user's other notes."""
    lines = [line for line in (existing or u'').splitlines() if not line.startswith('[LowLife OKK] ')]
    return u'\n'.join(lines + [u'[LowLife OKK] ' + note])


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def mul(a, n):
    return tuple(x * n for x in a)


def unit(a):
    length = math.sqrt(dot(a, a))
    if length < 1e-9:
        raise ValueError(tr(u'Нулевая длина оси.', u'Zero length axis.'))
    return mul(a, 1 / length)


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def frame(start, end):
    direction = unit(sub(end, start))
    right = cross(direction, (0, 0, 1))
    if dot(right, right) < 1e-8:
        right = (1, 0, 0)
    right = unit(right)
    up = unit(cross(right, direction))
    return right, up


def line_intersection(a, da, b, db, tolerance=1.0):
    """Intersection of 3D infinite lines, refusing skew/parallel lines."""
    da, db = unit(da), unit(db)
    c = dot(da, db)
    denominator = 1 - c*c
    if abs(denominator) < 1e-8:
        if math.sqrt(dot(cross(sub(b, a), da), cross(sub(b, a), da))) > tolerance:
            raise ValueError(tr(u'Параллельные смещённые трассы не сходятся.', u'Parallel offset routes do not meet.'))
        return mul(add(a, b), 0.5)
    delta = sub(b, a)
    t = (dot(delta, da) - c * dot(delta, db)) / denominator
    s = (c * dot(delta, da) - dot(delta, db)) / denominator
    p, q = add(a, mul(da, t)), add(b, mul(db, s))
    if math.sqrt(dot(sub(p, q), sub(p, q))) > tolerance:
        raise ValueError(tr(u'Смещённые трассы не сходятся в пространстве.', u'Offset routes do not meet in 3D.'))
    return mul(add(p, q), 0.5)


def section_fits_axes(row, right, up, box_right, box_up, inner_width, inner_height, tolerance=0.5):
    """Containment of an offset tray rectangle in a possibly rolled enclosure."""
    offset = add(mul(right, row['x']), mul(up, row['z']))
    for axis, limit in ((box_right, inner_width), (box_up, inner_height)):
        occupied = (abs(dot(offset, axis)) + abs(dot(right, axis)) * row['width']/2
                    + abs(dot(up, axis)) * row['height']/2)
        if occupied > limit/2 + tolerance:
            return False
    return True
