# -*- coding: utf-8 -*-
"""
Логика кнопки Schematic.panel/BuildRoomSchematic («Рыба структурной схемы»)
без Revit API и без WPF — чтобы её можно было покрыть pytest-тестами
(tests/test_room_schematic_core.py). Окно — room_schematic_picker.py.

Модель данных: на каждом этаже — список строк-помещений (любые объекты с
атрибутами name, number, label, room_id). label — то, как помещение
показывается на схеме: пустой — помещения на схеме нет; помещения одного
этажа с одинаковым label сливаются в ОДИН бокс (так делаются группы —
«Квартиры», «МОП», ...; отдельного параметра группы больше нет).

Типовые этажи: этаж «такой же», как другой, если у них совпадает набор
имён помещений (с учётом количества, без учёта номеров — номера на каждом
этаже свои). Тогда подписи копируются по имени: i-е по номеру помещение с
данным именем получает подпись i-го по номеру помещения с тем же именем на
этаже-образце.
"""

from collections import OrderedDict


def _norm(text):
    return u" ".join((text or u"").split()).lower()


def floor_signature(rows):
    """Набор имён помещений этажа (с повторами) — для сравнения типовых
    этажей. Пустой tuple, если на этаже нет помещений."""
    return tuple(sorted(_norm(r.name) for r in rows))


def has_labels(rows):
    return any((r.label or u"").strip() for r in rows)


def copy_labels_by_name(src_rows, dst_rows):
    """
    Переносит подписи с этажа src_rows на dst_rows по совпадению имени
    помещения (см. модульный докстринг). Строки обоих списков должны быть
    в одном порядке сортировки (по номеру). Перезаписывает label только у
    тех строк dst_rows, которым нашлась пара; возвращает их число.
    """
    by_name = {}
    for row in src_rows:
        by_name.setdefault(_norm(row.name), []).append(row.label or u"")

    used = {}
    copied = 0
    for row in dst_rows:
        key = _norm(row.name)
        labels = by_name.get(key)
        index = used.get(key, 0)
        if not labels or index >= len(labels):
            continue
        row.label = labels[index]
        used[key] = index + 1
        copied += 1
    return copied


def find_typical_source(level_order, rows_by_level, level_name):
    """
    Имя этажа-образца для level_name: этаж с тем же набором помещений
    (floor_signature) и хотя бы одной заполненной подписью — ближайший по
    порядку level_order. None, если такого нет.
    """
    target_rows = rows_by_level.get(level_name) or []
    if not target_rows:
        return None
    signature = floor_signature(target_rows)
    index = level_order.index(level_name)

    candidates = []
    for other_index, other in enumerate(level_order):
        if other == level_name:
            continue
        rows = rows_by_level.get(other) or []
        if rows and has_labels(rows) and floor_signature(rows) == signature:
            candidates.append((abs(other_index - index), other_index, other))
    if not candidates:
        return None
    return min(candidates)[2]


def boxes_for_floor(rows):
    """
    [box, ...] для room_schematic.rebuild — один бокс на каждую различную
    непустую подпись, в порядке первого появления в rows; box = {"kind",
    "label", "room_ids"} ("group", если в боксе больше одного помещения).
    """
    grouped = OrderedDict()
    for row in rows:
        label = (row.label or u"").strip()
        if not label:
            continue
        grouped.setdefault(label, []).append(row.room_id)

    boxes = []
    for label, room_ids in grouped.items():
        boxes.append({
            "kind": "group" if len(room_ids) > 1 else "room",
            "label": label,
            "room_ids": [i for i in room_ids if i is not None],
        })
    return boxes


def build_boxes(level_order, rows_by_level):
    """OrderedDict(level_name -> [box, ...]) только для этажей, где есть
    хотя бы один бокс, в порядке level_order."""
    result = OrderedDict()
    for level_name in level_order:
        boxes = boxes_for_floor(rows_by_level.get(level_name) or [])
        if boxes:
            result[level_name] = boxes
    return result
