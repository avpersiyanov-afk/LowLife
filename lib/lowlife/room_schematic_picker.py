# -*- coding: utf-8 -*-
"""
Выбор помещений/групп для кнопки Schematic.panel/BuildRoomSchematic
(«Рыба структурной схемы»).

Список помещений приходит от room_finder.get_records(doc) — та же база
(хост + все связи, с кэшем на сессию), что уже использует ToolsRooms.panel/
FindRoom. Уровни (порядок и подписи) — sot_levels.sorted_level_names/
get_level_label, та же сортировка этажей, что у СОТ/СПС/СКС.

Раньше это было одно большое кастомное WPF-окно сразу на все этажи —
неудобно при большом числе помещений в проекте ("мега большой список").
Вместо этого — цикл из стандартных pyRevit-диалогов (тот же forms.SelectFromList,
что и везде в проекте, см. ToolsRooms.panel/FindRoom):

  1. Один раз — параметр группировки (общее значение объединяет несколько
     помещений в один бокс схемы); "(без группировки)" — группы не строятся,
     доступны только отдельные помещения.
  2. Цикл: выбор этажа -> на этом этаже ОДИН список с чекбоксами
     (multiselect), где вперемешку и группы (непустые значения выбранного
     параметра, целиком), и ВСЕ помещения этажа по отдельности — можно
     отметить и группу, и вдобавок отдельные помещения из неё же (боксы
     независимы, специально не исключают друг друга, см. _room_label).
     После добавления — переключатель "Выбрать ещё"/"Завершить и построить"
     (forms.CommandSwitchWindow, тот же приём, что и у остальных пошаговых
     сценариев pyRevit). Esc/отмена на выборе этажа тоже завершает цикл.

Возвращает OrderedDict(level_name -> [box, ...]) с накопленным за все
проходы цикла набором, либо None, если ничего в итоге не выбрано.
"""

from collections import OrderedDict

from pyrevit import forms

from lowlife.params import get_param_any
from lowlife.room_finder import natural_key
from lowlife.sot_levels import sorted_level_names, get_level_label

_NO_GROUPING = u"(без группировки)"
_CONTINUE = u"Выбрать ещё"
_FINISH = u"Завершить и построить"


def list_room_param_names(records):
    """
    Отсортированный список имён параметров, встречающихся хотя бы на одном
    помещении из records — для выбора параметра группировки. Объединение
    (не пересечение): у части помещений (особенно из разных связей/типов)
    набор параметров может отличаться, показываем всё, что вообще где-то
    есть, а не только общее для всех сразу.
    """
    names = set()
    for record in records:
        try:
            for p in record.room.Parameters:
                name = p.Definition.Name if p and p.Definition else None
                if name:
                    names.add(name)
        except Exception:
            continue
    return sorted(names, key=lambda n: n.lower())


def _room_label(record):
    number = (record.number or u"").strip()
    name = (record.name or u"").strip()
    if number and name:
        return u"{} {}".format(number, name)
    return number or name or u"(без имени)"


def _build_level_groups(records):
    """
    OrderedDict(level_name -> {"elements": [...], "level": Level|None,
    "order": int}) — форма, ожидаемая sot_levels.sorted_level_names.
    Level берётся с самого room (record.room.Level) — он резолвится Revit
    API на родном документе помещения (хост или связь), поэтому безопасен
    и для помещений из связи, в отличие от doc.GetElement(record.room.LevelId)
    на документе-хосте (см. sot_levels.group_elements_by_level — та функция
    для этого случая не подходит).
    """
    groups = OrderedDict()
    for index, record in enumerate(records):
        name = record.level_name or u"Без уровня"
        if name not in groups:
            level = None
            try:
                level = record.room.Level
            except Exception:
                level = None
            groups[name] = {"elements": [], "level": level, "order": index}
        groups[name]["elements"].append(record)
    return groups


def _group_records_by_param(records, param_name):
    """OrderedDict(value -> [record, ...]) — только непустые значения
    param_name (в порядке первого появления). param_name=None -> {}
    (группировка выключена)."""
    groups = OrderedDict()
    if not param_name:
        return groups
    for record in records:
        value = get_param_any(record.room, param_name)
        value = value.strip() if value else u""
        if value:
            groups.setdefault(value, []).append(record)
    return groups


