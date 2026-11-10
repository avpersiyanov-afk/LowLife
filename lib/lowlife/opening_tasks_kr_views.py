# -*- coding: utf-8 -*-
"""Managed structural slab plans and wall-face sections, driven by KR receipts."""
from Autodesk.Revit.DB import (BoundingBoxXYZ, BuiltInParameter, Color, ElementId,
    FillPatternElement, FilteredElementCollector, Floor, RoofBase, Level, Line, OverrideGraphicSettings,
    PlanViewPlane, Transform, ViewFamily, ViewFamilyType, ViewPlan, ViewSection, Wall, XYZ)
from lowlife.i18n import tr
from lowlife.geometry import get_element_level
from lowlife.opening_levels_core import match_level
from lowlife import opening_tasks_storage as store
from lowlife import opening_tasks_revit as api
from lowlife.opening_tasks_views import unique_name
from lowlife.opening_tasks_visibility import configure


def corners(bb):
    return [bb.Transform.OfPoint(XYZ(x,y,z)) for x in (bb.Min.X,bb.Max.X)
            for y in (bb.Min.Y,bb.Max.Y) for z in (bb.Min.Z,bb.Max.Z)]


def projected_box(points, frame, pad):
    local=[frame.Inverse.OfPoint(p) for p in points]
    if not local:
        raise ValueError(tr(u'Не найден габарит конструкции.',u'Host bounding geometry is missing.'))
    box=BoundingBoxXYZ()
    box.Transform=frame
    box.Min=XYZ(min(p.X for p in local)-pad,min(p.Y for p in local)-pad,min(p.Z for p in local)-pad)
    box.Max=XYZ(max(p.X for p in local)+pad,max(p.Y for p in local)+pad,max(p.Z for p in local)+pad)
    return box


