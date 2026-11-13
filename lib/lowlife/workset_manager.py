# -*- coding: utf-8 -*-
"""Prepare, validate and atomically execute workset management rules."""
from lowlife import workset_manager_core as core
from lowlife.i18n import tr


def available(doc):
    if doc.IsFamilyDocument or not doc.IsWorkshared:
        raise ValueError(tr(u'В проекте не включена совместная работа — рабочие наборы недоступны.'))
    if doc.IsReadOnly or doc.IsModifiable:
        raise ValueError(tr(u'Завершите редактирование и откройте доступную для записи модель.'))


def prepare(doc, rules):
    """Simulate rule order, including chained transfers, without changing Revit."""
    from Autodesk.Revit import DB
    from lowlife.cable_tray import find_worksets

    available(doc)
    worksets = dict((w.Name, w) for w in find_worksets(doc, u''))
    initial = sorted((name, u'{0}'.format(w.Id), bool(w.IsOpen)) for name, w in worksets.items())
    original_names = set(name.lower() for name in worksets)
    operations = core.plan(list(worksets), rules)
    elements = {}
    for op in operations:
        if (op['action'] in ('create', 'rename')
                and op['target'].lower() not in original_names
                and not DB.WorksetTable.IsWorksetNameUnique(doc, op['target'])):
            raise ValueError(tr(u'Имя рабочего набора уже занято: «{0}».').format(op['target']))
        if op['action'] == 'create':
            elements[op['target']] = []
            worksets[op['target']] = None
        elif op['action'] == 'rename':
            old = op['source']
            if worksets.get(old) is not None and not worksets[old].IsOpen:
                raise ValueError(tr(u'Рабочий набор закрыт.'))
            worksets[op['target']] = worksets.pop(old, None)
            if old in elements:
                elements[op['target']] = elements.pop(old)
        else:
            for name in (op['source'], op['target']):
                workset = worksets.get(name)
                if workset is not None and not workset.IsOpen:
                    raise ValueError(tr(u'Рабочий набор закрыт.'))
                if name not in elements:
                    elements[name] = list(DB.FilteredElementCollector(doc).WherePasses(
                        DB.ElementWorksetFilter(workset.Id)).WhereElementIsNotElementType())
            op['elements'] = list(elements[op['source']])
            for element in op['elements']:
                param = element.get_Parameter(DB.BuiltInParameter.ELEM_PARTITION_PARAM)
                if param is None or param.IsReadOnly:
                    raise ValueError(tr(u'Элемент {0} нельзя перенести в другой рабочий набор.').format(element.Id))
            elements[op['target']].extend(op['elements'])
            elements[op['source']] = []
    return dict(rules=core.normalize_rules(rules), operations=operations, worksets=initial)


def signature(plan):
    return (plan['worksets'], [(op['action'], op['source'], op['target'],
             tuple(sorted(u'{0}'.format(el.Id) for el in op.get('elements', []))))
            for op in plan['operations']])


def apply(doc, preview):
    """Require the preview to remain current. Any failed operation rolls back all."""
    from Autodesk.Revit import DB
    from lowlife.cable_tray import find_worksets
    from lowlife.fire_boxes import assign_workset

    current = prepare(doc, preview['rules'])
    if signature(current) != signature(preview):
        raise ValueError(tr(u'Модель изменилась. Обновите предварительный просмотр.'))
    if not current['operations']:
        return 0
    worksets = dict((w.Name, w.Id) for w in find_worksets(doc, u''))
    tx = DB.Transaction(doc, tr(u'Управление рабочими наборами'))
    try:
        tx.Start()
        for op in current['operations']:
            if op['action'] == 'create':
                worksets[op['target']] = DB.Workset.Create(doc, op['target']).Id
            elif op['action'] == 'rename':
                workset_id = worksets.pop(op['source'])
                DB.WorksetTable.RenameWorkset(doc, workset_id, op['target'])
                worksets[op['target']] = workset_id
            else:
                for element in op['elements']:
                    assign_workset(element, worksets[op['target']])
        if tx.Commit() != DB.TransactionStatus.Committed:
            raise RuntimeError(tr(u'Изменения рабочих наборов не сохранены.'))
    except Exception:
        if tx.GetStatus() == DB.TransactionStatus.Started:
            tx.RollBack()
        raise
    finally:
        tx.Dispose()
    return len(current['operations'])
