# -*- coding: utf-8 -*-
"""Deterministic level matching and vertical-hit selection, without Revit."""
from lowlife.i18n import tr


def match_level(levels,name,elevation,tolerance=1.0/304.8):
    at_elevation=[level for level in levels if abs(level['elevation']-elevation)<=tolerance]
    exact=[level for level in at_elevation if level['name']==name]
    if len(exact)==1:
        return exact[0]
    if not exact and len(at_elevation)==1:
        return at_elevation[0]
    raise ValueError(tr(u'Нет однозначного уровня текущей модели на отметке конструкции «{}». Проверьте уровни АР и корпуса.',
                        u'No unique current-model level at the host elevation {}. Check architectural levels and buildings.').format(name or elevation))


def first_hit(hits,tolerance=1.0/304.8,allow_missing_level=False):
    hits=[h for h in hits if h['distance']>=-tolerance]
    if not hits:
        raise ValueError(tr(u'Луч вниз не пересёк перекрытие или фундамент в выбранной модели конструкции.',
                            u'The downward ray did not intersect a floor or foundation in the selected host model.'))
    hits.sort(key=lambda h:(h['distance'],h['host_uid']))
    first=hits[0]
    tied=[h for h in hits if abs(h['distance']-first['distance'])<=tolerance]
    if len(set(h.get('level_uid') for h in tied))>1:
        raise ValueError(tr(u'Под отверстием пересекаются конструкции разных уровней на одной отметке. Нужна проверка.',
                            u'Below the opening, structures assigned to different levels overlap at the same elevation. Review required.'))
    if not first.get('level_uid') and not allow_missing_level:
        raise ValueError(tr(u'У конструкции под отверстием не задан уровень.',
                            u'The structure below the opening has no level.'))
    return first
