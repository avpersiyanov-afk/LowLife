# -*- coding: utf-8 -*-
"""Текст задания АР по типам семейств, через общую раскладку оборудования.

Собственная схема хранит только UniqueId источника. Схемы отверстий и
слежения IndependentTag имеют другие контракты и для TextNote не подходят.
"""
from System import Guid, String
from Autodesk.Revit.DB import (
    FamilyInstance, FilteredElementCollector, TextNote, TextNoteType,
    TextNoteLeaderTypes, LeaderAtachement
)
from Autodesk.Revit.DB.ExtensibleStorage import Schema, SchemaBuilder, AccessLevel, Entity

from lowlife import equipment_tags, ar_task_annotations_settings as settings_module
from lowlife.i18n import tr

SCHEMA_ID = Guid('81fa4cc6-b226-432a-a006-93f8c9f55ed4')


def schema():
    value = Schema.Lookup(SCHEMA_ID)
    if value is None:
        builder = SchemaBuilder(SCHEMA_ID)
        builder.SetSchemaName('LowLifeARTaskAnnotationV1')
        builder.SetReadAccessLevel(AccessLevel.Public)
        builder.SetWriteAccessLevel(AccessLevel.Public)
        builder.AddSimpleField('SourceUid', String)
        value = builder.Finish()
    return value


def owned_notes(doc, view):
    """Только примечания нашей схемы, индексированные по источнику."""
    result = {}
    definition = Schema.Lookup(SCHEMA_ID)
    if definition is None:
        return result
    # Скрытая подпись тоже существует: сбор только видимых породил бы дубль.
    for note in FilteredElementCollector(doc).OfClass(TextNote):
        if note.OwnerViewId != view.Id:
            continue
        entity = note.GetEntity(definition)
        if entity.IsValid():
            uid = entity.Get[String](definition.GetField('SourceUid'))
            result.setdefault(uid, []).append(note)
    return result


class TextAnnotation(object):
    """Адаптер TextNote для equipment_tags.run; ошибки отменяют транзакцию."""

    def __init__(self, settings, type_id):
        self.settings = settings
        self.type_id = type_id

    def create(self, doc, view, element, _type_id, point):
        note = TextNote.Create(doc, view.Id, point,
                               settings_module.text_for(element.Symbol, self.settings), self.type_id)
        definition = schema()
        entity = Entity(definition)
        entity.Set[String](definition.GetField('SourceUid'), element.UniqueId)
        note.SetEntity(entity)
        return note

    def prepare(self, note, element):
        note.RemoveLeaders()
        if note.GetTypeId() != self.type_id:
            note.ChangeTypeId(self.type_id)
        note.Text = settings_module.text_for(element.Symbol, self.settings)
        note.LeaderLeftAttachment = LeaderAtachement.MidPoint
        note.LeaderRightAttachment = LeaderAtachement.MidPoint

    def head(self, note):
        return note.Coord

    def place(self, note, frame, head, depth, placement):
        note.Coord = frame.xyz(head, depth)
        center = (placement.tag_rect[0] + placement.tag_rect[2]) * 0.5
        kind = (TextNoteLeaderTypes.TNLT_STRAIGHT_L if placement.attach[0] < center
                else TextNoteLeaderTypes.TNLT_STRAIGHT_R)
        leader = note.AddLeader(kind)
        leader.End = frame.xyz(placement.end, depth)
        leader.Elbow = frame.xyz(placement.elbow, depth)


def run(doc, view, settings):
    """Видимые экземпляры текущей модели; одна аннотация на экземпляр/вид."""
    note_type = next((t for t in FilteredElementCollector(doc).OfClass(TextNoteType)
                      if equipment_tags._safe_name(t) == settings.get('text_type_name')), None)
    if note_type is None:
        raise ValueError(tr(u'Выберите тип текста в настройках (Shift+клик).',
                            u'Select a text type in settings (Shift-click).'))
    existing = owned_notes(doc, view)
    entries = []
    pinned = 0
    for element in FilteredElementCollector(doc, view.Id).OfClass(FamilyInstance):
        if not equipment_tags.is_equipment(element):
            continue
        if not settings_module.text_for(element.Symbol, settings).strip():
            continue
        notes = existing.get(element.UniqueId, [])
        if len(notes) > 1:
            raise ValueError(tr(u'У элемента {} несколько аннотаций задания АР. Удалите лишние копии.',
                                u'Element {} has multiple AR task annotations. Delete extra copies.').format(
                                    equipment_tags.id_int(element.Id)))
        note = notes[0] if notes else None
        if note is not None and note.Pinned:
            pinned += 1
            continue
        entries.append((element, note, None))
    # Проба масштаба УГО выполняется в equipment_tags.run до изменений текста.
    # Внешняя транзакция кнопки обеспечивает атомарность всей команды.
    stats = equipment_tags.run(doc, view, entries, settings,
                               annotation=TextAnnotation(settings, note_type.Id))
    stats['pinned'] = pinned
    return stats
