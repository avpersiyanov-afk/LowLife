# -*- coding: utf-8 -*-
"""Project UGO lists; pure decisions, independent of Revit and WPF."""
try:
    unicode
except NameError:
    unicode = str

from lowlife.level_views_core import clean_view_name
from lowlife.i18n import tr
from lowlife.slab_marks_core import split_words


def tokens(text):
    """Comma/semicolon separated memberships, unique, preserving spelling."""
    return split_words(text, preserve_case=True)


def selected_rows(rows, group):
    """Explicit list membership OR intersection with the list's systems."""
    systems = set(tokens(group.get('systems')))
    return [row for row in rows if group['name'] in tokens(row.get('groups'))
            or systems.intersection(tokens(row.get('systems')))]


def validate(rows, groups):
    names = [g['name'].strip() for g in groups]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError(tr(u'Имена списков должны быть непустыми и уникальными.',
                            u'List names must be nonempty and unique.'))
    known = set(names)
    for row in rows:
        unknown = set(tokens(row.get('groups'))) - known
        if unknown:
            raise ValueError(tr(u'Неизвестные списки: {}', u'Unknown lists: {}').format(
                u', '.join(sorted(unknown))))


def legend_name(group):
    return clean_view_name(u'УГО - ' + group['name'])


def rename_group(rows, old, new):
    """Rename explicit memberships together with a list (identity stays stable)."""
    for row in rows:
        row['groups'] = u', '.join(new if name == old else name
                                  for name in tokens(row.get('groups')))


def merge_catalog(catalog, saved):
    """Keep custom labels, including blanks; retain missing types in saved data."""
    result = []
    present = set()
    for uid, name in catalog:
        present.add(uid)
        row = dict(saved.get(uid, {}))
        row.update(uid=uid, name=name, available=True)
        row.setdefault('label', name)
        row.setdefault('systems', u'')
        row.setdefault('groups', u'')
        result.append(row)
    for uid in sorted(set(saved) - present):
        row = dict(saved[uid], uid=uid, available=False)
        row.setdefault('name', uid)
        row.setdefault('label', row['name'])
        row.setdefault('systems', u'')
        row.setdefault('groups', u'')
        result.append(row)
    return result
