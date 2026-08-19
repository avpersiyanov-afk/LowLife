# -*- coding: utf-8 -*-
"""
Классификация и сортировка этажей для структурной схемы СОТ.

Реальный Level.Elevation не всегда доступен/надёжен (отображаемое имя
этажа может браться из текстового параметра-override, не связанного с
геометрией), поэтому порядок в первую очередь определяется по имени
(число в имени, признак подземного этажа), а Elevation используется
только как резервный критерий, когда числа в имени нет.

Признак подземного этажа — имя начинается с "-" и цифры (например "-1",
"-2 этаж") либо с буквы-маркера (по умолчанию "П", настраивается в
sot_settings). Подземные этажи всегда идут после наземных; при нескольких
подземных — глубже (например "-3") оказывается ниже на схеме, чем мельче
("-1").
"""

import re

from lowlife.geometry import get_element_level
from lowlife.params import get_string_param

try:
    from collections import OrderedDict
except ImportError:
    OrderedDict = dict


_NUMBER_RE = re.compile(r"\d+")
_DASH_DEPTH_RE = re.compile(r"^-\s*(\d+)")


def classify_level_name(name, underground_prefix=u"П"):
    """
    (is_underground, number) для имени этажа.

    "-N" (N — число) в начале имени -> подземный, number = N.
    Имя начинается с underground_prefix (регистронезависимо) -> подземный,
    number = первое число в имени, иначе 1.
    Иначе -> наземный, number = первое число в имени (или None, если в
    имени вообще нет цифр).
    """
    text = (name or u"").strip()

    dash_match = _DASH_DEPTH_RE.match(text)
    if dash_match:
        return True, int(dash_match.group(1))

    if underground_prefix and text.upper().startswith(underground_prefix.upper()):
        number_match = _NUMBER_RE.search(text)
        return True, (int(number_match.group(0)) if number_match else 1)

    number_match = _NUMBER_RE.search(text)
    return False, (int(number_match.group(0)) if number_match else None)


def level_sort_key(name, elevation, order_index, underground_prefix=u"П"):
    """
    Ключ сортировки для порядка отрисовки этажей сверху вниз на схеме.

    Наземные этажи идут раньше подземных. Среди наземных — выше номер
    этажа (или больше elevation, если номера в имени нет) — раньше, т.е.
    выше на схеме. Среди подземных — меньшая глубина (-1) раньше большей
    (-3), поэтому "-3" оказывается самым нижним.
    """
    is_underground, number = classify_level_name(name, underground_prefix)
    elevation = elevation if elevation is not None else 0.0

    if is_underground:
        depth = number if number is not None else 0
        return (1, depth, elevation, order_index)

    primary = -number if number is not None else -elevation
    return (0, primary, -elevation, order_index)


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


def sorted_level_names(level_groups, underground_prefix=u"П"):
    """Имена групп из group_elements_by_level, отсортированные level_sort_key."""

    def key(name):
        info = level_groups[name]
        level = info["level"]
        elevation = level.Elevation if level is not None else 0.0
        return level_sort_key(name, elevation, info["order"], underground_prefix)

    return sorted(level_groups.keys(), key=key)
