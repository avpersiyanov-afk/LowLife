# -*- coding: utf-8 -*-
"""Thin interactive workflows for VIS and structural opening tasks."""
try:
    unicode
except NameError:
    unicode = str

import traceback
from Autodesk.Revit.DB import FilteredElementCollector, RevitLinkInstance
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import forms, revit, script
from lowlife.i18n import tr
from lowlife import select_list
from lowlife import opening_tasks_core as core
from lowlife import opening_tasks_storage as store
from lowlife import opening_tasks_revit as api
from lowlife import opening_tasks_settings as cfg
from lowlife import opening_tasks_mep as mep
from lowlife import tray_boxes as boxes


def state_label(state):
    return {
        'new':tr(u'Новое',u'New'), 'changed':tr(u'Изменено',u'Changed'),
        'accepted':tr(u'Принято',u'Accepted'), 'rejected':tr(u'Замечания',u'Comments'),
        'withdrawn':tr(u'Отозвано',u'Withdrawn'),
        'missing_opening':tr(u'Отверстие удалено',u'Opening deleted'),
        'opening_modified':tr(u'Отверстие изменено вручную',u'Opening manually modified'),
        'moved':tr(u'Перемещено',u'Moved'), 'resized':tr(u'Изменены размеры',u'Resized'),
        'rotated':tr(u'Повёрнуто',u'Rotated'), 'rehosted':tr(u'Изменена конструкция',u'Host changed'),
        'level':tr(u'Уточнён уровень конструкции',u'Host level corrected'),
        'object_part':tr(u'Назначен номер корпуса',u'Building number assigned'),
        'reissued':tr(u'Повторная выдача после отзыва',u'Reissued after withdrawal'),
    }.get(state,state)


def choose(options, title, multiple=False):
    labels = list(options)
    selected = select_list.SelectFromList.show(labels,title=title,multiselect=multiple,
                                               button_name=tr(u'Выбрать',u'Select'))
    if not selected:
        return [] if multiple else None
    return [options[label] for label in selected] if multiple else options[selected]


def selected_elements(selection_filter=None):
    doc, uidoc = revit.doc, revit.uidoc
    result = [doc.GetElement(eid) for eid in uidoc.Selection.GetElementIds()]
    if selection_filter is not None:
        result=[e for e in result if selection_filter.AllowElement(e)]
    if not result and selection_filter is not None:
        refs=uidoc.Selection.PickObjects(ObjectType.Element,selection_filter,
             tr(u'Выберите прямые лотки, воздуховоды, трубы или кабельные трубы',
                u'Select straight trays, ducts, pipes or conduits'))
        result=[doc.GetElement(r) for r in refs]
    elif not result:
        refs = uidoc.Selection.PickObjects(ObjectType.Element,
                tr(u'Выберите элементы текущей модели',u'Select elements in the current model'))
        result = [doc.GetElement(r) for r in refs]
    return result


def report_errors(errors):
    if not errors:
        return
    out = script.get_output()
    out.print_md(tr(u'## Пропуски и ошибки',u'## Skips and errors'))
    out.print_table([[out.linkify(eid),unicode(error)] for eid,error in errors],
                    columns=[tr(u'Элемент',u'Element'),tr(u'Причина',u'Reason')])
    out.show()


def report_placement_result(created,errors):
    report_errors(errors)
    details=u'\n'.join(u'ID {}: {}'.format(boxes._id_int(eid),error) for eid,error in errors)
    message=tr(u'Создано/обновлено: {}. Пропусков/ошибок: {}. Боксы ещё не выданы.',
               u'Created/updated: {}. Skips/errors: {}. Boxes are not issued yet.').format(created,len(errors))
    if errors:
        message+=tr(u'\nПричины: раскройте подробности этого сообщения. Ссылки на элементы — в окне вывода.',
                    u'\nReasons: expand this message for details. Element links are in the output window.')
    forms.alert(message,expanded=details or None)


