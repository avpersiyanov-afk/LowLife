# -*- coding: utf-8 -*-
"""UGO registry in the model and owned legend content. Caller owns transaction."""
try:
    unicode
except NameError:
    unicode = str

import json
from System import Guid, String
from System.Collections.Generic import List
from Autodesk.Revit.DB import (BuiltInCategory, ElementId, FamilyPlacementType,
    FilteredElementCollector, TextNote, TextNoteType, TextNoteOptions,
    HorizontalTextAlignment, VerticalTextAlignment, View, ViewType, ElementTransformUtils,
    ViewDuplicateOption, XYZ)
from Autodesk.Revit.DB.ExtensibleStorage import Schema, SchemaBuilder, Entity, AccessLevel
from Autodesk.Revit.DB import DataStorage
from lowlife.scs_settings import list_symbols_by_categories, TypeOption
from lowlife.room_explication_core import unique_name
from lowlife.i18n import tr
from lowlife import ugo_core as core

SCHEMA_ID = Guid('5ac27f63-89df-4e3e-94cd-989f8ea596b6')


def _schema():
    value = Schema.Lookup(SCHEMA_ID)
    if value is None:
        builder = SchemaBuilder(SCHEMA_ID)
        builder.SetSchemaName('LowLifeUgoV1')
        builder.SetReadAccessLevel(AccessLevel.Public)
        builder.SetWriteAccessLevel(AccessLevel.Public)
        builder.AddSimpleField('Json', String)
        value = builder.Finish()
    return value


def _read(element):
    entity = element.GetEntity(_schema())
    if not entity.IsValid():
        return None
    data = json.loads(entity.Get[String](_schema().GetField('Json')))
    if data.get('version') != 1:
        raise ValueError(tr(u'Неизвестная версия данных УГО.', u'Unknown UGO data version.'))
    return data


def _write(element, data):
    entity = Entity(_schema())
    entity.Set[String](_schema().GetField('Json'), unicode(json.dumps(dict(data, version=1))))
    element.SetEntity(entity)


def load(doc):
    registries = [el for el in FilteredElementCollector(doc).OfClass(DataStorage)
                  if _read(el) is not None]
    if len(registries) > 1:
        raise ValueError(tr(u'В модели несколько реестров УГО.', u'Multiple UGO registries in model.'))
    return (_read(registries[0]) if registries else
            dict(version=1, rows={}, groups=[], template_uid='', text_uid='',
                 scale=1, row_mm=12.0, gap_mm=8.0, width_mm=90.0))


def save(doc, data):
    registries = [el for el in FilteredElementCollector(doc).OfClass(DataStorage)
                  if _read(el) is not None]
    if len(registries) > 1:
        raise ValueError(tr(u'В модели несколько реестров УГО.', u'Multiple UGO registries in model.'))
    _write(registries[0] if registries else DataStorage.Create(doc), data)


def catalog(doc, data):
    pairs = [(s.UniqueId, TypeOption(s).name) for s in
             list_symbols_by_categories(doc, [BuiltInCategory.OST_DetailComponents])]
    return core.merge_catalog(sorted(pairs, key=lambda p: p[1].lower()), data['rows'])


def legends(doc):
    return sorted([v for v in FilteredElementCollector(doc).OfClass(View)
                   if not v.IsTemplate and v.ViewType == ViewType.Legend], key=lambda v: v.Name)


def _owned(element, view, group_id):
    if element is None or element.OwnerViewId != view.Id:
        return False
    mark = _read(element)
    return bool(mark and mark.get('group_id') == group_id and
                mark.get('view_uid') == view.UniqueId and mark.get('role') == 'item')


