# -*- coding: utf-8 -*-
"""Visibility for owned opening control views; called inside a transaction."""
from Autodesk.Revit.DB import BuiltInCategory, ElementId, FilteredElementCollector, View
from lowlife.loi_check import _hide_by_filter, _hide_other_categories, _keep_with_nested
from lowlife import tray_boxes as boxes

STRUCTURES = ('OST_Walls','OST_Floors','OST_StructuralColumns',
              'OST_StructuralFraming','OST_StructuralFoundation','OST_Roofs')


def structural_categories():
    return set(int(getattr(BuiltInCategory,n)) for n in STRUCTURES)


def configure(doc, view, elements, structures=False):
    """Only supplied boxes in 3D; structures plus supplied openings on plans."""
    view.ViewTemplateId=ElementId.InvalidElementId
    keep=_keep_with_nested(doc,set(boxes._id_int(e.Id) for e in elements))
    allowed=set(boxes._id_int(e.Category.Id) for e in elements if e.Category is not None)
    structural=structural_categories() if structures else set()
    allowed.update(structural)
    if structures:
        allowed.add(int(BuiltInCategory.OST_RvtLinks))
    _hide_other_categories(doc,view,allowed,include_annotations=False)
    others=[]
    for el in FilteredElementCollector(doc).WhereElementIsNotElementType():
        # Views are in the collector too; CanBeHidden alone does not exclude them.
        if isinstance(el,View) or el.Id==view.Id or el.Category is None:
            continue
        category=boxes._id_int(el.Category.Id)
        if category not in allowed or category in structural or category==int(BuiltInCategory.OST_RvtLinks):
            continue
        if boxes._id_int(el.Id) not in keep and el.CanBeHidden(view):
            others.append(boxes._id_int(el.Id))
    _hide_by_filter(doc,view,others,'LowLife opening isolation '+view.UniqueId)
