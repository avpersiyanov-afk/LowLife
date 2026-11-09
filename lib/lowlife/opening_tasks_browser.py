# -*- coding: utf-8 -*-
"""Cached browser filtering; no model access and no mutation of issue history."""
from lowlife import text_search

FILTERS = ('status','discipline','level','kind','issue','recipient','result','object_part','remark_number')


def select_rows(rows, filters=None, query='', attention=False):
    filters=filters or {}
    return [row for row in rows
            if all(not filters.get(key) or row.get(key)==filters[key] for key in FILTERS)
            and (not attention or row.get('attention',False))
            and text_search.matches(row.get('search_text',''),query)]


def row_key(record, task_id):
    return (record.get('source_model','local') if record else 'local')+'/'+task_id
