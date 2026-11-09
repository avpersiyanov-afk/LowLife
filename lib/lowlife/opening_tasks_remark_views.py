# -*- coding: utf-8 -*-
"""Idempotent group labels on tool-owned VIS views; no edits to user views."""
import copy
from Autodesk.Revit.DB import (Color, ElementId, ElementTypeGroup, FillPatternElement, FilteredElementCollector,
    OverrideGraphicSettings, TextNote, TextNoteLeaderTypes, View, View3D, ViewSchedule)
from pyrevit import revit
from lowlife import opening_tasks_core as core
from lowlife import opening_tasks_storage as store
from lowlife import tray_boxes as boxes
from lowlife.tag_layout import TagItem, find_clusters, layout, rect_union
from lowlife.i18n import tr


def sync(doc,project,rows,registry):
    if not project:return
    active=[row for row in rows if row.get('remark_group_id') and
            row.get('remark_state') in ('correction','review','withdraw_pending')]
    states=registry.get('remark_view_states',{})
    previous=states.get(project,{})
    offline=set(row['uid'] for row in rows if row.get('feedback_available') is False)
    preserve=set(previous.get('members',{}).get(uid) for uid in offline)
    preserve.discard(None)
    active=[row for row in active if row['remark_group_id'] not in preserve]
    if not active and not previous:return
    managed={key:uid for key,uid in registry.get('control_views',{}).items() if key.startswith(project+'/')}
    elements={}
    fingerprints=[]
    for row in active:
        element=doc.GetElement(row['uid'])
        bounds=element.get_BoundingBox(None) if element is not None else None
        points=boxes._box_points(bounds) if bounds is not None else []
        fingerprints.append((row['uid'],row['remark_group_id'],row['remark_number'],row['remark_state'],
                             [(round(p.X,6),round(p.Y,6),round(p.Z,6)) for p in points]))
        if element is not None:elements[row['uid']]=element
    signature=core.dumps(dict(offline=sorted(offline),views=sorted(managed.values()),rows=sorted(fingerprints)))
    if previous.get('signature')==signature and all(doc.GetElement(uid) is not None for uid in previous.get('notes',[])):
        return
    views=[]
    seen=set()
    for uid in managed.values():
        view=doc.GetElement(uid)
        if (uid in seen or not isinstance(view,View) or isinstance(view,ViewSchedule) or view.IsTemplate or
                isinstance(view,View3D) and view.IsPerspective):continue
        views.append(view);seen.add(uid)
    grouped={}
    for row in active:
        element=elements.get(row['uid'])
        if element is not None:
            grouped.setdefault((row['remark_group_id'],row['remark_state']),[]).append((row,element))
    plans=[]
    for view in views:
        visible=set(FilteredElementCollector(doc,view.Id).WhereElementIsNotElementType().ToElementIds())
        origin=view.Origin;right=view.RightDirection;up=view.UpDirection
        labels=[]
        for (gid,state),members in grouped.items():
            items=[];index={}
            for row,element in members:
                if element.Id not in visible:continue
                bbox=element.get_BoundingBox(view) or element.get_BoundingBox(None)
                if bbox is None:continue
                pts=[p.Subtract(origin) for p in boxes._box_points(bbox)]
                xs=[p.DotProduct(right) for p in pts];ys=[p.DotProduct(up) for p in pts]
                rect=(min(xs),min(ys),max(xs),max(ys))
                anchor=((rect[0]+rect[2])/2,(rect[1]+rect[3])/2)
                items.append(TagItem(element.UniqueId,anchor,rect,(0,0)))
                index[element.UniqueId]=(row,element)
            for cluster in find_clusters(items,boxes.ft(3000),split=False):
                caption=(u'Исправлено, ожидает проверки' if state=='review' else
                         u'Отзыв ожидает отработки' if state=='withdraw_pending' else u'На исправление')
                text=caption+u'\r'+index[cluster[0].key][0]['remark_number']
                x=max(i.elem_rect[2] for i in cluster)+boxes.ft(8*view.Scale)
                y=max(i.elem_rect[3] for i in cluster)+boxes.ft(5*view.Scale)
                pos=origin.Add(right.Multiply(x)).Add(up.Multiply(y))
                ends=[origin.Add(right.Multiply(i.anchor[0])).Add(up.Multiply(i.anchor[1])) for i in cluster]
                rect=rect_union([item.elem_rect for item in cluster])
                labels.append(TagItem(len(plans),((rect[0]+rect[2])/2,(rect[1]+rect[3])/2),rect,
                                      (boxes.ft(55*view.Scale),boxes.ft(8*view.Scale))))
                plans.append((view,gid,state,text,pos,ends,[index[i.key][1] for i in cluster]))
        for placement in layout(labels,offset=boxes.ft(8*view.Scale),gap=boxes.ft(3*view.Scale),
                                shelf=boxes.ft(4*view.Scale),cluster_dist=boxes.ft(3000)):
            plan=list(plans[placement.key])
            plan[4]=origin.Add(right.Multiply(placement.tag_rect[0])).Add(up.Multiply(placement.tag_rect[3]))
            plans[placement.key]=tuple(plan)
    type_id=doc.GetDefaultElementTypeId(ElementTypeGroup.TextNoteType) if plans else None
    if plans and (type_id is None or type_id==ElementId.InvalidElementId):
        raise ValueError(tr(u'Для подписей замечаний нужен тип текстового примечания.',u'A text note type is required for remark labels.'))
    solid=next((p.Id for p in FilteredElementCollector(doc).OfClass(FillPatternElement)
                if p.GetFillPattern().IsSolidFill),None) if plans else None
    working=copy.deepcopy(registry)
    saved=dict(signature=signature,notes=[],overrides=[],
               members={uid:gid for uid,gid in previous.get('members',{}).items() if gid in preserve})
    saved['members'].update({row['uid']:row['remark_group_id'] for row in active})
    with revit.Transaction(tr(u'Пометки групповых замечаний',u'Group remark labels'),doc=doc):
        for uid in previous.get('notes',[]):
            note=doc.GetElement(uid)
            data=store.read(note) if note is not None else {}
            if data and data.get('role')=='opening_remark_note':
                if data.get('remark_group_id') in preserve:saved['notes'].append(uid)
                else:doc.Delete(note.Id)
        for view_uid,element_uid in previous.get('overrides',[]):
            view=doc.GetElement(view_uid);element=doc.GetElement(element_uid)
            if previous.get('members',{}).get(element_uid) in preserve:
                saved['overrides'].append([view_uid,element_uid])
            elif view is not None and element is not None:view.SetElementOverrides(element.Id,OverrideGraphicSettings())
        for view,gid,state,text,pos,ends,elements in plans:
            if isinstance(view,View3D) and not view.IsLocked:view.SaveOrientationAndLock()
            note=TextNote.Create(doc,view.Id,pos,text,type_id)
            store.write(note,dict(schema=1,role='opening_remark_note',project=project,remark_group_id=gid))
            saved['notes'].append(note.UniqueId)
            for end in ends:
                kind=TextNoteLeaderTypes.TNLT_STRAIGHT_L if end.Subtract(pos).DotProduct(view.RightDirection)<0 else TextNoteLeaderTypes.TNLT_STRAIGHT_R
                leader=note.AddLeader(kind)
                leader.End=end
            color=Color(30,100,240) if state=='review' else Color(240,140,40)
            override=OverrideGraphicSettings().SetProjectionLineColor(color).SetCutLineColor(color).SetSurfaceTransparency(0)
            if solid is not None:
                override.SetSurfaceForegroundPatternId(solid).SetSurfaceForegroundPatternColor(color)
                override.SetCutForegroundPatternId(solid).SetCutForegroundPatternColor(color)
            for element in elements:
                view.SetElementOverrides(element.Id,override)
                saved['overrides'].append([view.UniqueId,element.UniqueId])
        working.setdefault('remark_view_states',{})[project]=saved
        store.save_registry(doc,working)
