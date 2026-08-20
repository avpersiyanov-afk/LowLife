# -*- coding: utf-8 -*-
"""
Хранение "базы" раскладки структурной схемы СОТ между запусками кнопки
«Структурная схема» — JSON в текстовом параметре самого чертёжного вида
(layout_param_name из настроек СОТ), а не в файле на диске: едет вместе
с моделью, доступен всем, кто открывает проект.

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

from Autodesk.Revit.DB import FilteredElementCollector, ViewDrafting

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


def find_layout_view(doc, layout_param_name):
    """
    Среди ViewDrafting документа ищет вид, у которого layout_param_name
    непустой и парсится как раскладка СОТ. Возвращает (view, state) —
    первый подходящий; (None, None), если такого вида нет (первый запуск
    кнопки, либо раскладка была стёрта/повреждена — тогда просто строим
    заново, как в первый раз).
    """
    if not layout_param_name:
        return None, None

    try:
        views = FilteredElementCollector(doc).OfClass(ViewDrafting).ToElements()
    except:
        return None, None

    for view in views:
        try:
            if view.IsTemplate:
                continue
        except:
            pass

        text = get_string_param(view, layout_param_name)
        state = _parse_state(text)

        if state is not None:
            return view, state

    return None, None


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
