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


def live_items(doc, view, items):
    """Актуальное состояние элементов: undo, ручное скрытие, удаление."""
    live = []
    skipped = 0
    for item in items:
        element = doc.GetElement(item['id'])
        if element is None or not element.CanBeHidden(view):
            skipped += 1
            continue
        live.append(dict(id=element.Id, hidden=element.IsHidden(view), hideable=True))
    return live, skipped


def set_visibility(doc, view, hide_ids, show_ids, workset_changes=None, title=None):
    """Одна транзакция скрытия/показа; пустые списки не пишутся."""
    from Autodesk.Revit.DB import ElementId, Transaction, TransactionStatus
    from System.Collections.Generic import List

    if not hide_ids and not show_ids and not workset_changes:
        return
    tx = Transaction(doc, title or tr(u'Фильтр осей и уровней'))
    tx.Start()
    try:
        if workset_changes:
            from Autodesk.Revit.DB import WorksetVisibility
            for workset_id, show in workset_changes:
                view.SetWorksetVisibility(
                    workset_id, WorksetVisibility.Visible if show else WorksetVisibility.Hidden)
        if hide_ids:
            view.HideElements(List[ElementId](hide_ids))
        if show_ids:
            view.UnhideElements(List[ElementId](show_ids))
        if tx.Commit() != TransactionStatus.Committed:
            raise RuntimeError(tr(u'Изменения видимости не сохранены.'))
    except Exception:
        if tx.GetStatus() == TransactionStatus.Started:
            tx.RollBack()
        raise
    finally:
        tx.Dispose()


def apply_visibility(doc, view, items, show):
    # Re-read live state: undo, manual hide and deletion may follow the snapshot.
    live, skipped = live_items(doc, view, items)
    ids = core.visibility_changes(live, show)
    if ids:
        if show:
            set_visibility(doc, view, [], ids)
        else:
            set_visibility(doc, view, ids, [])
    return len(ids), skipped


def apply_visibility_map(doc, view, changes):
    """Применить сохранённую группу: [(items, show), ...] за одну транзакцию."""
    hide_ids = []
    show_ids = []
    skipped = 0
    for items, show in changes:
        live, missed = live_items(doc, view, items)
        skipped += missed
        ids = core.visibility_changes(live, show)
        if show:
            show_ids.extend(ids)
        else:
            hide_ids.extend(ids)
    set_visibility(doc, view, hide_ids, show_ids)
    return len(hide_ids) + len(show_ids), skipped