def place(settings):
    from lowlife import opening_tasks_parts as parts
    parts.require_choice(settings['opening_project'],settings.get('opening_object_part',''))
    doc = revit.doc
    raw = selected_elements(mep.RouteSelectionFilter(settings))
    routes, errors = [], []
    for el in raw:
        try:
            routes.append(mep.Route(el))
        except Exception as ex:
            errors.append((el.Id,unicode(ex)))
    report_errors(errors)
    if not routes:
        return
    links = {u'{} — {}'.format(link.Name,boxes._id_int(link.Id)):link
             for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance)
             if link.GetLinkDocument() is not None}
    if not links:
        raise ValueError(tr(u'Нет загруженной связи получателя {}.',u'No loaded link for recipient {}.').format(settings.get('opening_recipient','KR')))
    link = choose(links,tr(u'Модель-получатель: {}',u'Target model: {}').format(settings.get('opening_recipient','KR')))
    if link is None:
        return
    types = boxes.find_box_types(doc,settings)
    if not types:
        raise ValueError(tr(u'Нет подходящего семейства бокса. Проверьте настройки.',
                            u'No matching box family. Check settings.'))
    symbol = types[0][1] if len(types)==1 else choose(dict(types),tr(u'Тип бокса',u'Box type'))
    if symbol is None:
        return
    if not boxes.placement_supported(symbol):
        raise ValueError(tr(u'Нужно семейство без основы или на рабочей плоскости.',
                            u'A level-based or work-plane-based family is required.'))
    worksets = boxes.find_box_worksets(doc,settings)
    workset = None
    if doc.IsWorkshared and settings.get('box_workset_words'):
        if not worksets:
            raise ValueError(tr(u'Рабочий набор боксов не найден.',u'Box workset not found.'))
        workset = worksets[0] if len(worksets)==1 else choose({w.Name:w for w in worksets},tr(u'Рабочий набор',u'Workset'))
        if workset is None:
            return
    with forms.ProgressBar(title=tr(u'Поиск пересечений: {value}/{max_value}',u'Finding crossings: {value}/{max_value}')) as bar:
        with revit.Transaction(tr(u'Боксы заданий ВИС',u'VIS task boxes')):
            entries, errors = api.place(doc,routes,link,symbol,settings,workset,
                                       lambda i,n:bar.update_progress(i,n))
    out = script.get_output()
    if entries:
        out.print_table([[out.linkify(route.Id),u'{:.0f} × {:.0f}'.format(float(boxes.mm(mep.Route(route).Width)),float(boxes.mm(mep.Route(route).Height))),
                      crossing.host_label(),out.linkify(inst.Id)] for route,crossing,inst,box in entries],
                    columns=[tr(u'Источник',u'Source'),tr(u'Сечение, мм',u'Cross-section, mm'),
                             tr(u'Конструкция',u'Host'),tr(u'Бокс',u'Box')])
    report_placement_result(len(entries),errors)


def publish(settings, elements=None):
    from lowlife import opening_tasks_parts as parts
    parts.require_choice(settings['opening_project'],settings.get('opening_object_part',''))
    doc = revit.doc
    target=settings.get('opening_recipient','KR')
    elements = selected_elements() if elements is None else elements
    drafts = api.prepare_drafts(doc,elements,settings)
    registry = store.registry(doc)
    with revit.Transaction(tr(u'Проверить статус выдачи',u'Check issue status')):
        for inst,draft in zip(elements,drafts):
            record = registry['tasks'].get(draft['task_id'])
            api.visible_issue(inst,settings,record,bool(record and record['status']=='issued' and (not core.geometry_equal(record['geometry'],draft['geometry']) or
                record.get('level')!=draft.get('level'))))
        from lowlife.opening_tasks_views import sync_selection_filters
        sync_selection_filters(doc,settings,registry)
    _registry, changes = core.issue(store.registry(doc),drafts,settings['opening_project'],
                                    settings['opening_discipline'],doc.Application.Username,api.now(),settings.get('opening_recipient','KR'))
    if not changes:
        forms.alert(tr(u'Изменений относительно последней выдачи нет.',u'No changes since the last issue.'))
        return
    out = script.get_output()
    old_tasks = store.registry(doc)['tasks']
    out.print_table([[r['task_id'],r['revision'],u', '.join(state_label(k) for k in core.change_kinds(old_tasks.get(r['task_id']),r)),
                      unicode(r['geometry']['center_mm']),u' × '.join(u'{:.0f}'.format(float(v)) for v in r['geometry']['size_mm'])]
                     for r in changes],columns=[tr(u'Задание',u'Task'),tr(u'Ревизия',u'Revision'),tr(u'Изменения',u'Changes'),
                             tr(u'Центр в модели получателя, мм',u'Center in recipient model, mm'),tr(u'Размеры, мм',u'Sizes, mm')])
    if forms.alert(tr(u'Выдать задания получателю {}: {}? Сохраните модель и обновите связь у получателя.',
                      u'Issue tasks to {}: {}? Save the model and reload its link at the recipient.').format(target,len(changes)),yes=True,no=True):
        with revit.Transaction(tr(u'Выдать задания: {}',u'Issue tasks: {}').format(target)):
            api.publish(doc,elements,settings)


