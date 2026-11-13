# -*- coding: utf-8 -*-
"""Ordered workset rules -> detached, testable creation/rename/mapping plan."""
try:
    unicode
except NameError:
    unicode = str

from lowlife.datum_filter_core import compile_mask
from lowlife.link_datums_core import natural_key
from lowlife.name_mask import render_mask
from lowlife.i18n import tr

RULES_KEY = 'workset_rules'
ACTIONS = ('create', 'rename', 'map')


def normalize_rules(rules):
    if not isinstance(rules, list):
        raise ValueError(tr(u'Правила рабочих наборов должны быть списком.'))
    result = []
    for row in rules:
        if not isinstance(row, dict) or row.get('action') not in ACTIONS:
            raise ValueError(tr(u'Неизвестное действие в правиле рабочего набора.'))
        source = unicode(row.get('source') or u'').strip()
        target = unicode(row.get('target') or u'').strip()
        if not target or (row['action'] != 'create' and not source):
            raise ValueError(tr(u'Заполните имя назначения и маску источника для переименования или переноса.'))
        if row['action'] != 'create':
            compile_mask(source)
        result.append(dict(action=row['action'], source=source, target=target))
    return result


def plan(existing_names, rules):
    """Apply rules in order. Existing targets require mapping rather than renaming.

    Source masks reuse the visibility filter syntax. Target {1} = original name,
    {2} = the first captured mask part. No project-specific names are defaults.
    """
    names = dict((name.lower(), name) for name in existing_names)
    operations = []
    for rule in normalize_rules(rules):
        action, source, target = rule['action'], rule['source'], rule['target']
        if action == 'create':
            matches = [None]
        else:
            pattern, labels = compile_mask(source)
            matches = sorted([name for name in names.values() if pattern.match(name)], key=natural_key)
            if not matches:
                raise ValueError(tr(u'Маске «{0}» не соответствует ни один рабочий набор.').format(source))
        for name in matches:
            captured = pattern.match(name).groups() if name is not None else ()
            destination = render_mask(target, {1: name or u'', 2: captured[0] if captured else u''})
            if not destination or any(char in destination for char in u'{}[]|;<>?`~\n\r'):
                raise ValueError(tr(u'Недопустимое имя рабочего набора: «{0}».').format(destination))
            current = names.get(destination.lower())
            if action == 'rename':
                if destination == name:
                    continue
                if current is not None and current != name:
                    raise ValueError(tr(u'Набор «{0}» уже есть. Для объединения используйте перенос элементов.').format(destination))
                operations.append(dict(action='rename', source=name, target=destination))
                del names[name.lower()]
                names[destination.lower()] = destination
            else:
                if current is None:
                    operations.append(dict(action='create', source=u'', target=destination))
                    names[destination.lower()] = destination
                if action == 'map' and name.lower() != destination.lower():
                    operations.append(dict(action='map', source=name, target=names[destination.lower()]))
    return operations