class _LevelOption(object):
    def __init__(self, level_name, label):
        self.level_name = level_name
        self.label = label

    def __str__(self):
        return self.label


class _GroupEntry(object):
    """Один пункт списка выбора — целая группа помещений (общее значение
    параметра группировки) как один будущий бокс схемы."""

    def __init__(self, value, records):
        self.value = value
        self.records = records

    def __str__(self):
        return u"▦ Группа «{}» ({} пом.) — один бокс".format(self.value, len(self.records))

    def to_box(self):
        return {
            "kind": "group",
            "label": self.value,
            "room_ids": [r.room_id for r in self.records if r.room_id is not None],
        }


class _RoomEntry(object):
    """Один пункт списка выбора — отдельное помещение как свой бокс.
    Показываются ВСЕ помещения этажа, включая те, что уже входят в одну
    из групп выше, — группа и отдельное помещение выбираются независимо
    (см. модульный докстринг: комбинированный сценарий)."""

    def __init__(self, record):
        self.record = record

    def __str__(self):
        return _room_label(self.record)

    def to_box(self):
        return {
            "kind": "room",
            "label": _room_label(self.record),
            "room_ids": [self.record.room_id] if self.record.room_id is not None else [],
        }


def _build_entries_for_level(level_records, param_name):
    groups = _group_records_by_param(level_records, param_name)
    entries = [_GroupEntry(value, recs) for value, recs in groups.items()]
    ordered_records = sorted(level_records, key=lambda r: natural_key(r.number))
    entries.extend(_RoomEntry(r) for r in ordered_records)
    return entries


def _ask_param_name(records):
    param_names = list_room_param_names(records)
    choice = forms.SelectFromList.show(
        [_NO_GROUPING] + param_names,
        title=u"Параметр группировки помещений в боксы схемы",
        button_name=u"Выбрать",
        multiselect=False,
    )
    if not choice:
        return None, False
    return (None if choice == _NO_GROUPING else choice), True


def _ask_level(level_order, boxes):
    options = []
    for level_name in level_order:
        count = len(boxes.get(level_name, []))
        label = get_level_label(level_name)
        if count:
            label = u"{} (уже добавлено: {})".format(label, count)
        options.append(_LevelOption(level_name, label))

    picked = forms.SelectFromList.show(
        options,
        title=u"На каком этаже добавляем боксы?",
        button_name=u"Далее",
        multiselect=False,
    )
    return picked.level_name if picked else None


def _box_signature(box):
    return box["kind"], box["label"], tuple(sorted(box["room_ids"]))


def show(doc, records):
    """
    Ведёт пользователя через цикл выбора (параметр группировки один раз,
    затем этаж -> группы/помещения на нём -> "выбрать ещё"/"завершить").
    Возвращает OrderedDict(level_name -> [box, ...]) с накопленным
    результатом, либо None, если в итоге ничего не выбрано/отменено.
    """
    if not records:
        return None

    level_groups = _build_level_groups(records)
    level_order = sorted_level_names(level_groups)

    param_name, param_chosen = _ask_param_name(records)
    if not param_chosen:
        return None

    boxes = OrderedDict()

    while True:
        level_name = _ask_level(level_order, boxes)
        if level_name is None:
            break

        level_records = level_groups[level_name]["elements"]
        entries = _build_entries_for_level(level_records, param_name)

        picked = forms.SelectFromList.show(
            entries,
            title=u"{} — отметьте группы и/или отдельные помещения".format(
                get_level_label(level_name)
            ),
            button_name=u"Добавить в список",
            multiselect=True,
        )

        if picked:
            level_boxes = boxes.setdefault(level_name, [])
            seen = set(_box_signature(b) for b in level_boxes)
            for entry in picked:
                box = entry.to_box()
                sig = _box_signature(box)
                if sig in seen:
                    continue
                seen.add(sig)
                level_boxes.append(box)

        total_boxes = sum(len(v) for v in boxes.values())
        if total_boxes == 0:
            # Ничего не накоплено ни разу — сразу к выбору другого этажа,
            # без вопроса "ещё?" (нечего завершать).
            continue

        switch = forms.CommandSwitchWindow.show(
            [_CONTINUE, _FINISH],
            message=u"Добавлено боксов: {} (этажей: {}).".format(
                total_boxes, len([1 for v in boxes.values() if v])
            ),
        )
        if switch != _CONTINUE:
            break

    return boxes if any(boxes.values()) else None
