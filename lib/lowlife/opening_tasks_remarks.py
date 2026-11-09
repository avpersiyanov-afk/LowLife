# -*- coding: utf-8 -*-
"""Grouped review decisions. Identity is receiver model + GUID, never display number."""
import copy
from lowlife import opening_tasks_core as core
from lowlife.i18n import tr


def create(registry,records,project,recipient,receiver_model,comment,author,when,windows_user=''):
    if not records or not comment.strip():
        raise ValueError(tr(u'Выберите задания и заполните замечание.',u'Select tasks and enter a comment.'))
    core.check_recipient(records,recipient,project,receiver_model)
    if any(r['status']!='issued' for r in records):
        raise ValueError(tr(u'Замечание назначается только выданным заданиям.',u'Only issued tasks can receive a remark.'))
    keys={core.task_key(r):r for r in records}
    if len(keys)!=len(records):
        raise ValueError(tr(u'В группе повторяются задания.',u'The group contains duplicate tasks.'))
    result=copy.deepcopy(registry)
    receipts=core.receipts(result,recipient)
    for key in keys:
        previous=receipts.get(key,{})
        if previous.get('opening_uid') and not set(previous['revisions']).issubset(set(keys)):
            raise ValueError(tr(u'Выберите все задания существующего объединённого отверстия.',
                                u'Select all tasks belonging to the existing merged opening.'))
    seqkey=project+'/'+recipient
    counters=result.setdefault('remark_sequences',{})
    counters[seqkey]=counters.get(seqkey,0)+1
    group=dict(id=core.guid(),number=u'{}-ЗМ-{:03d}'.format(u'КР' if recipient=='KR' else u'АР',counters[seqkey]),
               sequence=counters[seqkey],project=project,recipient=recipient,receiver_model=receiver_model,
               revisions={key:r['revision'] for key,r in keys.items()},comment=comment.strip(),
               author=author,revit_user=author,windows_user=windows_user,at=when)
    result.setdefault('remark_groups',{})[group['id']]=group
    partitions={}
    for key in keys:
        previous=receipts.get(key,{})
        partitions.setdefault(previous.get('opening_uid') or key,[]).append(key)
    embedded=False
    for members in partitions.values():
        previous=receipts.get(members[0],{})
        receipt=copy.deepcopy(previous) if previous.get('opening_uid') else dict(schema=1)
        receipt.update(status='rejected',project=project,recipient=recipient,
                       revisions={key:keys[key]['revision'] for key in members},
                       object_part=keys[members[0]].get('object_part',''),
                       remark_group_id=group['id'],remark_number=group['number'],
                       comment=u'[{}] {}'.format(group['number'],group['comment']),
                       author=author,revit_user=author,windows_user=windows_user,at=when)
        for key in members:receipts[key]=receipt
        decision=copy.deepcopy(receipt)
        if not embedded:
            decision['remark_group']=copy.deepcopy(group)
            embedded=True
        result.setdefault('decisions' if recipient=='KR' else 'ar_decisions',[]).append(decision)
    return result,group


def latest_by_task(registry,project,recipient):
    groups={g['id']:g for g in registry.get('remark_groups',{}).values()
            if g.get('project')==project and g.get('recipient')==recipient}
    # Embedded copies also support older or externally exchanged registry snapshots.
    decisions=registry.get('decisions' if recipient=='KR' else 'ar_decisions',[])
    for receipt in list(core.receipts(registry,recipient).values())+list(decisions):
        group=receipt.get('remark_group')
        if group and group.get('project')==project and group.get('recipient')==recipient:groups.setdefault(group['id'],group)
    result={}
    for group in sorted(groups.values(),key=lambda g:(g['at'],g.get('sequence',0),g['id'])):
        for key in group['revisions']:result[key]=group
    return result


def state(task,receipt,group):
    if not group:return ''
    key=core.task_key(task)
    current=bool(receipt and receipt.get('revisions',{}).get(key)==task['revision'] and task['revision']>=group['revisions'][key])
    if task['status']=='withdrawn':
        return 'closed' if current and receipt.get('status')=='withdrawn' else 'withdraw_pending'
    if current and receipt.get('status')=='accepted':return 'closed'
    if current and receipt.get('status')=='rejected':return 'correction'
    return 'review' if task['revision']>group['revisions'][key] else 'correction'


def group_state(group,receipts,tasks=None,verified=None):
    """Latest loaded receiver decisions; tasks adds known newer VIS revisions."""
    tasks=tasks or {}
    for key,revision in group['revisions'].items():
        reply=receipts.get(key,{})
        expected=max(tasks[key]['revision'],revision) if key in tasks else revision
        if key in tasks and reply.get('status')!=('withdrawn' if tasks[key]['status']=='withdrawn' else 'accepted'):return 'open'
        if (reply.get('status') not in ('accepted','withdrawn') or
                reply.get('revisions',{}).get(key,0)<expected):return 'open'
        if reply.get('status')=='accepted' and verified is not None and not verified(reply):return 'open'
    return 'closed'
