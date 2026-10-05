# -*- coding: utf-8 -*-
"""
Деление структурной схемы СОТ на блоки «Корпус → Секция» — чистая логика
без Revit API (тестируется в tests/test_sot_sections.py).

Объект делится на корпуса, корпус — на секции, и у каждой секции свой
стояк (и свой шкаф). Поэтому на схеме каждая пара (корпус, секция) — свой
блок: заголовок «Корпус 1, секция 2», под ним этажи этой секции, у блока
свой вертикальный стояк и свои линии к своему шкафу (см.
sot_schematic.sync_section_groups). Блоки идут сверху вниз: сначала по
корпусу, внутри корпуса — по секции, в «естественном» порядке (номер 10
после 2, а не перед ним).

Значения корпуса/секции берутся с устройства (параметры из настроек СОТ);
вызывающий код передаёт сюда уже прочитанные строки. Если параметр в
настройках не задан — передаётся None, и это измерение просто не делит
схему (без обоих параметров — один блок без заголовка, как было раньше).
Если параметр задан, а на устройстве он пуст — устройство попадает в
блок «(без корпуса)»/«(без секции)», а не теряется.
"""

import re

NO_BUILDING = u"(без корпуса)"
NO_SECTION = u"(без секции)"

# Разделитель составного ключа блока в JSON раскладки — символ, которого
# не бывает в значениях параметров.
KEY_SEPARATOR = u"\u001f"

_SPLIT_NUMBER_RE = re.compile(r"(\d+)")


def natural_sort_key(text):
    """«Корпус 2» < «Корпус 10»: числовые куски сравниваются как числа."""
    parts = _SPLIT_NUMBER_RE.split(text or u"")
    return tuple((0, int(part), u"") if part.isdigit() else (1, 0, part.lower()) for part in parts)


def normalize_value(raw, placeholder):
    """
    Значение параметра корпуса/секции на устройстве -> значение для группы.
    raw=None — параметр не задан в настройках (измерение не используется) ->
    None; пустое/пробелы -> placeholder; иначе — значение без пробелов по краям.
    """
    if raw is None:
        return None
    text = raw.strip()
    return text if text else placeholder


def _with_prefix(value, prefix):
    """«1» -> «Корпус 1»; «Корпус 1» (слово уже есть в значении) — как есть."""
    if value.startswith(u"("):
        return value
    if prefix.lower() in value.lower():
        return value
    return u"{} {}".format(prefix, value)


def group_key(building, section):
    """Составной ключ блока (строка — ключ в JSON раскладки). Без корпуса и секции — u""."""
    if building is None and section is None:
        return u""
    return u"{}{}{}".format(building or u"", KEY_SEPARATOR, section or u"")


def group_label(building, section):
    """
    Заголовок блока на схеме: «Корпус 1, секция 2», «Корпус 1», «Секция 2»;
    без корпуса и секции — u"" (заголовок не рисуется).
    """
    parts = []
    if building is not None:
        parts.append(_with_prefix(building, u"Корпус"))
    if section is not None:
        text = _with_prefix(section, u"Секция")
        if parts and text.startswith(u"Секция"):
            text = u"с" + text[1:]
        parts.append(text)
    return u", ".join(parts)


def _group_sort_key(building, section):
    def one(value, placeholder):
        if value is None:
            return (0, ())
        # «(без корпуса)»/«(без секции)» — в конец, после всех настоящих.
        if value == placeholder:
            return (2, ())
        return (1, natural_sort_key(value))
    return (one(building, NO_BUILDING), one(section, NO_SECTION))


def split_into_groups(items, building_of, section_of):
    """
    Делит items на блоки (корпус, секция).

    building_of(item)/section_of(item) — сырое значение параметра на
    устройстве (строка, возможно пустая) или None, если параметр не задан в
    настройках (тогда это измерение схему не делит).

    Возвращает список блоков в порядке отрисовки сверху вниз:
    [{"key": ..., "label": ..., "building": ..., "section": ..., "items": [...]}, ...];
    порядок items внутри блока — как во входном списке.
    """
    groups = {}

    for item in items:
        building = normalize_value(building_of(item), NO_BUILDING)
        section = normalize_value(section_of(item), NO_SECTION)
        key = group_key(building, section)
        if key not in groups:
            groups[key] = {
                "key": key,
                "label": group_label(building, section),
                "building": building,
                "section": section,
                "items": []
            }
        groups[key]["items"].append(item)

    return sorted(groups.values(), key=lambda g: _group_sort_key(g["building"], g["section"]))