def withdraw(settings, task_ids=None):
    registry = store.registry(revit.doc)
    options = {}
    for tid,record in registry['tasks'].items():
        if record['status']=='issued' and record['project']==settings['opening_project']:
            missing = revit.doc.GetElement(record['owner_uid']) is None
            label = u'{} | r{} | {}'.format(tid,record['revision'],
                    tr(u'бокс удалён',u'box deleted') if missing else tr(u'выдано',u'issued'))
            options[label] = tid
    selected = task_ids if task_ids is not None else choose(options,tr(u'Отозвать выданные задания',u'Withdraw issued tasks'),True)
    if selected and forms.alert(tr(u'Зафиксировать отзыв выбранных заданий: {}?',u'Record withdrawal of {} selected tasks?').format(len(selected)),yes=True,no=True):
        with revit.Transaction(tr(u'Отзыв заданий',u'Withdraw tasks')):
            api.retract(revit.doc,selected,settings)


def receipt_state(record, registry, doc, recipient='KR'):
    receipt = core.receipts(registry,recipient).get(core.task_key(record))
    opening=doc.GetElement(receipt['opening_uid']) if receipt and receipt.get('opening_uid') else None
    exists=opening is not None
    if exists and not api.opening_matches(opening,receipt):
        return 'opening_modified'
    return core.incoming_state(record,receipt,exists)


def kr(settings, action=None, selected=None):
    doc = revit.doc
    out = script.get_output()
    if selected is None:
        registry = store.registry(doc)
        for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
            if link.GetLinkDocument() is None:
                script.get_output().print_md(tr(u'Связь не загружена: {}. Её задания не проверены.',
                                               u'Link is unloaded: {}. Its tasks were not checked.').format(link.Name))
        incoming = api.incoming(doc,settings['opening_project'],settings.get('opening_recipient','KR'))
        if not incoming:
            forms.alert(tr(u'Нет выданных заданий для модели получателя {}. Проверьте связи и код проекта.',
                           u'No issued tasks for recipient model {}. Check links and project code.').format(settings.get('opening_recipient','KR')))
            return
        options = {}
        for record,link in incoming:
            g = record['geometry']
            receipt = core.receipts(registry,settings.get('opening_recipient','KR')).get(core.task_key(record))
            state = state_label(receipt_state(record,registry,doc,settings.get('opening_recipient','KR')))
            label = u'{} | {} | {} | r{} | {} | {} | {}'.format(link.Name,record['discipline'],record['task_id'],record['revision'],state,
                        u' × '.join(u'{:.0f}'.format(float(v)) for v in g['size_mm']),record['issued_at'])
            options[label] = record
            inst = link.GetLinkDocument().GetElement(record['owner_uid'])
            out.print_md(u'- {} | {} | {} | {}'.format(record['task_id'],state,
                           out.linkify(link.Id),out.linkify(inst.Id) if inst and link.GetLinkDocument()==doc else record['owner_uid']))
        selected = choose(options,tr(u'Входящие задания {}: выберите задания',u'Incoming {} tasks: select tasks').format(settings.get('opening_recipient','KR')),True)
    if not selected:
        return
    actions = {tr(u'Принять отдельно',u'Accept separately'):'accept',
               tr(u'Объединить и принять',u'Merge and accept'):'merge',
               tr(u'Замечание / отклонить',u'Comment / reject'):'reject',
               tr(u'Удалить отверстия отозванных заданий',u'Remove openings of withdrawn tasks'):'remove',
               tr(u'Показать конструкцию',u'Show host'):'show'}
    if action is None:
        action = choose(actions,tr(u'Действие получателя {}',u'Recipient action: {}').format(settings.get('opening_recipient','KR')))
    if action == 'show':
        host = doc.GetElement(selected[0]['geometry']['host_uid'])
        if host:
            from System.Collections.Generic import List
            from Autodesk.Revit.DB import ElementId
            revit.uidoc.Selection.SetElementIds(List[ElementId]([host.Id]))
            revit.uidoc.ShowElements(host.Id)
        return
    if action in ('reject','reject_group'):
        comment = forms.ask_for_string(prompt=tr(u'Причина / замечание',u'Reason / comment'))
        if comment:
            with revit.Transaction(tr(u'Решение получателя {}',u'Recipient decision: {}').format(settings.get('opening_recipient','KR'))):
                api.reject(doc,selected,settings,comment,grouped=True)
        return
    if action == 'remove':
        if forms.alert(tr(u'Удалить ранее созданные отверстия только для отозванных заданий?',
                          u'Delete previously created openings for withdrawn tasks only?'),yes=True,no=True):
            with revit.Transaction(tr(u'Отработать отзыв',u'Process withdrawal')):
                api.remove_withdrawn(doc,selected,settings)
        return
    if action not in ('accept','merge'):
        return
    if action=='merge':
        core.common_part(selected)
        from lowlife.opening_tasks_merge_preview import show
        if not show(selected):
            return
        g = core.merge_geometry([r['geometry'] for r in selected])
        question = tr(u'Объединить в одно отверстие размером {} мм?',u'Merge into one opening sized {} mm?').format(
                       u' × '.join(u'{:.0f}'.format(float(v)) for v in g['size_mm']))
    else:
        question = tr(u'Создать/обновить отдельные отверстия: {}?',u'Create/update {} separate openings?').format(len(selected))
    question += u'\n' + tr(u'Сдвиг без изменения габарита обновляется с сохранением элемента. Замена с марками/размерами будет остановлена. Продолжить?',
                            u'Translation without size changes preserves the element. Replacement affecting tags/dimensions is blocked. Continue?')
    if not forms.alert(question,yes=True,no=True):
        return
    groups = [selected] if action=='merge' else [[r] for r in selected]
    with revit.Transaction(tr(u'Принять задания {}',u'Accept {} tasks').format(settings.get('opening_recipient','KR'))):
        for group in groups:
            opening = api.accept(doc,group,settings)
            out.print_md(tr(u'Создано отверстие: {}',u'Created opening: {}').format(out.linkify(opening.Id)))


