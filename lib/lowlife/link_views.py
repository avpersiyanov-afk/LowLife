# -*- coding: utf-8 -*-
"""Display Revit link instances by their own views on multiple host views.

Revit imports are deferred so validation and transaction behaviour can be
tested without Revit. No changes are made to linked documents or link types.
"""

try:
    unicode
except NameError:
    unicode = str

from lowlife.i18n import tr


def _db():
    from Autodesk.Revit import DB
    return DB


def safe_name(element):
    try:
        return _db().Element.Name.GetValue(element)
    except Exception:
        return unicode(element.Id)


def availability(doc, view):
    """Explain unsupported views/templates before showing an editable dialog."""
    db = _db()
    if not hasattr(view, 'SetLinkOverrides') or not hasattr(db, 'RevitLinkGraphicsSettings'):
        return tr(u"Настройка видов связей требует Revit 2024 или новее.",
                  u"Linked view settings require Revit 2024 or later.")
    if view.IsTemplate or not view.AreGraphicsOverridesAllowed():
        return tr(u"На текущем виде нельзя настроить отображение связей.",
                  u"Link display cannot be configured on the current view.")
    template = doc.GetElement(view.ViewTemplateId)
    if template is not None:
        param = db.ElementId(db.BuiltInParameter.VIS_GRAPHICS_RVT_LINKS)
        controlled = template.GetTemplateParameterIds()
        free = template.GetNonControlledTemplateParameterIds()
        if any(p == param for p in controlled) and not any(p == param for p in free):
            return tr(u"Отображение связей задаёт шаблон «{}». Исключите «Связи Revit» из управления шаблоном и повторите команду.",
                      u"Link display is controlled by template “{}”. Exclude “Revit Links” from template control and run the command again.").format(safe_name(template))
    return None


def compatible_views(link_doc, host_view):
    """Conservative candidates: the same view type, never templates."""
    db = _db()
    return sorted([v for v in db.FilteredElementCollector(link_doc).OfClass(db.View)
                   if not v.IsTemplate and v.ViewType == host_view.ViewType],
                  key=lambda v: safe_name(v).lower())


def current_settings(host_view, link):
    """Use instance settings, or inherited type settings if no override exists."""
    settings = host_view.GetLinkOverrides(link.Id)
    if settings is None:
        settings = host_view.GetLinkOverrides(link.GetTypeId())
    return settings


def collect_rows(doc, host_view):
    db = _db()
    rows = []
    for link in db.FilteredElementCollector(doc).OfClass(db.RevitLinkInstance):
        linked_doc = link.GetLinkDocument()
        views = compatible_views(linked_doc, host_view) if linked_doc else []
        reason = None
        if linked_doc is None:
            reason = tr(u"Связь не загружена", u"Link is unloaded")
        elif not views:
            reason = tr(u"Нет видов такого же типа", u"No views of the same type")
        settings = current_settings(host_view, link) if linked_doc else None
        current = tr(u"По основному виду", u"By host view")
        if settings is not None:
            if settings.LinkVisibilityType == db.LinkVisibility.ByLinkView:
                linked_view = linked_doc.GetElement(settings.LinkedViewId)
                current = (safe_name(linked_view) if linked_view else
                           tr(u"Связанный вид недоступен", u"Linked view is unavailable"))
            elif settings.LinkVisibilityType == db.LinkVisibility.Custom:
                current = tr(u"Пользовательские настройки", u"Custom settings")
        rows.append(dict(link=link, name=u"{} [Id {}]".format(safe_name(link), link.Id),
                         views=views, reason=reason, current=current))
    return sorted(rows, key=lambda row: row['name'].lower())


def collect_many_rows(doc, host_views):
    """Show shared settings, or an explicit mixed value across host views."""
    rows = collect_rows(doc, host_views[0])
    for host in host_views[1:]:
        other = dict((unicode(r['link'].Id), r) for r in collect_rows(doc, host))
        for row in rows:
            if row['current'] != other[unicode(row['link'].Id)]['current']:
                row['current'] = tr(u"Разные значения", u"Mixed values")
    return rows


def apply(doc, host_view, choices):
    return apply_many(doc, [host_view], choices)


def apply_many(doc, host_views, choices):
    """Apply (instance, linked view) pairs atomically; one Revit Undo step.

    Read the existing settings so other supported graphics properties survive.
    Revit validates the actual compatibility in SetLinkOverrides. Any rejection
    rolls back the entire batch, including failures during commit.
    """
    db = _db()
    host_views = list(host_views)
    choices = list(choices)
    for host_view in host_views:
        problem = availability(doc, host_view)
        if problem:
            raise ValueError(u"{}: {}".format(safe_name(host_view), problem))
    seen = set()
    for link, linked_view in choices:
        key = unicode(link.Id)
        if key in seen:
            raise ValueError(tr(u"Связь выбрана повторно: {}", u"Link selected twice: {}").format(safe_name(link)))
        seen.add(key)
        linked_doc = link.GetLinkDocument()
        if (linked_doc is None or linked_view.Document != linked_doc
                or linked_view.IsTemplate
                or any(linked_view.ViewType != v.ViewType for v in host_views)):
            raise ValueError(tr(u"Вид не подходит для связи: {}", u"View is incompatible with link: {}").format(safe_name(link)))
    if not choices or not host_views:
        return 0
    transaction = db.Transaction(doc, tr(u"Виды связанных моделей", u"Linked model views"))
    try:
        transaction.Start()
        for host_view in host_views:
            for link, linked_view in choices:
                settings = current_settings(host_view, link)
                if settings is None:
                    settings = db.RevitLinkGraphicsSettings()
                settings.LinkVisibilityType = db.LinkVisibility.ByLinkView
                settings.LinkedViewId = linked_view.Id
                host_view.SetLinkOverrides(link.Id, settings)
        status = transaction.Commit()
        if status != db.TransactionStatus.Committed:
            raise RuntimeError(tr(u"Revit не сохранил настройки связей.", u"Revit did not commit the link settings."))
    except Exception:
        if transaction.GetStatus() == db.TransactionStatus.Started:
            transaction.RollBack()
        raise
    finally:
        transaction.Dispose()
    return len(choices) * len(host_views)
