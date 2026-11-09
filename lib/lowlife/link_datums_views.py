# -*- coding: utf-8 -*-
"""Host control views containing selected linked datums for native Copy/Monitor."""
from lowlife.i18n import tr


def _name_filter(doc, view, category, choices):
    """Hide every linked datum whose name is outside the selected rows."""
    from Autodesk.Revit import DB
    from System.Collections.Generic import List
    names = sorted(set(choice[1].link['name'] for choice in choices))
    filters = [DB.ElementParameterFilter(DB.ParameterFilterRuleFactory.CreateNotEqualsRule(
        DB.ElementId(DB.BuiltInParameter.DATUM_TEXT), name)) for name in names]
    rule = filters[0] if len(filters) == 1 else DB.LogicalAndFilter(List[DB.ElementFilter](filters))
    element = DB.ParameterFilterElement.Create(doc, view.Name + u' - outside selection',
                                               List[DB.ElementId]([category]), rule)
    view.AddFilter(element.Id)
    view.SetFilterVisibility(element.Id, False)


def prepare(doc, link, choices):
    """Create one 3D level view and/or one grid plan in an atomic Undo step.

    New views use unique names and do not edit existing views or the linked file.
    Returns [(view, choices_for_view)]; levels precede grids.
    """
    from Autodesk.Revit import DB
    from lowlife import loi_check, level_views
    from lowlife.family_section import unique_name
    from lowlife.link_views import safe_name
    from lowlife.opening_tasks_names import safe_name as clean_name
    if link.GetLinkDocument() is None:
        raise ValueError(tr(u'Связь больше не загружена.', u'Link is no longer loaded.'))
    groups = [(kind, [c for c in choices if c[0] == kind]) for kind in ('level', 'grid')]
    groups = [(kind, selected) for kind, selected in groups if selected]
    if not groups:
        return []
    taken = set(safe_name(v) for v in DB.FilteredElementCollector(doc).OfClass(DB.View))
    output = []
    transaction = DB.Transaction(doc, u'LowLife: Copy/Monitor control views')
    transaction.Start()
    try:
        for kind, selected in groups:
            if kind == 'level':
                vft = loi_check._three_d_type(doc)
                if vft is None:
                    raise ValueError(tr(u'Не найден тип 3D-вида.', u'No 3D view type.'))
                view = DB.View3D.CreateIsometric(doc, vft.Id)
                view.IsSectionBoxActive = False
                caption = tr(u'Недостающие уровни - 3D', u'Missing levels - 3D')
                category = DB.ElementId(DB.BuiltInCategory.OST_Levels)
                host_class = DB.Level
            else:
                levels = level_views.document_levels(doc)
                types = level_views._plan_types(doc)
                vft = types.get(DB.ViewFamily.FloorPlan) or types.get(DB.ViewFamily.StructuralPlan)
                if not levels or vft is None:
                    raise ValueError(tr(u'Для плана осей нужны уровень и тип плана в текущей модели.',
                                        u'A host level and a plan view type are required for the grid plan.'))
                active_level = getattr(doc.ActiveView, 'GenLevel', None)
                level = active_level if active_level is not None else levels[0]
                view = DB.ViewPlan.Create(doc, vft.Id, level.Id)
                view.CropBoxActive = False
                view.CropBoxVisible = False
                caption = tr(u'Недостающие оси - план', u'Missing grids - plan')
                category = DB.ElementId(DB.BuiltInCategory.OST_Grids)
                host_class = DB.Grid
            view.Name = unique_name(clean_name(u'LowLife - {} - {}'.format(caption, safe_name(link)), 180), taken)
            view.ViewTemplateId = DB.ElementId.InvalidElementId
            view.Discipline = DB.ViewDiscipline.Coordination
            view.AreAnnotationCategoriesHidden = False
            loi_check._hide_other_categories(doc, view,
                set([category.IntegerValue, int(DB.BuiltInCategory.OST_RvtLinks)]),
                include_annotations=True)
            view.SetCategoryHidden(category, False)
            # Force source datums to follow our category/name filters, never a linked view.
            graphics = DB.RevitLinkGraphicsSettings()
            graphics.LinkVisibilityType = DB.LinkVisibility.ByHostView
            view.SetLinkOverrides(link.Id, graphics)
            _name_filter(doc, view, category, selected)
            hidden = [el.Id.IntegerValue for el in DB.FilteredElementCollector(doc).OfClass(host_class)]
            hidden.extend(el.Id.IntegerValue for el in DB.FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance)
                          if el.Id != link.Id)
            loi_check._hide_by_filter(doc, view, hidden, view.Name + u' - host elements')
            output.append((view, selected))
        if transaction.Commit() != DB.TransactionStatus.Committed:
            raise ValueError(tr(u'Не удалось создать контрольные виды.', u'Could not create control views.'))
    except Exception:
        if transaction.GetStatus() == DB.TransactionStatus.Started:
            transaction.RollBack()
        raise
    finally:
        transaction.Dispose()
    return output


def activate(uidoc, view, link=None, choices=None):
    """Open the prepared host view and fit the visible source datums."""
    if uidoc.ActiveView.Id != view.Id:
        uidoc.ActiveView = view
    uidoc.RefreshActiveView()
    if link is not None and choices and choices[0][0] == 'grid':
        from Autodesk.Revit import DB
        from lowlife.room_finder import zoom_to_bbox
        transform = link.GetTotalTransform()
        points = []
        for kind, row, element_type, workset in choices:
            grid = link.GetLinkDocument().GetElement(row.link['id'])
            points.extend(transform.OfPoint(p) for p in grid.Curve.Tessellate())
        bounds = (DB.XYZ(min(p.X for p in points), min(p.Y for p in points), min(p.Z for p in points)),
                  DB.XYZ(max(p.X for p in points), max(p.Y for p in points), max(p.Z for p in points)))
        # ZoomToFit includes the whole link's box, even with its contents hidden.
        if zoom_to_bbox(uidoc, view, bounds):
            return
    for ui_view in uidoc.GetOpenUIViews():
        if ui_view.ViewId == view.Id:
            ui_view.ZoomToFit()
            break
