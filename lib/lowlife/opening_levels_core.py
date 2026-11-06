# -*- coding: utf-8 -*-
"""Deterministic level matching and vertical-hit selection, without Revit."""
from lowlife.i18n import tr


def match_level(levels,name,elevation,tolerance=1.0/304.8):
    exact=[level for level in levels if level['name']==name and
           abs(level['elevation']-elevation)<=tolerance]
    if len(exact)!=1:
        raise ValueError(tr(u'Нет однозначного уровня ВИС «{}» на отметке конструкции. Проверьте имя и отметку уровня.',
                            u'No unique VIS level named {} at the structural elevation. Check the level name and elevation.').format(name))
    return exact[0]


def first_hit(hits,tolerance=1.0/304.8):
    hits=[h for h in hits if h['distance']>=-tolerance]
    if not hits:
        raise ValueError(tr(u'Луч вниз не пересёк перекрытие в выбранной модели конструкции.',
                            u'The downward ray did not intersect a floor in the selected host model.'))
    hits.sort(key=lambda h:(h['distance'],h['host_uid']))
    first=hits[0]
    tied=[h for h in hits if abs(h['distance']-first['distance'])<=tolerance]
    if len(set(h.get('level_uid') for h in tied))>1:
        raise ValueError(tr(u'Под отверстием пересекаются конструкции разных уровней на одной отметке. Нужна проверка.',
                            u'Below the opening, structures assigned to different levels overlap at the same elevation. Review required.'))
    if not first.get('level_uid'):
        raise ValueError(tr(u'У конструкции под отверстием не задан уровень.',
                            u'The structure below the opening has no level.'))
    return first
