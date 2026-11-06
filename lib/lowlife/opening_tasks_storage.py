# -*- coding: utf-8 -*-
"""Atomic model registry in DataStorage; element metadata in ExtensibleStorage."""
try:
    unicode
except NameError:
    unicode = str

from System import Guid, String
from lowlife.i18n import tr
from Autodesk.Revit.DB import DataStorage, FilteredElementCollector, StorageType
from Autodesk.Revit.DB.ExtensibleStorage import Schema, SchemaBuilder, AccessLevel, Entity
from lowlife import opening_tasks_core as core

SCHEMA_ID = Guid('12d35d7d-c051-4f57-bd4b-829e67b6bd72')


def schema():
    value = Schema.Lookup(SCHEMA_ID)
    if value is None:
        builder = SchemaBuilder(SCHEMA_ID)
        builder.SetSchemaName('LowLifeOpeningTasksV1')
        builder.SetReadAccessLevel(AccessLevel.Public)
        builder.SetWriteAccessLevel(AccessLevel.Public)
        builder.AddSimpleField('Json', String)
        value = builder.Finish()
    return value


def read(element):
    entity = element.GetEntity(schema())
    if not entity.IsValid():
        return None
    return core.loads(entity.Get[String](schema().GetField('Json')))


def write(element, value):
    entity = Entity(schema())
    entity.Set[String](schema().GetField('Json'), unicode(core.dumps(value)))
    element.SetEntity(entity)


def registry_element(doc):
    found = []
    for element in FilteredElementCollector(doc).OfClass(DataStorage):
        data = read(element)
        if data and data.get('role') == 'registry':
            found.append(element)
    if len(found) > 1:
        raise ValueError(tr(u'В модели несколько реестров заданий на отверстия',u'Multiple opening registries in model'))
    return found[0] if found else None


def registry(doc):
    element = registry_element(doc)
    return read(element) if element else core.empty_registry()


def save_registry(doc, data):
    element = registry_element(doc) or DataStorage.Create(doc)
    value = dict(data, role='registry')
    write(element, value)


def model_id(doc):
    return doc.ProjectInformation.UniqueId


def set_parameter(element, name, value):
    param = element.LookupParameter(name) if name else None
    if param is None or param.IsReadOnly or param.StorageType != StorageType.String:
        raise ValueError(tr(u'Нужен доступный для записи текстовый параметр экземпляра: ',u'A writable text instance parameter is required: ') + (name or ''))
    if not param.Set(unicode(core.dumps(value))):
        raise ValueError(tr(u'Не удалось записать JSON задания',u'Could not write opening-task JSON'))