def build(doc, data, group, rows):
    """Validate before deleting, duplicate a blank legend, replace only owned items."""
    if not rows:
        raise ValueError(tr(u'Выбранный список пуст.', u'The selected list is empty.'))
    for row in rows:
        symbol = doc.GetElement(row['uid'])
        if symbol is None:
            raise ValueError(tr(u'Тип элемента узла удалён: {}', u'Detail type was deleted: {}').format(row['name']))
        if symbol.Family.FamilyPlacementType != FamilyPlacementType.ViewBased:
            raise ValueError(tr(u'Нужен точечный элемент узла: {}', u'A point-based detail item is required: {}').format(row['name']))
        if not row['label'].strip():
            raise ValueError(tr(u'Заполните подпись: {}', u'Enter a label: {}').format(row['name']))
    text_type = doc.GetElement(data.get('text_uid', '')) if data.get('text_uid') else None
    if not isinstance(text_type, TextNoteType):
        raise ValueError(tr(u'Выберите тип текста.', u'Select a text type.'))
    view = doc.GetElement(group['view_uid']) if group.get('view_uid') else None
    if view is not None:
        mark = _read(view)
        if (view.ViewType != ViewType.Legend or not mark or
                mark.get('group_id') != group['id'] or mark.get('role') != 'legend'):
            raise ValueError(tr(u'Легенда списка не принадлежит кнопке УГО.', u'The list legend is not owned by UGO.'))
        view.Name = unique_name(core.legend_name(group), [v.Name for v in
            FilteredElementCollector(doc).OfClass(View) if v.Id != view.Id])
    else:
        template = doc.GetElement(data.get('template_uid', '')) if data.get('template_uid') else None
        if template is None or template.ViewType != ViewType.Legend:
            raise ValueError(tr(u'Выберите пустую легенду-образец.', u'Select an empty source legend.'))
        if (list(FilteredElementCollector(doc, template.Id).OfCategory(BuiltInCategory.OST_DetailComponents).WhereElementIsNotElementType())
                or list(FilteredElementCollector(doc, template.Id).OfClass(TextNote))):
            raise ValueError(tr(u'В легенде-образце не должно быть элементов узлов и текстов.',
                                u'The source legend must contain no detail items or text notes.'))
        view = doc.GetElement(template.Duplicate(ViewDuplicateOption.WithDetailing))
        view.Name = unique_name(core.legend_name(group), [v.Name for v in FilteredElementCollector(doc).OfClass(View)])
        group['view_uid'] = view.UniqueId
        _write(view, dict(role='legend', group_id=group['id']))
    view.Scale = int(data['scale'])
    # Only UIDs registered on this list, with matching ownership on the element.
    ids = List[ElementId]()
    for uid in group.get('items', []):
        element = doc.GetElement(uid)
        if _owned(element, view, group['id']):
            ids.Add(element.Id)
    if ids.Count:
        deleted = doc.Delete(ids)
        if any(element_id not in ids for element_id in deleted):
            # Caller rolls the transaction back; never remove manual dependents.
            raise ValueError(tr(u'К элементам УГО привязаны другие элементы. Уберите зависимости перед обновлением.',
                                u'Other elements depend on the UGO items. Remove those dependencies before updating.'))
    group['items'] = []
    factor = view.Scale / 304.8
    placed = []
    half_width = 0.0
    for row in rows:
        symbol = doc.GetElement(row['uid'])
        if not symbol.IsActive:
            symbol.Activate()
            doc.Regenerate()
        item = doc.Create.NewFamilyInstance(XYZ.Zero, symbol, view)
        doc.Regenerate()
        box = item.get_BoundingBox(view)
        if box is None:
            raise ValueError(tr(u'Не удалось определить габарит: {}', u'Could not measure detail item: {}').format(row['name']))
        half_width = max(half_width, (box.Max.X - box.Min.X) / 2.0)
        placed.append((row, item, box))
    y = 0.0
    for row, item, box in placed:
        # Normalize each symbol's top edge so the next row cannot overlap it.
        ElementTransformUtils.MoveElement(doc, item.Id,
            XYZ(-(box.Min.X + box.Max.X) / 2.0, y - box.Max.Y, 0))
        height = box.Max.Y - box.Min.Y
        options = TextNoteOptions(text_type.Id)
        options.HorizontalAlignment = HorizontalTextAlignment.Left
        options.VerticalAlignment = VerticalTextAlignment.Top
        note = TextNote.Create(doc, view.Id, XYZ(half_width + data['gap_mm'] * factor, y, 0),
                               data['width_mm'] * factor, row['label'], options)
        doc.Regenerate()
        note_box = note.get_BoundingBox(view)
        top = max(y, note_box.Max.Y if note_box else y)
        bottom = min(y - height, note_box.Min.Y if note_box else y)
        y -= max(data['row_mm'] * factor, top - bottom + 2 * factor)
        for element in (item, note):
            _write(element, dict(role='item', group_id=group['id'], view_uid=view.UniqueId))
            group['items'].append(element.UniqueId)
    return view