def confirm(settings, task_ids=None):
    results = api.structural_results(revit.doc,settings['opening_project'],settings.get('opening_recipient','KR'))
    options = {u'{} | r{} | {}'.format(task['task_id'],task['revision'],receipt['opening_id']):
               (task,receipt,link) for task,receipt,link in results}
    if not options:
        forms.alert(tr(u'Нет актуальных принятых отверстий получателя {}. Обновите связи.',
                       u'No current accepted openings from recipient {}. Reload links.').format(settings.get('opening_recipient','KR')))
        return
    selected = ([value for value in options.values() if value[0]['task_id'] in task_ids]
                if task_ids is not None else choose(options,tr(u'Подтвердить результат {}',u'Confirm {} results').format(settings.get('opening_recipient','KR')),True))
    if selected and forms.alert(tr(u'Подтвердить отверстия получателя {}: {}?',u'Confirm openings from recipient {}: {}?').format(settings.get('opening_recipient','KR'),len(selected)),yes=True,no=True):
        with revit.Transaction(tr(u'Подтверждение ВИС',u'VIS confirmation')):
            api.confirm_results(revit.doc,selected,settings)


def run(role, config_mode=False, action=None):
    try:
        settings_form = cfg.make(role,revit.doc if role=='VIS' else None)
        if config_mode:
            settings_form.get_settings_interactive()
            return
        settings = cfg.for_document(settings_form.get_settings_silent(),revit.doc)
        from lowlife import opening_tasks_parts as parts
        settings['opening_object_part']=parts.selection(settings['opening_project'],role,store.model_id(revit.doc))
        required = ['opening_project']
        if role=='VIS':
            required += ['opening_discipline','opening_json_param']
        settings_form.require(settings,required)
        if role in ('KR','AR'):
            settings['opening_recipient']=role
            kr(settings, action)
            return
        if action=='place':
            settings_form.require(settings,['box_width_param','box_depth_param','box_height_param','box_host_filter_param'])
            place(settings)
        elif action=='issue':
            settings_form.require(settings,['opening_status_param'])
            publish(settings)

        elif action=='withdraw':
            withdraw(settings)
        elif action=='confirm':
            confirm(settings)
    except OperationCanceledException:
        return
    except Exception:
        forms.alert(tr(u'Операция не завершена. Текущая транзакция отменена.\n\n{}',
                       u'Operation did not complete. The current transaction was rolled back.\n\n{}').format(traceback.format_exc()))


def delete_boxes_from_list(uidoc, rows=None):
    doc=uidoc.Document
    candidates=([doc.GetElement(row['uid']) for row in rows] if rows else
                list(FilteredElementCollector(doc).OfClass(api.FamilyInstance)))
    options={}
    for inst in candidates:
        data=api.metadata(inst) if inst is not None else None
        if data and data.get('owner_uid')==inst.UniqueId:
            options[u'ID {} | {}'.format(boxes._id_int(inst.Id),data['task_id'])]=inst
    if not options:
        forms.alert(tr(u'Нет собственных боксов для удаления.',u'No original task boxes to delete.'))
        return
    selected=choose(options,tr(u'Удалить боксы — выберите из списка',u'Delete boxes — select from the list'),True)
    if not selected:
        return
    details=u', '.join(unicode(boxes._id_int(inst.Id)) for inst in selected)
    if not forms.alert(tr(u'Удалить боксы из модели: {}?\nID: {}\n\nИстория выданных заданий сохранится. Удаление не заменяет отзыв задания. Связанные с боксами марки могут быть удалены Revit.',
                          u'Delete {} boxes from the model?\nIDs: {}\n\nIssued task history remains. Deletion does not withdraw tasks. Revit may delete dependent tags.').format(len(selected),details),yes=True,no=True):
        return
    with revit.Transaction(tr(u'Удалить боксы заданий',u'Delete task boxes')):
        api.delete_boxes(doc,selected)
