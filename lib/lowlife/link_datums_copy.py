# -*- coding: utf-8 -*-
"""Configure only new datums produced by native Revit Copy/Monitor."""
from lowlife.i18n import tr
from lowlife import link_datums_core as core


def missing_rows(levels, grids):
    """Only unpaired linked datums; renamed/moved pairs must not be duplicated."""
    return [(kind, row) for kind, rows in (("level", levels), ("grid", grids))
            for row in rows if row.status == core.MISSING_IN_MODEL and row.link]


def configure_copies(doc, link, choices, original_ids, tolerance):
    """Apply target settings only to new, natively monitored, matched datums.

    choices: [(kind, Row, host ElementType, WorksetId or None)]. Each item
    commits separately; failures roll back settings, leaving Revit's native copy.
    No Level.Create, Grid.Create, CopyElements or custom monitoring is used.
    """
    from Autodesk.Revit import DB
    from lowlife import link_datums
    from lowlife.fire_boxes import assign_workset
    created, errors = [], []
    levels, grids = link_datums.compare(doc, link, tolerance)
    pairs = dict(((kind, row.link['id_int']), row.model)
                 for kind, rows in (('level', levels), ('grid', grids))
                 for row in rows if row.link and row.model)
    for kind, row, element_type, workset_id in choices:
        key = (kind, row.link['id_int'])
        transaction = None
        try:
            model = pairs.get(key)
            if model is None or model['id_int'] in original_ids:
                raise ValueError(tr(u'Новая копия не найдена.', u'No new copy was found.'))
            element = doc.GetElement(model['id'])
            if not element.IsMonitoringLinkElement() or link.Id not in element.GetMonitoredLinkElementIds():
                raise ValueError(tr(u'Нет штатного мониторинга выбранной связи.',
                                    u'Native monitoring of the selected link is missing.'))
            expected = DB.LevelType if kind == 'level' else DB.GridType
            if not isinstance(element_type, expected):
                raise ValueError(tr(u'Источник или выбранный тип недоступен.',
                                    u'The source or selected type is unavailable.'))
            transaction = DB.Transaction(doc, u'LowLife: Configure monitored datum')
            transaction.Start()
            element.Pinned = False
            replacement = element.ChangeTypeId(element_type.Id)
            if replacement != DB.ElementId.InvalidElementId:
                element = doc.GetElement(replacement)
            assign_workset(element, workset_id)
            element.Pinned = True
            if not element.IsMonitoringLinkElement() or link.Id not in element.GetMonitoredLinkElementIds():
                raise ValueError(tr(u'После смены типа потерян штатный мониторинг.',
                                    u'Native monitoring was lost after changing the type.'))
            if transaction.Commit() != DB.TransactionStatus.Committed:
                raise ValueError(tr(u'Транзакция не завершена.', u'The transaction did not commit.'))
            created.append(element.Id)
            original_ids.add(model['id_int'])
        except Exception as exc:
            if transaction is not None and transaction.GetStatus() == DB.TransactionStatus.Started:
                transaction.RollBack()
            errors.append(u'{}: {}'.format(row.link['name'], exc))
        finally:
            if transaction is not None:
                transaction.Dispose()
    return created, errors
