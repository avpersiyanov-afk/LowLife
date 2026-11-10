# -*- coding: utf-8 -*-
"""Deterministic level matching and vertical-hit selection, without Revit."""
from lowlife.i18n import tr
from lowlife.level_name_template import LevelNameTemplate, DEFAULT_TEMPLATE


def match_level(levels,name,elevation,tolerance=1.0/304.8,template=None):
    template=template if isinstance(template,LevelNameTemplate) else LevelNameTemplate(template or DEFAULT_TEMPLATE)
    if template.error:
        raise ValueError(template.error)
    source=template.parse(name,with_discipline=True)
    if source is not None:
        matched=[]
        for level in levels:
            parts=template.parse(level['name'],with_discipline=True)
            if parts is not None and parts[:2]==source[:2]:
                matched.append((level,parts))
        if not matched:
            raise ValueError(tr(u'По маске уровней не найден этаж «{}» корпуса «{}» в текущей модели. Проверьте имена и маску; другой этаж автоматически не выбирается.',
                                u'No level matches floor "{}" in building "{}" in the current model. Check names and the level mask; another floor is not selected automatically.').format(source[1],source[0]))
        ar=[level for level,parts in matched if parts[3] in (u'ар','ar')]
        levels=ar or [level for level,parts in matched]
    else:
        exact=[level for level in levels if name and level['name']==name]
        levels=exact or levels
    if levels:
        distance=min(abs(level['elevation']-elevation) for level in levels)
        nearest=[level for level in levels
                 if abs(abs(level['elevation']-elevation)-distance)<=tolerance]
        if len(nearest)==1:
            return nearest[0]
        named=[level for level in nearest if level['name']==name]
        if len(named)==1:
            return named[0]
    raise ValueError(tr(u'Нельзя однозначно выбрать ближайший уровень текущей модели к отметке конструкции «{}». Проверьте уровни и корпуса.',
                        u'Cannot uniquely select the current-model level nearest to host elevation {}. Check levels and buildings.').format(name or elevation))


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
