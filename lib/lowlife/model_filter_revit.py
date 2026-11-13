# -*- coding: utf-8 -*-
"""View-local workset/link visibility. Only call inside Revit API callbacks.

Uses the datum filter's grouping, live element reads and atomic transaction.
No workset loading, link reloads, link-type edits or linked-document edits.
"""
import json
from lowlife import datum_filter_core as core
from lowlife import datum_filter_revit as datums
from lowlife import link_views
from lowlife.model_filter_settings import TITLE
from lowlife.i18n import N_, tr

supported = datums.supported
WORKSETS = N_(u'Рабочие наборы')
LINKS = N_(u'Связанные модели')


def manage(doc):
    from lowlife.workset_manager_dialog import run
    run(doc)


def _workset_item(doc, view, workset, controlled):
    from Autodesk.Revit.DB import WorksetVisibility, WorksetDefaultVisibilitySettings
    source = doc.GetElement(view.ViewTemplateId) if controlled else view
    visibility = source.GetWorksetVisibility(workset.Id)
    if visibility == WorksetVisibility.UseGlobalSetting:
        defaults = WorksetDefaultVisibilitySettings.GetWorksetDefaultVisibilitySettings(doc)
        visible = defaults.IsWorksetVisible(workset.Id)
    else:
        visible = visibility == WorksetVisibility.Visible
    reason = (tr(u'Видимость задаёт шаблон вида.') if controlled else
              tr(u'Рабочий набор закрыт.') if not workset.IsOpen else u'')
    return dict(id=workset.Id, name=workset.Name, kind='workset',
                hidden=not visible or not workset.IsOpen,
                hideable=workset.IsOpen and not controlled, reason=reason)


def snapshot(doc, view, settings):
    from Autodesk.Revit.DB import BuiltInParameter, FilteredElementCollector, RevitLinkInstance
    from lowlife.cable_tray import find_worksets

    worksets = []
    if doc.IsWorkshared:
        controlled = link_views.template_controls(doc, view, BuiltInParameter.VIS_GRAPHICS_WORKSETS)
        worksets = [_workset_item(doc, view, workset, controlled)
                    for workset in find_worksets(doc, u'')]
    links = []
    # Include unloaded instances as disabled rows; loaded_links intentionally omits them.
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        loaded = link.GetLinkDocument() is not None
        links.append(dict(id=link.Id, name=link_views.safe_name(link), kind='link',
                          hidden=link.IsHidden(view) or not loaded,
                          hideable=loaded and link.CanBeHidden(view),
                          reason=u'' if loaded else tr(u'Связанная модель не загружена.')))
    groups = []
    unmatched = 0
    for kind, section, items, mask in (
            ('workset', WORKSETS, worksets, settings['workset_mask']),
            ('link', LINKS, links, settings['link_mask'])):
        rows, missed = core.group_datums(items, mask)
        for row in rows:
            row['section'] = section
            # Keep identical names in the two sections independent, in either language.
            row['visibility_key'] = kind + u':' + json.dumps(row['key'], ensure_ascii=False)
        groups.extend(rows)
        unmatched += missed
    caption = tr(u'Рабочие наборы: {0}. Связанные модели: {1}.').format(
        settings['workset_mask'], settings['link_mask'])
    return groups, unmatched, caption, False


def apply_visibility(doc, view, items, show):
    return apply_visibility_map(doc, view, [(items, show)])


def apply_visibility_map(doc, view, changes):
    """Re-read state after Undo/deletion/template changes, then one transaction."""
    from Autodesk.Revit.DB import BuiltInParameter, RevitLinkInstance, WorksetKind

    if doc.IsFamilyDocument or not supported(view):
        raise ValueError(tr(u'Выберите план, разрез, фасад или 3D-вид проекта.'))
    controlled = (doc.IsWorkshared and link_views.template_controls(
        doc, view, BuiltInParameter.VIS_GRAPHICS_WORKSETS))
    workset_changes, hide_ids, show_ids = [], [], []
    skipped = 0
    for items, show in changes:
        for item in items:
            if item['kind'] == 'workset':
                try:
                    workset = doc.GetWorksetTable().GetWorkset(item['id'])
                except Exception:
                    workset = None
                if workset is None or workset.Kind != WorksetKind.UserWorkset:
                    skipped += 1
                    continue
                live = _workset_item(doc, view, workset, controlled)
                if not live['hideable']:
                    skipped += 1
                elif core.visibility_changes([live], show):
                    workset_changes.append((workset.Id, show))
            else:
                link = doc.GetElement(item['id'])
                if not isinstance(link, RevitLinkInstance) or link.GetLinkDocument() is None:
                    skipped += 1
                    continue
                live, missed = datums.live_items(doc, view, [item])
                skipped += missed
                ids = core.visibility_changes(live, show)
                (show_ids if show else hide_ids).extend(ids)
    datums.set_visibility(doc, view, hide_ids, show_ids, workset_changes, tr(TITLE))
    return len(workset_changes) + len(hide_ids) + len(show_ids), skipped
