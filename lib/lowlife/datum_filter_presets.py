# -*- coding: utf-8 -*-
"""Пользовательские группы настроек фильтра осей и уровней.

Каждая группа живёт внутри одной модели и хранит: имя, маски осей/уровней
и видимость групп по именам. Хранилище — ключ 'presets' в JSON настроек
кнопки: {ключ модели: {имя группы: {grid_mask, level_mask, visibility}}}.
Модуль чистый — без Revit API.
"""
try:
    unicode
except NameError:
    unicode = str

from lowlife import datum_filter_core as core
from lowlife.link_datums_core import natural_key

PRESETS_KEY = 'presets'
MASK_KEYS = ('grid_mask', 'level_mask')


def document_key(title, path):
    """Ключ модели в хранилище: полный путь файла, иначе имя документа."""
    return (path or title or u'').strip()


def normalize_preset(name, data, mask_keys=MASK_KEYS):
    """Сырые данные группы → словарь с гарантированными ключами."""
    data = data if isinstance(data, dict) else {}
    visibility = data.get('visibility') or {}
    if not isinstance(visibility, dict):
        visibility = {}
    visibility = dict((unicode(key), bool(value))
                      for key, value in visibility.items()
                      if value is not None)
    result = dict(name=unicode(name), visibility=visibility)
    for key in mask_keys:
        result[key] = (unicode(data.get(key) or u'*')).strip() or u'*'
    return result


def list_presets(raw, doc_key, mask_keys=MASK_KEYS):
    """Словарь групп одной модели → список групп по имени."""
    if not isinstance(raw, dict):
        return []
    model = raw.get(doc_key) or {}
    if not isinstance(model, dict):
        return []
    result = [normalize_preset(name, data, mask_keys)
              for name, data in model.items() if name]
    return sorted(result, key=lambda preset: natural_key(preset['name']))


def validate_masks(grid_mask, level_mask):
    """Битые маски → ValueError из compile_mask до записи в файл."""
    core.compile_mask(grid_mask)
    core.compile_mask(level_mask)


def save_preset(raw, doc_key, name, grid_mask, level_mask, visibility, mask_keys=MASK_KEYS):
    """Новый словарь presets с добавленной или обновлённой группой."""
    validate_masks(grid_mask, level_mask)
    data = dict(raw) if isinstance(raw, dict) else {}
    model = dict(data.get(doc_key) or {})
    model[unicode(name)] = dict(
        (key, (unicode(value or u'*')).strip() or u'*')
        for key, value in zip(mask_keys, (grid_mask, level_mask)))
    model[unicode(name)]['visibility'] = dict(visibility or {})
    data[unicode(doc_key)] = model
    return data


def delete_preset(raw, doc_key, name):
    """Новый словарь presets без указанной группы (пустая модель вычищается)."""
    data = dict(raw) if isinstance(raw, dict) else {}
    model = dict(data.get(doc_key) or {})
    model.pop(name, None)
    if model:
        data[unicode(doc_key)] = model
    else:
        data.pop(doc_key, None)
    return data


def visibility_map(groups):
    """Текущие группы панели → {имя группы: True/False/None}."""
    return dict((group.get('visibility_key', group['name']), group['checked']) for group in groups)


def plan_changes(groups, saved_map):
    """Что выставить на виде по сохранённой группе: [(items, show), ...].

    Группы, которых нет в сохранённой карте (и чья видимость там не задана),
    не трогаются; None (смешанное) в карте тоже пропускается. Нужны только
    элементы, чья видимость реально изменится.
    """
    changes = []
    for group in groups:
        target = (saved_map or {}).get(group.get('visibility_key', group['name']))
        if target is None:
            continue
        show = bool(target)
        if core.visibility_changes(group['items'], show):
            changes.append((group['items'], show))
    return changes
