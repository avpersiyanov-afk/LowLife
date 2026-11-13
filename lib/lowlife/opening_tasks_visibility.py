# -*- coding: utf-8 -*-
"""Visibility for owned opening control views; called inside a transaction."""
from System.Collections.Generic import List
from Autodesk.Revit.DB import (BuiltInCategory, DisplayStyle, ElementId, ElementMulticategoryFilter,
    FilteredElementCollector, RevitLinkInstance, TemporaryViewMode, View,
    BoundingBoxIntersectsFilter, Outline)
from lowlife.loi_check import _hide_by_filter, _hide_other_categories, _keep_with_nested
from lowlife import tray_boxes as boxes

STRUCTURES = ('OST_Walls','OST_Floors','OST_StructuralColumns',
              'OST_StructuralFraming','OST_StructuralFoundation','OST_Roofs')
STRUCTURE_TRANSPARENCY = 70


def structural_categories():
    return set(int(getattr(BuiltInCategory,n)) for n in STRUCTURES)


def transparent_structures(doc, view, links=None):
    """Fade only structural context, preserving other graphic overrides."""
    for cid in structural_categories():
        category=ElementId(cid)
        if view.CanCategoryBeHidden(category):
            overrides=view.GetCategoryOverrides(category)
            overrides.SetSurfaceTransparency(STRUCTURE_TRANSPARENCY)
            view.SetCategoryOverrides(category,overrides)
    if links is None:
        links=FilteredElementCollector(doc).OfClass(RevitLinkInstance)
    for link in links:
        overrides=view.GetElementOverrides(link.Id)
        overrides.SetSurfaceTransparency(STRUCTURE_TRANSPARENCY)
        view.SetElementOverrides(link.Id,overrides)


def configure(doc, view, elements, structures=False, cache=None):
    """Only supplied boxes in 3D; structures plus supplied openings on plans."""
    view.ViewTemplateId=ElementId.InvalidElementId
    view.DisplayStyle=DisplayStyle.ShadingWithEdges
    keep=_keep_with_nested(doc,set(boxes._id_int(e.Id) for e in elements))
    allowed=set(boxes._id_int(e.Category.Id) for e in elements if e.Category is not None)
    structural=structural_categories() if structures else set()
    allowed.update(structural)
    if structures:
        allowed.add(int(BuiltInCategory.OST_RvtLinks))
    # Keep generated remark labels; hide grids, levels, sections and scope boxes.
    visible=allowed | set([int(BuiltInCategory.OST_TextNotes)])
    _hide_other_categories(doc,view,visible,include_annotations=True)
    cache=cache if cache is not None else {}
    if structures:
        if "links" not in cache:
            cache["links"]=list(FilteredElementCollector(doc).OfClass(RevitLinkInstance))
        transparent_structures(doc,view,cache["links"])
    scoped=allowed-structural-set([int(BuiltInCategory.OST_RvtLinks)])
    key=tuple(sorted(scoped))
    if key not in cache:
        cache[key]=list(FilteredElementCollector(doc).WherePasses(
            ElementMulticategoryFilter(List[ElementId]([ElementId(cid) for cid in scoped]))).WhereElementIsNotElementType()) if scoped else []
    others=[]
    for el in cache[key]:
        # Views are in the collector too; CanBeHidden alone does not exclude them.
        if isinstance(el,View) or el.Id==view.Id or el.Category is None:
            continue
        category=boxes._id_int(el.Category.Id)
        if category not in allowed or category in structural or category==int(BuiltInCategory.OST_RvtLinks):
            continue
        if boxes._id_int(el.Id) not in keep and el.CanBeHidden(view):
            others.append(boxes._id_int(el.Id))
    _hide_by_filter(doc,view,others,'LowLife opening isolation '+view.UniqueId)


def isolate_preview(doc, view, elements, crop):
    """Hide unrelated local elements only within the active section box."""
    keep=_keep_with_nested(doc,set(boxes._id_int(e.Id) for e in elements))
    shown=[]
    for eid in keep:
        if eid==boxes._id_int(view.Id):
            continue
        element=doc.GetElement(ElementId(eid))
        if element is not None and element.IsHidden(view):
            shown.append(element.Id)
    if shown:
        view.UnhideElements(List[ElementId](shown))
    if view.IsTemporaryHideIsolateActive():
        view.DisableTemporaryViewMode(TemporaryViewMode.TemporaryHideIsolate)
    # The section box clips everything outside this region. A native bounding
    # filter avoids permanent-isolation conversion across the whole document.
    region=BoundingBoxIntersectsFilter(Outline(crop.Min,crop.Max))
    others=[]
    for element in FilteredElementCollector(doc).WherePasses(region).WhereElementIsNotElementType():
        if isinstance(element,View) or element.Id==view.Id or element.Category is None:
            continue
        if boxes._id_int(element.Id) not in keep and element.CanBeHidden(view):
            others.append(boxes._id_int(element.Id))
    _hide_by_filter(doc,view,others,'LowLife box preview isolation '+view.UniqueId)
