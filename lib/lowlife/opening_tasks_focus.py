# -*- coding: utf-8 -*-
"""Dedicated 3D preview. Linked geometry is shown via a structural-only KR view."""
from System.Collections.Generic import List
from Autodesk.Revit.DB import (BoundingBoxXYZ, BuiltInCategory, CategoryType, Color,
    ElementId, FamilyInstance, FillPatternElement, FilteredElementCollector,
    OverrideGraphicSettings, RevitLinkGraphicsSettings, LinkVisibility,
    View, View3D, ViewFamily, ViewFamilyType, XYZ)
from pyrevit import forms, revit
from lowlife.i18n import tr
from lowlife import select_list
from lowlife import opening_tasks_revit as api
from lowlife import opening_tasks_storage as store
from lowlife.opening_tasks_views import unique_name
from lowlife.loi_check import _unhide_all
from lowlife.route_preview import zoom_to_fit_points

from lowlife.opening_tasks_visibility import structural_categories, isolate_preview


def new_view(doc):
    typ = next(t for t in FilteredElementCollector(doc).OfClass(ViewFamilyType) if t.ViewFamily==ViewFamily.ThreeDimensional)
    return View3D.CreateIsometric(doc,typ.Id)


def structures_view(doc):
    view = next((v for v in FilteredElementCollector(doc).OfClass(View3D)
                 if not v.IsTemplate and (store.read(v) or {}).get('role')=='structural_preview'),None)
    if view is None:
        view = new_view(doc)
        view.Name = unique_name(doc,u'LowLife | Конструкции для просмотра заданий')
    _unhide_all(doc,view)
    allowed = structural_categories()
    for cat in doc.Settings.Categories:
        if view.CanCategoryBeHidden(cat.Id):
            view.SetCategoryHidden(cat.Id,api.boxes._id_int(cat.Id) not in allowed)
        if api.boxes._id_int(cat.Id) in allowed:
            view.SetCategoryOverrides(cat.Id,OverrideGraphicSettings().SetSurfaceTransparency(80))
    view.IsSectionBoxActive=False
    store.write(view,dict(schema=1,role='structural_preview'))
    return view


def link_visibility(settings, structure):
    if structure is not None:
        settings.LinkVisibilityType=LinkVisibility.ByLinkView
        settings.LinkedViewId=structure.Id
    else:
        settings.LinkVisibilityType=LinkVisibility.ByHostView
    return settings


def focus(doc, inst):
    data = api.metadata(inst)
    if not data or data.get('owner_uid')!=inst.UniqueId:
        raise ValueError(tr(u'Выберите собственный бокс задания ВИС.',u'Select an original VIS task box.'))
    source = doc.GetElement(data['source_uid'])
    link = doc.GetElement(data['host_link_uid'])
    if source is None or link is None or link.GetLinkDocument() is None:
        raise ValueError(tr(u'Нет исходного элемента или загруженной связи КР.',u'Source element or loaded KR link is missing.'))
    linked = link.GetLinkDocument()
    structure = next((v for v in FilteredElementCollector(linked).OfClass(View3D)
                      if not v.IsTemplate and (store.read(v) or {}).get('role')=='structural_preview'),None)
    registry=store.registry(doc)
    previews=registry.setdefault('box_previews',{})
    view=doc.GetElement(previews[inst.UniqueId]) if inst.UniqueId in previews else None
    if view is not None and not isinstance(view,View3D):
        raise ValueError(tr(u'Сохранённый вид имеет неверный тип.',u'Stored view has an invalid type.'))
    created=view is None
    if created:
        view=new_view(doc)
        view.Name=unique_name(doc,u'LowLife | Бокс '+str(api.boxes._id_int(inst.Id)))
        previews[inst.UniqueId]=view.UniqueId
    isolate_preview(doc,view,[inst,source,link])
    linked_settings=RevitLinkGraphicsSettings()
    link_visibility(linked_settings,structure)
    allowed=structural_categories() | set([api.boxes._id_int(inst.Category.Id),
        api.boxes._id_int(source.Category.Id),int(BuiltInCategory.OST_RvtLinks)])
    for category in doc.Settings.Categories:
        if view.CanCategoryBeHidden(category.Id):
            view.SetCategoryHidden(category.Id,api.boxes._id_int(category.Id) not in allowed)
    view.SetLinkOverrides(link.Id,linked_settings)
    view.SetElementOverrides(link.Id,OverrideGraphicSettings().SetSurfaceTransparency(80))
    blue=Color(30,100,240)
    overrides=OverrideGraphicSettings().SetProjectionLineColor(blue).SetCutLineColor(blue).SetSurfaceTransparency(0)
    solid=next((f.Id for f in FilteredElementCollector(doc).OfClass(FillPatternElement) if f.GetFillPattern().IsSolidFill),None)
    if solid:
        overrides.SetSurfaceForegroundPatternId(solid).SetSurfaceForegroundPatternColor(blue)
        overrides.SetCutForegroundPatternId(solid).SetCutForegroundPatternColor(blue)
    view.SetElementOverrides(inst.Id,overrides)
    bounds=inst.get_BoundingBox(None)
    if bounds is None:
        raise ValueError(tr(u'У бокса нет габарита.',u'Box has no bounding geometry.'))
    margin=api.boxes.ft(700)
    crop=BoundingBoxXYZ()
    crop.Min=bounds.Min.Subtract(XYZ(margin,margin,margin))
    crop.Max=bounds.Max.Add(XYZ(margin,margin,margin))
    view.SetSectionBox(crop)
    view.IsSectionBoxActive=True
    if created:
        store.save_registry(doc,registry)
    return view,crop


def run(structures=False):
    try:
        if structures:
            with revit.Transaction(tr(u'Вид конструкций КР',u'KR structural view')):
                view=structures_view(revit.doc)
            revit.uidoc.ActiveView=view
            forms.alert(tr(u'Вид конструкций подготовлен. Сохраните КР и обновите связь в ВИС.',
                           u'Structural view prepared. Save KR and reload its link in VIS.'))
            return
        selected=[revit.doc.GetElement(i) for i in revit.uidoc.Selection.GetElementIds()]
        inst=selected[0] if len(selected)==1 and api.metadata(selected[0]) else None
        if inst is None:
            drafts=[e for e in FilteredElementCollector(revit.doc).OfClass(FamilyInstance) if api.metadata(e)]
            options={u'{} | {}'.format(api.boxes._id_int(e.Id),api.metadata(e)['task_id']):e for e in drafts}
            choice=select_list.SelectFromList.show(sorted(options),title=tr(u'Просмотр бокса в 3D',u'Box 3D preview'),multiselect=False)
            if not choice:
                return
            inst=options[choice]
        with revit.Transaction(tr(u'Просмотр бокса',u'Box preview')):
            view,crop=focus(revit.doc,inst)
        revit.uidoc.ActiveView=view
        zoom_to_fit_points(revit.uidoc,view,[crop.Min,crop.Max],min_margin_ft=0.0)
    except Exception as ex:
        forms.alert(tr(u'Не удалось подготовить просмотр: {}',u'Could not prepare preview: {}').format(ex))
