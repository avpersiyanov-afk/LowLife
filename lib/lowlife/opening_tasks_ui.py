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
        'reissued':tr(u'Повторная выдача после отзыва',u'Reissued after withdrawal'),
    }.get(state,state)


def choose(options, title, multiple=False):
    labels = list(options)
    selected = select_list.SelectFromList.show(labels,title=title,multiselect=multiple,
                                               button_name=tr(u'Выбрать',u'Select'))
    if not selected:
        return [] if multiple else None
    return [options[label] for label in selected] if multiple else options[selected]


def selected_elements():
    doc, uidoc = revit.doc, revit.uidoc
    result = [doc.GetElement(eid) for eid in uidoc.Selection.GetElementIds()]
    if not result:
        refs = uidoc.Selection.PickObjects(ObjectType.Element,
                tr(u'Выберите элементы текущей модели',u'Select elements in the current model'))
        result = [doc.GetElement(r) for r in refs]
    return result


def report_errors(errors):
    out = script.get_output()
    for eid, error in errors:
        out.print_md(u'- {}: {}'.format(out.linkify(eid),error))


def place(settings):
    doc = revit.doc
    raw = selected_elements()
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
        raise ValueError(tr(u'Нет загруженной связи КР.',u'No loaded structural link.'))
    link = choose(links,tr(u'Модель конструкций КР',u'Structural model'))
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
    out.print_table([[out.linkify(route.Id),u'{:.0f} × {:.0f}'.format(float(boxes.mm(mep.Route(route).Width)),float(boxes.mm(mep.Route(route).Height))),
                      crossing.host_label(),out.linkify(inst.Id)] for route,crossing,inst,box in entries],
                    columns=[tr(u'Источник',u'Source'),tr(u'Сечение, мм',u'Cross-section, mm'),
                             tr(u'Конструкция',u'Host'),tr(u'Бокс',u'Box')])
    report_errors(errors)
    forms.alert(tr(u'Создано/обновлено: {}. Пропусков/ошибок: {}. Боксы ещё не выданы.',
                   u'Created/updated: {}. Skips/errors: {}. Boxes are not issued yet.').format(len(entries),len(errors)))


def publish(settings):
    doc = revit.doc
    elements = selected_elements()
    drafts = api.prepare_drafts(doc,elements,settings)
    _registry, changes = core.issue(store.registry(doc),drafts,settings['opening_project'],
                                    settings['opening_discipline'],doc.Application.Username,api.now())
    if not changes:
        forms.alert(tr(u'Изменений относительно последней выдачи нет.',u'No changes since the last issue.'))
        return
    out = script.get_output()
    old_tasks = store.registry(doc)['tasks']
    out.print_table([[r['task_id'],r['revision'],u', '.join(state_label(k) for k in core.change_kinds(old_tasks.get(r['task_id']),r)),
                      unicode(r['geometry']['center_mm']),u' × '.join(u'{:.0f}'.format(float(v)) for v in r['geometry']['size_mm'])]
                     for r in changes],columns=[tr(u'Задание',u'Task'),tr(u'Ревизия',u'Revision'),tr(u'Изменения',u'Changes'),
                             tr(u'Центр в модели КР, мм',u'Center in KR model, mm'),tr(u'Размеры, мм',u'Sizes, mm')])
    if forms.alert(tr(u'Выдать выбранные задания КР: {}? Получатель увидит выпуск после сохранения модели и обновления связи.',
                      u'Issue {} selected tasks to KR? Save the model and reload its link to deliver the release.').format(len(changes)),yes=True,no=True):
        with revit.Transaction(tr(u'Выдать задания КР',u'Issue tasks to KR')):
            api.publish(doc,elements,settings)


def withdraw(settings):
    registry = store.registry(revit.doc)
    options = {}
    for tid,record in registry['tasks'].items():
        if record['status']=='issued' and record['project']==settings['opening_project']:
            missing = revit.doc.GetElement(record['owner_uid']) is None
            label = u'{} | r{} | {}'.format(tid,record['revision'],
                    tr(u'бокс удалён',u'box deleted') if missing else tr(u'выдано',u'issued'))
            options[label] = tid
    selected = choose(options,tr(u'Отозвать выданные задания',u'Withdraw issued tasks'),True)
    if selected and forms.alert(tr(u'Зафиксировать отзыв выбранных заданий: {}?',u'Record withdrawal of {} selected tasks?').format(len(selected)),yes=True,no=True):
        with revit.Transaction(tr(u'Отзыв заданий',u'Withdraw tasks')):
            api.retract(revit.doc,selected,settings)


def receipt_state(record, registry, doc):
    receipt = registry['receipts'].get(core.task_key(record))
    exists = bool(receipt and receipt.get('opening_uid') and doc.GetElement(receipt['opening_uid']))
    if exists and not api.opening_matches(doc.GetElement(receipt['opening_uid']),receipt):
        return 'opening_modified'
    return core.incoming_state(record,receipt,exists)


