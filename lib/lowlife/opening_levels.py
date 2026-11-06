# -*- coding: utf-8 -*-
"""Level comes from the pierced slab or a downward floor hit in the SAME source."""
from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector, Level, Transform, XYZ
from lowlife import opening_levels_core as core
from lowlife.i18n import tr


class Resolver(object):
    def __init__(self,doc):
        self.doc=doc
        self.levels=list(FilteredElementCollector(doc).OfClass(Level))
        self.sources={}
        self.probes={}

    def source(self,crossing):
        from lowlife import tray_boxes as boxes
        link=crossing.link
        key=link.UniqueId if link is not None else 'local'
        if key not in self.sources:
            source=boxes._Source(link.GetLinkDocument() if link is not None else self.doc,link)
            if source.transform is not None and source.transform.BasisZ.DistanceTo(XYZ.BasisZ)>1e-6:
                raise ValueError(tr(u'Наклонённая связь не поддерживает однозначное сопоставление уровней.',
                                    u'A tilted link cannot be mapped unambiguously to host levels.'))
            self.sources[key]=source
        return key,self.sources[key]

    def probe(self,key,source):
        from lowlife.slab_marks import SlabProbe
        if key not in self.probes:
            self.probes[key]=SlabProbe(self.doc,
                sources={0:(source.doc,source.transform if source.transform is not None else Transform.Identity)},
                categories=[BuiltInCategory.OST_Floors],down_range_mm=None)
        return self.probes[key]

    def resolve(self,crossing):
        from lowlife import tray_boxes as boxes
        key,source=self.source(crossing)
        support=crossing.host
        method='floor_host'
        if crossing.kind=='wall':
            method='downward_ray'
            point=boxes._xyz(crossing.center())
            hits=[]
            for distance,floor in self.probe(key,source).floor_hits_below(point.X,point.Y,point.Z):
                level=source.doc.GetElement(floor.LevelId)
                hits.append(dict(distance=distance,host_uid=floor.UniqueId,
                    level_uid=level.UniqueId if isinstance(level,Level) else None,element=floor))
            support=core.first_hit(hits)['element']
        elif crossing.kind!='floor':
            raise ValueError(tr(u'Не поддерживается тип конструкции для определения уровня.',
                                u'Unsupported host kind for level resolution.'))
        source_level=source.doc.GetElement(support.LevelId)
        if not isinstance(source_level,Level):
            raise ValueError(tr(u'У пересекаемой конструкции не задан уровень.',u'The intersected host has no level.'))
        name=boxes.safe_element_name(source_level)
        elevation=source.to_model(XYZ(0,0,source_level.ProjectElevation)).Z
        if crossing.link is None:
            target=source_level
        else:
            candidates=[dict(name=boxes.safe_element_name(lv),elevation=lv.ProjectElevation,element=lv)
                        for lv in self.levels]
            target=core.match_level(candidates,name,elevation)['element']
        info=dict(name=name,source_level_uid=source_level.UniqueId,
                  source_model=source.doc.ProjectInformation.UniqueId,
                  support_uid=support.UniqueId,method=method,
                  elevation_mm=boxes.mm(elevation),box_level_uid=target.UniqueId)
        return target,info



def assign_level(doc,instance,level):
    """Reuse the established level assigner, with strict target and position checks."""
    from lowlife import level_assign, geometry
    current=geometry.get_element_level(doc,instance)
    if current is not None and current.Id==level.Id:
        return
    before=instance.Location.Point
    if not level_assign.assign_by_param(doc,instance,level):
        raise ValueError(tr(u'Семейство бокса не позволяет изменить уровень без пересоздания.',
                            u'The box family cannot change its level without recreation.'))
    current=geometry.get_element_level(doc,instance)
    if current is None or current.Id!=level.Id:
        raise ValueError(tr(u'Семейство бокса не применило уровень конструкции.',
                            u'The box family did not apply the host level.'))
    if instance.Location.Point.DistanceTo(before)>1e-6:
        raise ValueError(tr(u'Смена уровня переместила бокс. Изменение отменено.',
                            u'Changing the level moved the box. The change was cancelled.'))
