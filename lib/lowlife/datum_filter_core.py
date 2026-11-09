# -*- coding: utf-8 -*-
"""Name masks and view-local datum visibility; importable without Revit."""
import re
from lowlife.link_datums_core import natural_key


def compile_mask(mask):
    """Whole-name glob; {labels} capture grouping parts, * and ? skip text.

    Labels are descriptive only (including Cyrillic); they are not regex names.
    No captures means one row per full name. Unmatched names are never changed.
    """
    mask = (mask or u'*').strip() or u'*'
    parts = []
    labels = []
    index = 0
    while index < len(mask):
        char = mask[index]
        if char == u'{':
            end = mask.find(u'}', index + 1)
            if end < 0:
                raise ValueError('Unclosed mask placeholder')
            label = mask[index + 1:end].strip()
            if not label or u'{' in label or label in labels:
                raise ValueError('Empty or duplicate mask placeholder')
            labels.append(label)
            parts.append(u'(.+?)')
            index = end + 1
            continue
        if char == u'}':
            raise ValueError('Unexpected closing brace')
        parts.append(u'.*?' if char == u'*' else u'.' if char == u'?' else re.escape(char))
        index += 1
    return re.compile(u'^' + u''.join(parts) + u'$', re.IGNORECASE), labels


def group_datums(items, mask):
    pattern, labels = compile_mask(mask)
    groups = {}
    unmatched = 0
    for item in items:
        match = pattern.match(item['name'])
        if not match:
            unmatched += 1
            continue
        key = tuple(part.strip() for part in match.groups()) if labels else (item['name'],)
        groups.setdefault(key, []).append(item)
    result = []
    for key, members in groups.items():
        visible = sum(not item['hidden'] for item in members)
        result.append(dict(key=key, name=u' / '.join(key), items=members,
                           checked=True if visible == len(members) else False if not visible else None))
    return sorted(result, key=lambda row: natural_key(row['name'])), unmatched


def visibility_changes(items, show):
    """Only change explicit per-element hiding, never category/template settings."""
    return [item['id'] for item in items
            if item['hideable'] and bool(item['hidden']) == bool(show)]
