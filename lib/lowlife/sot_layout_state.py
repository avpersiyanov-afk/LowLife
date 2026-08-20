# -*- coding: utf-8 -*-
"""
Хранение "базы" раскладки структурной схемы СОТ между запусками кнопки
«Структурная схема» — JSON в текстовом параметре самого чертёжного вида
(layout_param_name из настроек СОТ), а не в файле на диске: едет вместе
с моделью, доступен всем, кто открывает проект. Вид, который обновляется,
определяется по имени (schematic_view_name из настроек СОТ) — см.
find_layout_view.

Структура state (после load_state):
{
    "v": 1,
    "levels": {
        "<имя уровня>": {
            "y": 0.0,
            "text_id": 123,           # ElementId.IntegerValue подписи уровня, либо None
            "line_ids": [124, 125],   # линии рамки/разделителя уровня
            "rooms": {
                "<room_key>": {
                    "x_left": 0.0,
                    "x_right": 12.3,
                    "text_id": 200,
                    "line_ids": [201, 202, 203, 204, 205],
                    "devices": {
                        "<UniqueId>": {"x": 1.2, "instance_id": 300, "tag_id": 301}
                    }
                }
            }
        }
    }
}

Все id хранятся как int (ElementId.IntegerValue) — при использовании
резолвятся обратно через doc.GetElement(ElementId(id)); нерезолвящийся id
(элемент удалён вручную/undo) — не ошибка, вызывающий код просто считает
группу "изменившейся" и перерисовывает её заново.
"""

import json

from Autodesk.Revit.DB import FilteredElementCollector, View, ViewDrafting

from lowlife.params import get_string_param, set_param_any

EMPTY_STATE = {"v": 1, "levels": {}}


def _empty_state():
    return {"v": 1, "levels": {}}


def _parse_state(text):
    if not text:
        return None

    try:
        data = json.loads(text)
    except:
        return None

    if not isinstance(data, dict) or "levels" not in data:
        return None

    return data


def find_layout_view(doc, view_name, layout_param_name):
    """
    Ищет вид с точным именем view_name (имя из настроек СОТ, а не
    "первый вид с непустой раскладкой" — так раскладка не зависит от
    случайного порядка обхода и не путается с дублированными видами:
    "Дублировать вид" в Revit копирует и параметр раскладки, поэтому
    поиск по заполненности параметра был бы неоднозначным).

    Возвращает (view, state, name_conflict):
      - вид с этим именем есть и это ViewDrafting -> (view, его раскладка
        (пустая, если параметр ещё не заполнен), False);
      - вид с этим именем есть, но не ViewDrafting -> (None, None, True) —
        конфликт имени, вызывающий код должен остановиться и попросить
        переименовать вид/сменить имя в настройках;
      - вида с таким именем нет -> (None, None, False) — первый запуск,
        создаём новый.
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

    return existing, load_state(existing, layout_param_name), False


def load_state(view, layout_param_name):
    """Раскладка вида, либо пустая структура (view=None, параметр пуст/битый)."""
    if view is None or not layout_param_name:
        return _empty_state()

    text = get_string_param(view, layout_param_name)
    state = _parse_state(text)

    return state if state is not None else _empty_state()


def save_state(view, layout_param_name, state):
    """Пишет state обратно в параметр вида. Вызывать внутри транзакции."""
    if view is None or not layout_param_name:
        return False

    try:
        text = json.dumps(state, ensure_ascii=False)
    except:
        return False

    return set_param_any(view, layout_param_name, text)
