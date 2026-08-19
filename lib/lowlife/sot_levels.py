# -*- coding: utf-8 -*-
"""
Разбор, сортировка и подпись этажей для структурной схемы СОТ.

Имя уровня в проекте всегда содержит две вещи: "Этаж N" (номер этажа) и
отметку — число вида "X,YYY"/"XX,YYY" с запятой, может быть отрицательным
("-X,YYY"/"-XX,YYY"). Знак отметки — это и есть признак подземного этажа:
отрицательная отметка -> этаж под землёй, положительная (без "-") -> над
землёй. Оба куска разбираются из имени уровня регулярками
(parse_level_mark), и по ним же строится подпись на схеме — "Этаж N
(отметка)" (get_level_label) — вместо того чтобы писать на схему сырое
имя уровня.

Сортировка идёт по числовому значению отметки, по убыванию: чем выше
отметка — тем выше этаж на схеме; отрицательные отметки автоматически
оказываются ниже положительных, а среди отрицательных более глубокая
(например -12,000) — ниже более мелкой (-4,000). Отдельный признак
"подземный/наземный" для этого не нужен — знак отметки уже всё определяет.

Если у уровня отметку по маске найти не удалось (имя не соответствует
формату) — используется реальная Elevation связанного Level как резерв,
чтобы такой этаж всё равно встал в разумное место, а не потерялся.
"""

import re

from lowlife.geometry import get_element_level
from lowlife.params import get_string_param

try:
    from collections import OrderedDict
except ImportError:
    OrderedDict = dict


_ETAZH_RE = re.compile(u"Этаж\\s*(-?\\d+)", re.IGNORECASE | re.UNICODE)
_MARK_RE = re.compile(r"(-?\d{1,2},\d{3})")


def parse_level_mark(name):
    """
    Разбирает имя уровня по маске проекта "... Этаж N ... X,YYY ..." ->
    (floor_num, mark_str, mark_value); floor_num/mark_str — как найдено в
    тексте (строки), mark_value — то же число как float (запятая заменена
    на точку, знак сохранён). Если "Этаж N" и/или отметка не нашлись —
    (None, None, None).
    """
    text = name or u""

    floor_match = _ETAZH_RE.search(text)
    mark_match = _MARK_RE.search(text)

    if not floor_match or not mark_match:
        return None, None, None

    floor_num = floor_match.group(1)
    mark_str = mark_match.group(1)

    try:
        mark_value = float(mark_str.replace(u",", u"."))
    except ValueError:
        return None, None, None

    return floor_num, mark_str, mark_value


def get_level_label(name):
    """
    Подпись уровня для схемы: "Этаж N (X,YYY)", если имя разобралось по
    маске проекта, иначе — исходное имя как есть (резерв для уровней,
    названных не по этой маске).
    """
    floor_num, mark_str, _mark_value = parse_level_mark(name)

    if floor_num is not None and mark_str is not None:
        return u"Этаж {} ({})".format(floor_num, mark_str)

    return name or u""


def level_sort_key(name, elevation, order_index):
    """
    Ключ сортировки для порядка отрисовки этажей сверху вниз на схеме —
    по убыванию эффективной высоты (выше — раньше, т.е. выше на схеме).

    Эффективная высота — отметка по маске проекта (parse_level_mark), если
    в имени уровня она нашлась; иначе — реальная Elevation связанного
    Level (в футах — единицы другие, чем у отметки в метрах, но для
    относительного порядка это неважно).
    """
    _floor_num, _mark_str, mark_value = parse_level_mark(name)
    effective_height = mark_value if mark_value is not None else (elevation or 0.0)

    return (-effective_height, order_index)


def get_level_display_name(doc, el, level_param_name):
    """
    Отображаемое имя этажа элемента: параметр level_param_name, если задан
    и заполнен, иначе имя реального Level (через get_element_level).
    """
    if level_param_name:
        value = get_string_param(el, level_param_name)
        if value and value.strip():
            return value.strip()

    level = get_element_level(doc, el)
    if level is not None:
        try:
            return level.Name
        except:
            pass

    return u"Без уровня"


def group_elements_by_level(doc, elements, level_param_name):
    """
    OrderedDict(display_name -> {"elements": [...], "level": Level|None,
    "order": int}) — level и order нужны только для сортировки
    (sorted_level_names), сгруппировано в порядке первого появления имени.
    """
    groups = OrderedDict()

    for index, el in enumerate(elements):
        if el is None:
            continue

        name = get_level_display_name(doc, el, level_param_name)

        if name not in groups:
            groups[name] = {
                "elements": [],
                "level": get_element_level(doc, el),
                "order": index
            }

        groups[name]["elements"].append(el)

    return groups


def sorted_level_names(level_groups):
    """Имена групп из group_elements_by_level, отсортированные level_sort_key."""

    def key(name):
        info = level_groups[name]
        level = info["level"]
        elevation = level.Elevation if level is not None else 0.0
        return level_sort_key(name, elevation, info["order"])

    return sorted(level_groups.keys(), key=key)
