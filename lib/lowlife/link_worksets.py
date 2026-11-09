# -*- coding: utf-8 -*-
"""Open/close user worksets by reloading top-level links, outside transactions."""
from lowlife.i18n import tr
from lowlife.link_views import safe_name


def restriction(link_type):
    """Reload restrictions that can be explained before changing a link."""
    if link_type.IsNestedLink:
        return tr(u'Вложенная связь: управляйте наборами в родительской модели.',
                  u'Nested link: manage worksets in its parent model.')
    if not link_type.IsNotLoadedIntoMultipleOpenDocuments():
        return tr(u'Связь используется в нескольких открытых проектах. Закройте остальные проекты.',
                  u'The link is used in multiple open projects. Close the other projects.')
    if link_type.HasSaveablePositions():
        return tr(u'Сначала сохраните или отмените изменения общих координат связи.',
                  u'Save or discard the linked shared coordinate changes first.')
    return None


def collect_rows(doc):
    """One row per loaded link type; store IDs/values, never linked API objects."""
    from lowlife.linked_elements import loaded_links
    from lowlife.cable_tray import find_worksets
    rows = {}
    for instance in loaded_links(doc):
        key = u'{}'.format(instance.GetTypeId())
        if key in rows:
            rows[key]['instances'] += 1
            continue
        link_type = doc.GetElement(instance.GetTypeId())
        row = dict(type_id=link_type.Id, name=safe_name(link_type),
                   instances=1, worksets=[], reason=None)
        rows[key] = row
        try:
            linked_doc = instance.GetLinkDocument()
            row['reason'] = restriction(link_type)
            if not linked_doc.IsWorkshared:
                row['reason'] = tr(u'Модель без рабочих наборов.', u'Model has no worksets.')
            else:
                row['worksets'] = [dict(id=w.Id, name=w.Name, opened=bool(w.IsOpen))
                                   for w in find_worksets(linked_doc, u'')]
                row['worksets'].sort(key=lambda w: w['name'].lower())
                if not row['worksets']:
                    row['reason'] = tr(u'Нет пользовательских рабочих наборов.',
                                       u'No user worksets.')
        except Exception as exc:
            row['reason'] = u'{}'.format(exc)
    return sorted(rows.values(), key=lambda row: row['name'].lower())


def source(link_type):
    """Keep the original source: absolute ModelPath or external resource."""
    from Autodesk.Revit import DB
    if link_type.IsExternalFileReference():
        return link_type.GetExternalFileReference().GetAbsolutePath()
    resource_type = DB.ExternalResourceTypes.BuiltInExternalResourceTypes.RevitLink
    reference = link_type.GetExternalResourceReference(resource_type)
    if reference is None:
        raise ValueError(tr(u'Источник связи недоступен.', u'Link source is unavailable.'))
    return reference


def apply(doc, choices, progress=None):
    """Reload changed types once; report partial success, never promise rollback.

    choices: [(row, [open WorksetId, ...])]. Linked documents are invalidated
    by each reload. Only host type IDs and detached values survive between calls.
    """
    from Autodesk.Revit import DB
    from System.Collections.Generic import List
    if doc.IsModifiable or doc.IsReadOnly or doc.IsFamilyDocument:
        raise ValueError(tr(u'Закройте режим редактирования и транзакции перед изменением связей.',
                            u'Exit edit mode and close transactions before changing links.'))
    changed, errors = [], []
    for index, (row, opened) in enumerate(choices):
        if progress:
            progress(index, len(choices))
        initial = set(u'{}'.format(w['id']) for w in row['worksets'] if w['opened'])
        wanted = set(u'{}'.format(w) for w in opened)
        if wanted == initial:
            continue
        config = None
        result = None
        try:
            if row['reason']:
                raise ValueError(row['reason'])
            known = set(u'{}'.format(w['id']) for w in row['worksets'])
            if not wanted.issubset(known):
                raise ValueError(tr(u'Неизвестный рабочий набор.', u'Unknown workset.'))
            link_type = doc.GetElement(row['type_id'])
            if link_type is None or not DB.RevitLinkType.IsLoaded(doc, row['type_id']):
                raise ValueError(tr(u'Связь больше не загружена.', u'Link is no longer loaded.'))
            reason = restriction(link_type)
            if reason:
                raise ValueError(reason)
            original_source = source(link_type)
            config = DB.WorksetConfiguration(DB.WorksetConfigurationOption.CloseAllWorksets)
            if opened:
                config.Open(List[DB.WorksetId](opened))
            # LoadFrom clears Undo and must NOT be wrapped in a transaction/group.
            result = link_type.LoadFrom(original_source, config)
            if result.LoadResult != DB.LinkLoadResultType.LinkLoaded:
                raise ValueError(u'{}'.format(result.LoadResult))
            changed.append(row['name'])
        except Exception as exc:
            errors.append(u'{}: {}'.format(row['name'], exc))
        finally:
            if result is not None:
                result.Dispose()
            if config is not None:
                config.Dispose()
    if progress:
        progress(len(choices), len(choices))
    return changed, errors
