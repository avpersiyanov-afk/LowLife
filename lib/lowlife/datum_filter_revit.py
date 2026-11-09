# -*- coding: utf-8 -*-
"""Revit adapter. Call only in an API callback, never directly from WPF."""
from lowlife import datum_filter_core as core
from lowlife.i18n import tr


def supported(view):
    from Autodesk.Revit.DB import ViewType
    return (not view.IsTemplate and view.ViewType in (
        ViewType.ThreeD, ViewType.FloorPlan, ViewType.CeilingPlan,
        ViewType.EngineeringPlan, ViewType.AreaPlan, ViewType.Section, ViewType.Elevation))


def snapshot(doc, view, settings):
    from Autodesk.Revit.DB import View3D
    from lowlife import link_datums

    is_3d = isinstance(view, View3D)
    mask = settings['level_mask' if is_3d else 'grid_mask']
    datums = (link_datums.collect_levels(doc, None, 0.0) if is_3d
              else link_datums.collect_grids(doc, None))
    items = []
    for datum in datums:
        element = doc.GetElement(datum['id'])
        items.append(dict(id=datum['id'], name=datum['name'],
                          hidden=element.IsHidden(view), hideable=element.CanBeHidden(view)))
    groups, unmatched = core.group_datums(items, mask)
    return groups, unmatched, mask, is_3d


def apply_visibility(doc, view, items, show):
    from Autodesk.Revit.DB import ElementId, Transaction, TransactionStatus
    from System.Collections.Generic import List
    # Re-read live state: undo, manual hide and deletion may follow the snapshot.
    live = []
    skipped = 0
    for item in items:
        element = doc.GetElement(item['id'])
        if element is None or not element.CanBeHidden(view):
            skipped += 1
            continue
        live.append(dict(id=element.Id, hidden=element.IsHidden(view), hideable=True))
    ids = core.visibility_changes(live, show)
    if ids:
        tx = Transaction(doc, tr(u'Фильтр осей и уровней'))
        tx.Start()
        try:
            if show:
                view.UnhideElements(List[ElementId](ids))
            else:
                view.HideElements(List[ElementId](ids))
            if tx.Commit() != TransactionStatus.Committed:
                raise RuntimeError(tr(u'Изменения видимости не сохранены.'))
        except Exception:
            if tx.GetStatus() == TransactionStatus.Started:
                tx.RollBack()
            raise
        finally:
            tx.Dispose()
    return len(ids), skipped