def kr(settings):
    doc = revit.doc
    registry = store.registry(doc)
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        if link.GetLinkDocument() is None:
            script.get_output().print_md(tr(u'Связь не загружена: {}. Её задания не проверены.',
                                           u'Link is unloaded: {}. Its tasks were not checked.').format(link.Name))
    incoming = api.incoming(doc,settings['opening_project'])
    if not incoming:
        forms.alert(tr(u'Нет выданных заданий для этой модели КР. Проверьте связи и код проекта.',
                       u'No issued tasks for this KR model. Check links and project code.'))
        return
    out = script.get_output()
    options = {}
    for record,link in incoming:
        g = record['geometry']
        receipt = registry['receipts'].get(core.task_key(record))
        state = state_label(receipt_state(record,registry,doc))
        label = u'{} | {} | {} | r{} | {} | {} | {}'.format(link.Name,record['discipline'],record['task_id'],record['revision'],state,
                    u' × '.join(u'{:.0f}'.format(float(v)) for v in g['size_mm']),record['issued_at'])
        options[label] = record
        inst = link.GetLinkDocument().GetElement(record['owner_uid'])
        out.print_md(u'- {} | {} | {} | {}'.format(record['task_id'],state,
                       out.linkify(link.Id),out.linkify(inst.Id) if inst and link.GetLinkDocument()==doc else record['owner_uid']))
    selected = choose(options,tr(u'Входящие задания КР: выберите задания',u'Incoming KR tasks: select tasks'),True)
    if not selected:
        return
    actions = {tr(u'Принять отдельно',u'Accept separately'):'accept',
               tr(u'Объединить и принять',u'Merge and accept'):'merge',
               tr(u'Замечание / отклонить',u'Comment / reject'):'reject',
               tr(u'Удалить отверстия отозванных заданий',u'Remove openings of withdrawn tasks'):'remove',
               tr(u'Показать конструкцию',u'Show host'):'show'}
    action = choose(actions,tr(u'Действие КР',u'KR action'))
    if action == 'show':
        host = doc.GetElement(selected[0]['geometry']['host_uid'])
        if host:
            from System.Collections.Generic import List
            from Autodesk.Revit.DB import ElementId
            revit.uidoc.Selection.SetElementIds(List[ElementId]([host.Id]))
            revit.uidoc.ShowElements(host.Id)
        return
    if action == 'reject':
        comment = forms.ask_for_string(prompt=tr(u'Причина / замечание',u'Reason / comment'))
        if comment:
            with revit.Transaction(tr(u'Решение КР',u'KR decision')):
                api.reject(doc,selected,settings,comment)
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
        g = core.merge_geometry([r['geometry'] for r in selected])
        question = tr(u'Объединить в одно отверстие размером {} мм?',u'Merge into one opening sized {} mm?').format(
                       u' × '.join(u'{:.0f}'.format(float(v)) for v in g['size_mm']))
    else:
        question = tr(u'Создать/обновить отдельные отверстия: {}?',u'Create/update {} separate openings?').format(len(selected))
    question += u'\n' + tr(u'Ранее принятые отверстия выбранных заданий будут заменены. Продолжить?',
                            u'Previously accepted openings of selected tasks will be replaced. Continue?')
    if not forms.alert(question,yes=True,no=True):
        return
    groups = [selected] if action=='merge' else [[r] for r in selected]
    with revit.Transaction(tr(u'Принять задания КР',u'Accept KR tasks')):
        for group in groups:
            opening = api.accept(doc,group,settings)
            out.print_md(tr(u'Создано отверстие: {}',u'Created opening: {}').format(out.linkify(opening.Id)))


def confirm(settings):
    results = api.structural_results(revit.doc,settings['opening_project'])
    options = {u'{} | r{} | {}'.format(task['task_id'],task['revision'],receipt['opening_id']):
               (task,receipt,link) for task,receipt,link in results}
    if not options:
        forms.alert(tr(u'Нет актуальных принятых отверстий КР для подтверждения. Обновите связи.',
                       u'No current accepted KR openings to confirm. Reload links.'))
        return
    selected = choose(options,tr(u'Подтвердить результат КР',u'Confirm KR results'),True)
    if selected and forms.alert(tr(u'Подтвердить выбранные отверстия КР: {}?',u'Confirm {} selected KR openings?').format(len(selected)),yes=True,no=True):
        with revit.Transaction(tr(u'Подтверждение ВИС',u'VIS confirmation')):
            api.confirm_results(revit.doc,selected,settings)


def run(role, config_mode=False):
    try:
        settings_form = cfg.make(role,revit.doc if role=='VIS' else None)
        if config_mode:
            settings_form.get_settings_interactive()
            return
        settings = settings_form.get_settings_silent()
        required = ['opening_project']
        if role=='VIS':
            required += ['opening_discipline','opening_json_param']
        settings_form.require(settings,required)
        if role=='KR':
            kr(settings)
            return
        action = choose({tr(u'Расставить / обновить боксы',u'Place / update boxes'):'place',
                         tr(u'Выдать выбранные боксы КР',u'Issue selected boxes to KR'):'issue',
                         tr(u'Отозвать задания',u'Withdraw tasks'):'withdraw',
                         tr(u'Подтвердить результат КР',u'Confirm KR results'):'confirm'},
                         tr(u'Задания ВИС',u'VIS tasks'))
        if action=='place':
            settings_form.require(settings,['box_width_param','box_depth_param','box_height_param','box_host_filter_param'])
            place(settings)
        elif action=='issue':
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
