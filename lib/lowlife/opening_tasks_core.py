# -*- coding: utf-8 -*-
"""Versioned opening tasks. No Revit dependencies; all geometry in host-local mm."""
import copy
import json
import math
import uuid
from lowlife.i18n import tr

VERSION = 1


def guid():
    return str(uuid.uuid4())


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def loads(text):
    value = json.loads(text)
    if not isinstance(value, dict) or value.get('schema') != VERSION:
        raise ValueError(tr(u'Версия формата задания не поддерживается',u'Unsupported opening-task schema'))
    return value


def empty_registry():
    return dict(schema=VERSION, tasks={}, issues=[], receipts={})


def validate_geometry(g):
    if g['kind'] not in ('wall', 'floor'):
        raise ValueError(tr(u'Тип конструкции не поддерживается',u'Unsupported host kind'))
    for key in ('center_mm', 'x_dir', 'size_mm'):
        if len(g[key]) != 3 or not all(not math.isnan(float(v)) and not math.isinf(float(v)) for v in g[key]):
            raise ValueError(tr(u'Некорректная геометрия задания',u'Invalid geometry'))
    if any(float(v) <= 0 for v in g['size_mm']):
        raise ValueError(tr(u'Размеры отверстия должны быть положительными',u'Opening sizes must be positive'))
    x = g['x_dir']
    if abs(x[2]) > 1e-6 or abs(math.hypot(x[0], x[1]) - 1.0) > 1e-6:
        raise ValueError(tr(u'Ось X отверстия должна быть горизонтальным единичным вектором',u'Opening must have a horizontal unit X axis'))
    if not g.get('host_uid') or not g.get('host_model'):
        raise ValueError(tr(u'Нет идентификатора конструкции',u'Missing host identity'))


def geometry_equal(a, b, tolerance_mm=0.1):
    validate_geometry(a)
    validate_geometry(b)
    if any(a[k] != b[k] for k in ('kind', 'host_uid', 'host_model')):
        return False
    return (all(abs(x-y) <= tolerance_mm for key in ('center_mm', 'size_mm') for x, y in zip(a[key], b[key]))
            and all(abs(x-y) < 1e-8 for x, y in zip(a['x_dir'], b['x_dir'])))


def issue(registry, drafts, project, discipline, author, when):
    """Explicit selected scope. Missing tasks NEVER become withdrawn implicitly."""
    if not project.strip() or not discipline.strip():
        raise ValueError(tr(u'Заполните код проекта и дисциплину',u'Project and discipline are required'))
    result = copy.deepcopy(registry)
    seen, changes = set(), []
    issue_id = guid()
    issue_number = len(result['issues']) + 1
    next_task_number = max([r.get('task_number',0) for r in result['tasks'].values()]+[len(result['tasks'])])+1
    for draft in drafts:
        tid = draft['task_id']
        if tid in seen:
            raise ValueError(tr(u'Повторяется GUID задания',u'Duplicate task GUID'))
        seen.add(tid)
        validate_geometry(draft['geometry'])
        old = result['tasks'].get(tid)
        if old and (old['source_model'] != draft['source_model'] or old['project'] != project):
            raise ValueError(tr(u'Конфликт идентификатора задания или кода проекта',u'Task identity or project conflict'))
        if (old and old['status'] == 'issued' and geometry_equal(old['geometry'], draft['geometry'])
                and old['source_uid'] == draft['source_uid'] and old['discipline'] == discipline):
            continue
        record = copy.deepcopy(draft)
        number = old.get('task_number') if old else None
        if not number:
            number = next_task_number
            next_task_number += 1
        record['task_number'] = number
        record.update(schema=VERSION, project=project, discipline=discipline, recipient='KR', status='issued',
                      revision=old['revision']+1 if old else 1, issue_id=issue_id, issue_number=issue_number,
                      created_at=old['created_at'] if old else when, issued_at=when, author=author)
        result['tasks'][tid] = record
        changes.append(record)
    if changes:
        result['issues'].append(dict(id=issue_id, author=author, at=when, action='issue', tasks=copy.deepcopy(changes)))
    return result, changes


def withdraw(registry, task_ids, author, when):
    result, changes = copy.deepcopy(registry), []
    for tid in set(task_ids):
        record = result['tasks'][tid]
        if record['status'] == 'withdrawn':
            continue
        record.update(status='withdrawn', revision=record['revision']+1, issued_at=when, author=author)
        changes.append(copy.deepcopy(record))
    if changes:
        iid = guid()
        for record in changes:
            record['issue_id'] = iid
            result['tasks'][record['task_id']]['issue_id'] = iid
        result['issues'].append(dict(id=iid, author=author, at=when, action='withdraw', tasks=changes))
    return result, changes


def task_key(record):
    return record['source_model'] + '/' + record['task_id']


def incoming_state(record, receipt, opening_exists=True):
    if record['status'] == 'withdrawn':
        return 'withdrawn'
    if not receipt:
        return 'new'
    revisions = receipt.get('revisions', {})
    if revisions.get(task_key(record)) != record['revision']:
        return 'changed'
    if receipt.get('status') == 'accepted' and not opening_exists:
        return 'missing_opening'
    return receipt['status']


def merge_geometry(geometries):
    """Bounding rectangle in one host's frame; no cross-host or rotated merges."""
    first = geometries[0]
    validate_geometry(first)
    axis = first['x_dir']
    yaxis = [-axis[1], axis[0], 0.0]
    axes = [axis, yaxis, [0, 0, 1]]
    ranges = []
    for g in geometries:
        validate_geometry(g)
        if any(g[k] != first[k] for k in ('host_uid', 'host_model', 'kind')):
            raise ValueError(tr(u'Объединять можно только задания одной конструкции',u'Merge requires a single host'))
        if any(abs(a-b)>1e-6 for a,b in zip(g['x_dir'], axis)):
            raise ValueError(tr(u'Для объединения нужна одинаковая ориентация',u'Merge requires matching orientation'))
        c = [sum(p*q for p,q in zip(g['center_mm'], ax)) for ax in axes]
        ranges.append([(v-size/2.0,v+size/2.0) for v,size in zip(c,g['size_mm'])])
    lo = [min(r[i][0] for r in ranges) for i in range(3)]
    hi = [max(r[i][1] for r in ranges) for i in range(3)]
    local = [(a+b)/2.0 for a,b in zip(lo,hi)]
    result = copy.deepcopy(first)
    result['center_mm'] = [sum(local[j]*axes[j][i] for j in range(3)) for i in range(3)]
    result['size_mm'] = [b-a for a,b in zip(lo,hi)]
    return result


def change_kinds(old, new, tolerance_mm=0.1):
    if old is None:
        return ['new']
    changes = []
    a,b = old['geometry'],new['geometry']
    if any(abs(x-y)>tolerance_mm for x,y in zip(a['center_mm'],b['center_mm'])):
        changes.append('moved')
    if any(abs(x-y)>tolerance_mm for x,y in zip(a['size_mm'],b['size_mm'])):
        changes.append('resized')
    if any(abs(x-y)>1e-8 for x,y in zip(a['x_dir'],b['x_dir'])):
        changes.append('rotated')
    if any(a[k]!=b[k] for k in ('host_uid','host_model','kind')):
        changes.append('rehosted')
    if old['status']=='withdrawn' and new['status']=='issued':
        changes.append('reissued')
    return changes
