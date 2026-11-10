# -*- coding: utf-8 -*-
"""On-demand check of final task envelopes against neighboring linked walls."""
try:
    unicode
except NameError:
    unicode = str

from System.Collections.Generic import List
from Autodesk.Revit.DB import (BooleanOperationsUtils, BooleanOperationsType,
    BoundingBoxIntersectsFilter, BuiltInCategory, CurveLoop, ElementId,
    FilteredElementCollector, GeometryCreationUtilities, Line, Options, XYZ, FamilyInstance)
from pyrevit import forms, script
from lowlife.i18n import tr
from lowlife import opening_tasks_revit as api, tray_boxes as boxes, select_list
from lowlife.route_preview import zoom_to_fit_points


def envelope_solid(g):
    """Logical sized box, independent of symbolic family lines and nested geometry."""
    center=boxes._xyz([boxes.ft(v) for v in g['center_mm']])
    x=boxes._xyz(g['x_dir'])
    y=XYZ(-x.Y,x.X,0)
    w,d,h=[boxes.ft(v) for v in g['size_mm']]
    base=center.Subtract(XYZ(0,0,h/2.0))
    points=[base.Add(x.Multiply(a*w/2.0)).Add(y.Multiply(b*d/2.0))
            for a,b in [(-1,-1),(1,-1),(1,1),(-1,1)]]
    loop=CurveLoop()
    for i in range(4):
        loop.Append(Line.CreateBound(points[i],points[(i+1)%4]))
    return GeometryCreationUtilities.CreateExtrusionGeometry(List[CurveLoop]([loop]),XYZ.BasisZ,h)


def check(doc, elements):
    """Return [(box, link, [walls])], [(box, error)]. No model writes."""
    matches,errors=[],[]
    options=Options()
    solids={}
    for inst in elements:
        body=None
        try:
            data=api.metadata(inst)
            if not data or data.get('owner_uid')!=inst.UniqueId:
                continue
            link=doc.GetElement(data['host_link_uid'])
            linked=link.GetLinkDocument() if link is not None else None
            if linked is None:
                raise ValueError(tr(u'Связь конструкции не загружена.',u'Host link is unloaded.'))
            body=envelope_solid(api.host_geometry(inst,data,link))
            region=BoundingBoxIntersectsFilter(boxes._outline(boxes._box_points(body.GetBoundingBox())))
            walls=[]
            for wall in FilteredElementCollector(linked).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType().WherePasses(region):
                if wall.UniqueId==data['host_uid']:
                    continue
                key=(link.UniqueId,wall.UniqueId)
                if key not in solids:
                    solids[key]=boxes._solids(wall,options)
                if not solids[key]:
                    raise ValueError(tr(u'Не удалось получить тело соседней стены: {}.',u'Cannot obtain solid geometry for neighboring wall: {}.').format(wall.UniqueId))
                for solid in solids[key]:
                    intersection=None
                    try:
                        intersection=BooleanOperationsUtils.ExecuteBooleanOperation(body,solid,BooleanOperationsType.Intersect)
                        if intersection.Volume>boxes.ft(1.0)**3:
                            walls.append(wall)
                            break
                    finally:
                        if intersection is not None:
                            intersection.Dispose()
            if walls:
                matches.append((inst,link,walls))
        except Exception as ex:
            errors.append((inst,unicode(ex)))
        finally:
            if body is not None:
                body.Dispose()
    return matches,errors


def run(uidoc):
    doc=uidoc.Document
    elements=list(FilteredElementCollector(doc).OfClass(FamilyInstance))
    with forms.ProgressBar(title=tr(u'Проверка соседних стен',u'Checking neighboring walls')):
        matches,errors=check(doc,elements)
    out=script.get_output()
    if errors:
        out.print_table([[out.linkify(inst.Id),error] for inst,error in errors],
                        columns=[tr(u'Не проверен бокс',u'Unchecked box'),tr(u'Причина',u'Reason')])
        out.show()
    if not matches:
        forms.alert(tr(u'Боксов, заходящих в соседние стены: 0. Не проверено: {}.',
                       u'Boxes overlapping neighboring walls: 0. Unchecked: {}.').format(len(errors)))
        return
    out.print_table([[out.linkify(inst.Id),link.Name,u', '.join(unicode(boxes._id_int(w.Id)) for w in walls)]
                     for inst,link,walls in matches],
                    columns=[tr(u'Бокс',u'Box'),tr(u'Модель конструкций',u'Structural model'),tr(u'ID соседних стен',u'Neighbor wall IDs')])
    options={u'{} | {} | {}'.format(boxes._id_int(inst.Id),link.Name,
             u', '.join(unicode(boxes._id_int(w.Id)) for w in walls)):inst for inst,link,walls in matches}
    chosen=select_list.SelectFromList.show(sorted(options),
        title=tr(u'Боксы в соседних стенах — выберите для подсветки',u'Boxes overlapping neighboring walls — select to highlight'),multiselect=True)
    if chosen:
        selected=[options[label] for label in chosen]
        uidoc.Selection.SetElementIds(List[ElementId]([inst.Id for inst in selected]))
        uidoc.ShowElements(List[ElementId]([inst.Id for inst in selected]))
        points=[p for inst in selected for p in boxes._box_points(inst.get_BoundingBox(None))]
        zoom_to_fit_points(uidoc,uidoc.ActiveView,points)
