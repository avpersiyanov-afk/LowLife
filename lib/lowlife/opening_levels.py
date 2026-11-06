# -*- coding: utf-8 -*-
"""Level comes from the pierced slab or a downward floor hit in the SAME source."""
from Autodesk.Revit.DB import (BuiltInCategory, BuiltInParameter, ElementId,
    ElementTransformUtils, FilteredElementCollector, Level, Line,
    Options, SolidCurveIntersectionOptions, ViewDetailLevel, XYZ)
from lowlife import opening_levels_core as core
from lowlife.i18n import tr


class Resolver(object):
    def __init__(self,doc):
        self.doc=doc
        self.levels=list(FilteredElementCollector(doc).OfClass(Level))
        self.sources={}
        self.options=Options()
        self.options.DetailLevel=ViewDetailLevel.Fine

    def source(self,crossing):
        from lowlife import tray_boxes as boxes
        link=crossing.link
        key=link.UniqueId if link is not None else 'local'
        if key not in self.sources:
            source=boxes._Source(link.GetLinkDocument() if link is not None else self.doc,link)
            if source.transform is not None and source.transform.BasisZ.DistanceTo(XYZ.BasisZ)>1e-6:
                raise ValueError(tr(u'Наклонённая связь не поддерживает однозначное сопоставление уровней.',
                                    u'A tilted link cannot be mapped unambiguously to host levels.'))
            self.sources[key]=(source,None)
        return key,self.sources[key][0]

    def floors(self,key,source):
        from lowlife import tray_boxes as boxes
        cached=self.sources[key][1]
        if cached is None:
            cached=[]
            for element in (FilteredElementCollector(source.doc).OfCategory(BuiltInCategory.OST_Floors)
                            .WhereElementIsNotElementType()):
                bb=element.get_BoundingBox(None)
                if bb is not None:
                    pts=boxes._box_points(bb)
                    cached.append((element,
                        (min(p.X for p in pts),max(p.X for p in pts),
                         min(p.Y for p in pts),max(p.Y for p in pts),
                         min(p.Z for p in pts))))
            self.sources[key]=(source,cached)
        return cached

    def resolve(self,crossing):
        from lowlife import tray_boxes as boxes
        key,source=self.source(crossing)
        support=crossing.host
        method='floor_host'
        if crossing.kind=='wall':
            method='downward_ray'
            start=source.to_local(boxes._xyz(crossing.center()))
            tolerance=1.0/304.8
            candidates=[(el,b) for el,b in self.floors(key,source)
                        if b[0]-tolerance<=start.X<=b[1]+tolerance and
                           b[2]-tolerance<=start.Y<=b[3]+tolerance and b[4]<=start.Z]
            hits=[]
            if candidates:
                end=XYZ(start.X,start.Y,min(b[4] for el,b in candidates)-1.0)
                ray=Line.CreateBound(start,end)
                for floor,bounds in candidates:
                    for solid in source.solids(floor,self.options):
                        intersection=solid.IntersectWithCurve(ray,SolidCurveIntersectionOptions())
                        try:
                            for i in range(intersection.SegmentCount):
                                segment=intersection.GetCurveSegment(i)
                                distance=min(start.Z-segment.GetEndPoint(j).Z for j in (0,1))
                                level=source.doc.GetElement(floor.LevelId)
                                hits.append(dict(distance=max(0.0,distance),host_uid=floor.UniqueId,
                                                 level_uid=level.UniqueId if isinstance(level,Level) else None,
                                                 element=floor))
                        finally:
                            intersection.Dispose()
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


def instance_level_id(instance):
    if instance.LevelId!=ElementId.InvalidElementId:
        return instance.LevelId
    host=instance.Host
    if isinstance(host,Level):
        return host.Id
    for name in ('FAMILY_LEVEL_PARAM','INSTANCE_REFERENCE_LEVEL_PARAM'):
        param=instance.get_Parameter(getattr(BuiltInParameter,name))
        if param is not None and param.HasValue:
            value=param.AsElementId()
            if value!=ElementId.InvalidElementId:
                return value
    return ElementId.InvalidElementId


def assign_level(doc,instance,level):
    """Change the actual instance level without changing its physical position/ID."""
    if instance_level_id(instance)==level.Id:
        return
    before=instance.Location.Point
    param=None
    for name in ('FAMILY_LEVEL_PARAM','INSTANCE_REFERENCE_LEVEL_PARAM'):
        candidate=instance.get_Parameter(getattr(BuiltInParameter,name))
        if candidate is not None and not candidate.IsReadOnly:
            param=candidate
            break
    if param is None or not param.Set(level.Id):
        raise ValueError(tr(u'Семейство бокса не позволяет изменить уровень без пересоздания.',
                            u'The box family cannot change its level without recreation.'))
    doc.Regenerate()
    if instance_level_id(instance)!=level.Id:
        raise ValueError(tr(u'Семейство бокса не применило уровень конструкции.',
                            u'The box family did not apply the host level.'))
    delta=before.Subtract(instance.Location.Point)
    if delta.GetLength()>1e-9:
        ElementTransformUtils.MoveElement(doc,instance.Id,delta)
    doc.Regenerate()
    if instance.Location.Point.DistanceTo(before)>1e-6:
        raise ValueError(tr(u'Смена уровня переместила бокс. Изменение отменено.',
                            u'Changing the level moved the box. The change was cancelled.'))