def build(doc, project, mode, records=None):
    registry=store.registry(doc)
    managed=registry.setdefault('kr_control_views',{})
    receipts={r['opening_uid']:r for r in registry['receipts'].values()
              if r.get('project')==project and r.get('status')=='accepted' and r.get('opening_uid')}
    accepted=[]
    for uid,r in receipts.items():
        opening=doc.GetElement(uid)
        host=doc.GetElement(r['geometry']['host_uid'])
        if opening is not None and host is not None:
            accepted.append((opening,host,r))
    family=ViewFamily.FloorPlan if mode=='plans' else ViewFamily.Section
    typ=next((t for t in FilteredElementCollector(doc).OfClass(ViewFamilyType) if t.ViewFamily==family),None)
    if typ is None:
        raise ValueError(tr(u'Не найден подходящий тип вида.',u'Required view type was not found.'))
    output=[]
    blue=Color(30,100,240)
    orange=Color(240,140,40)
    solid=next((f.Id for f in FilteredElementCollector(doc).OfClass(FillPatternElement) if f.GetFillPattern().IsSolidFill),None)
    def existing(key,cls):
        view=doc.GetElement(managed[key]) if key in managed else None
        if view is not None and (not isinstance(view,cls) or view.IsTemplate):
            raise ValueError(tr(u'Неверный тип сохранённого вида КР.',u'Invalid stored KR view type.'))
        return view
    def decorate(view,entries):
        configure(doc,view,[opening for opening,host,r in entries],structures=True)
        for opening,host,r in entries:
            color=blue if api.opening_matches(opening,r) else orange
            ogs=OverrideGraphicSettings().SetProjectionLineColor(color).SetCutLineColor(color)
            if solid:
                ogs.SetSurfaceForegroundPatternId(solid).SetSurfaceForegroundPatternColor(color)
                ogs.SetCutForegroundPatternId(solid).SetCutForegroundPatternColor(color)
            view.SetElementOverrides(opening.Id,ogs)
    if mode=='plans':
        levels=list(FilteredElementCollector(doc).OfClass(Level))
        candidates=[dict(name=api.boxes.safe_element_name(level),elevation=level.ProjectElevation,element=level) for level in levels]
        by_level={}
        for entry in accepted:
            opening,host,receipt=entry
            if not isinstance(host,(Floor,RoofBase)):continue
            assigned=get_element_level(doc,host)
            if assigned is None:
                assigned=match_level(candidates,'',api.boxes.ft(receipt['geometry']['center_mm'][2]))['element']
            by_level.setdefault(assigned.Id,[]).append(entry)
        for level in levels:
            key=project+'/slab-plan/'+level.UniqueId
            view=existing(key,ViewPlan)
            if view is None:
                view=ViewPlan.Create(doc,typ.Id,level.Id)
                view.Name=unique_name(doc,u'LowLife | '+project+u' | Плиты | '+level.Name)
                managed[key]=view.UniqueId
            entries=by_level.get(level.Id,[])
            bounds=[e[1].get_BoundingBox(None) for e in entries]
            bounds=[b for b in bounds if b is not None]
            low=min([b.Min.Z-level.ProjectElevation for b in bounds]+[-api.boxes.ft(500)])
            high=max([b.Max.Z-level.ProjectElevation for b in bounds]+[api.boxes.ft(500)])
            cut=(min(b.Min.Z for b in bounds)+max(b.Max.Z for b in bounds))/2-level.ProjectElevation if bounds else 0.0
            vr=view.GetViewRange()
            for plane,offset in [(PlanViewPlane.TopClipPlane,high+api.boxes.ft(100)),
                                 (PlanViewPlane.CutPlane,cut),
                                 (PlanViewPlane.BottomClipPlane,low-api.boxes.ft(100)),
                                 (PlanViewPlane.ViewDepthPlane,low-api.boxes.ft(100))]:
                vr.SetLevelId(plane,level.Id)
                vr.SetOffset(plane,offset)
            view.SetViewRange(vr)
            decorate(view,entries)
            output.append(view)
    else:
        if records:
            host_ids=set(r['geometry']['host_uid'] for r in records if r['geometry']['kind']=='wall')
        else:
            host_ids=set(host.UniqueId for opening,host,r in accepted if isinstance(host,Wall))
        for uid in sorted(host_ids):
            wall=doc.GetElement(uid)
            if not isinstance(wall,Wall) or not isinstance(wall.Location.Curve,Line):
                raise ValueError(tr(u'Разрезы поддерживают только прямые стены.',u'Sections support straight walls only.'))
            bb=wall.get_BoundingBox(None)
            if bb is None:
                continue
            x=wall.Location.Curve.Direction
            if abs(x.Z)>1e-6:
                raise ValueError(tr(u'Ось стены должна быть горизонтальной.',u'Wall axis must be horizontal.'))
            up=XYZ.BasisZ
            normal=x.CrossProduct(up).Normalize()
            origin=wall.Location.Curve.Evaluate(.5,True)
            center=XYZ(origin.X,origin.Y,(bb.Min.Z+bb.Max.Z)/2)
            frame=Transform.Identity
            frame.Origin=center.Subtract(normal.Multiply(wall.Width/2+api.boxes.ft(600)))
            frame.BasisX=x
            frame.BasisY=up
            frame.BasisZ=normal
            points=corners(bb)
            crop=projected_box(points,frame,api.boxes.ft(300))
            key=project+'/wall-section/'+uid
            view=existing(key,ViewSection)
            if view is None:
                view=ViewSection.CreateSection(doc,typ.Id,crop)
                view.Name=unique_name(doc,u'LowLife | '+project+u' | Стена '+str(api.boxes._id_int(wall.Id)))
                managed[key]=view.UniqueId
            else:
                actual=view.CropBox.Transform
                if abs(actual.BasisZ.DotProduct(normal))<.999:
                    raise ValueError(tr(u'Стена повернулась: удалите устаревший разрез и повторите команду.',
                                        u'Wall rotated: delete its outdated section and run the command again.'))
                crop=projected_box(points,actual,api.boxes.ft(300))
                if crop.Max.Z<=0:
                    raise ValueError(tr(u'Стена вышла за плоскость разреза. Пересоздайте этот разрез.',
                                        u'Wall moved behind its section plane. Recreate that section.'))
                view.CropBox=crop
            far=view.get_Parameter(BuiltInParameter.VIEWER_BOUND_OFFSET_FAR)
            if far is not None and not far.IsReadOnly:
                far.Set(max(crop.Max.Z,api.boxes.ft(100)))
            view.CropBoxActive=True
            view.CropBoxVisible=False
            decorate(view,[e for e in accepted if e[1].UniqueId==uid])
            output.append(view)
    store.save_registry(doc,registry)
    return output
