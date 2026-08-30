# -*- coding: utf-8 -*-
"""
Манифест (состояние) структурной схемы СКУД — JSON в текстовом параметре
самого чертёжного вида (manifest_param_name из настроек СКУД), а не в
файле на диске: едет вместе с моделью, доступен всем. Тот же приём, что
sot_layout_state.py для СОТ/СПС.

Вид определяется по имени (schematic_view_name) — см. find_schematic_view.

Структура (v2) — инкрементальное состояние, ключи по UniqueId (стабильны
между сессиями), внутри дублируются IntegerValue id для быстрого резолва
(нерезолвящийся id → BuildSkudSchematic считает узел «изменившимся» и
перерисовывает):

{
    "schema_version": 2,
    "line_ids": [id, ...],                 # линии контроллер→точки прохода,
                                           # пересоздаются каждый запуск
    "controllers": {
        "<controller UniqueId>": {
            "address": "F1",
            "node": {"element_ids": [id]},   # схемное семейство контроллера
            "passage_points": {
                "<pp_key>": {
                    "signature": [["считыватель", 1], ["замок", 1]],
                    "group": "<имя группы | null>",
                    "element_ids": [id, ...],
                    "devices": {
                        "<device UniqueId>": {
                            "schematic_id": id, "category": "считыватель",
                            "address": "F1.1", "room": "Коридор (101)"
                        }
                    }
                }
            }
        }
    }
}
"""

import json

from Autodesk.Revit.DB import FilteredElementCollector, View, ViewDrafting

from lowlife.params import get_string_param, set_param_any

SCHEMA_VERSION = 2


def empty_manifest():
    return {"schema_version": SCHEMA_VERSION, "line_ids": [], "controllers": {}}


def _parse(text):
    """dict манифеста ТЕКУЩЕЙ версии, либо None (пусто/битый/другая версия)."""
    if not text:
        return None
    try:
        data = json.loads(text)
    except:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema_version") != SCHEMA_VERSION:
        return None
    if not isinstance(data.get("controllers"), dict):
        return None
    return data


def raw_manifest(view, manifest_param_name):
    """Сырой dict из параметра вида без проверки версии (для миграции)."""
    if view is None or not manifest_param_name:
        return None
    try:
        return json.loads(get_string_param(view, manifest_param_name) or u"")
    except:
        return None


def find_schematic_view(doc, view_name, manifest_param_name):
    """
    Ищет чертёжный вид с точным именем view_name.

    Возвращает (view, manifest, name_conflict):
      - вид есть и это ViewDrafting -> (view, его манифест v2 или пустой, False);
      - вид с этим именем есть, но не ViewDrafting -> (None, None, True);
      - вида нет -> (None, None, False) — первый запуск, создаём новый.
    """
    if not view_name:
        return None, None, False

    try:
        views = FilteredElementCollector(doc).OfClass(View).ToElements()
    except:
        return None, None, False

    existing = None
    for view in views:
        try:
            name = view.Name
        except:
            continue
        if name == view_name:
            existing = view
            break

    if existing is None:
        return None, None, False

    if not isinstance(existing, ViewDrafting):
        return None, None, True

    return existing, load_manifest(existing, manifest_param_name), False


def load_manifest(view, manifest_param_name):
    """Манифест v2 из параметра вида, либо пустая структура."""
    if view is None or not manifest_param_name:
        return empty_manifest()

    data = _parse(get_string_param(view, manifest_param_name))
    return data if data is not None else empty_manifest()


def save_manifest(view, manifest_param_name, data):
    """
    Пишет манифест в параметр вида. Вызывать внутри транзакции. Возвращает
    (ok, reason) — reason=None при успехе, иначе короткое пояснение, почему
    запись не удалась (параметр не резолвится через LookupParameter на
    этом виде, только для чтения, или Set() бросил исключение).
    """
    if view is None:
        return False, u"вид не найден"

    if not manifest_param_name:
        return False, u"имя параметра манифеста не задано в настройках"

    payload = dict(data)
    payload["schema_version"] = SCHEMA_VERSION

    try:
        text = json.dumps(payload, ensure_ascii=False)
    except Exception as e:
        return False, u"не удалось сериализовать манифест в JSON: {}".format(e)

    try:
        p = view.LookupParameter(manifest_param_name)
    except Exception as e:
        return False, u"LookupParameter упал с ошибкой: {}".format(e)

    if p is None:
        return False, u"LookupParameter('{}') вернул None на этом виде".format(manifest_param_name)

    try:
        if p.IsReadOnly:
            return False, u"параметр «{}» на этом виде только для чтения".format(manifest_param_name)
    except Exception as e:
        return False, u"не удалось проверить IsReadOnly: {}".format(e)

    if not set_param_any(view, manifest_param_name, text):
        return False, u"set_param_any не смог записать значение (см. StorageType параметра)"

    return True, None
