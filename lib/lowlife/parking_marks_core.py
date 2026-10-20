# -*- coding: utf-8 -*-
"""
Чистая логика кнопки «Отметки парковки» (Tools.panel/ParkingMarks), без
Revit API: зона это или машиноместо, текст отметки по шаблону, отметка от
выбранной базы, попадание в секущий диапазон вида. Revit-часть —
parking_marks.py, настройки — parking_marks_settings.py.
"""

from lowlife.slab_marks_core import split_words, has_word, format_height

__all__ = ["split_words", "has_word", "format_height", "is_zone", "label",
           "split_template", "elevation_mm", "overlaps", "zone_label"]

PLACEHOLDER = u"{h}"


def is_zone(comment, words):
    """Комментарий элемента содержит одно из слов (без учёта регистра, ё = е)."""
    return bool(words) and has_word(comment, words)


def label(template, value_mm):
    """«Верх {h}», 3150 → «Верх +3,150». Нет «{h}» в шаблоне — отметка дописывается в конец."""
    template = template or PLACEHOLDER
    text = format_height(value_mm)
    if PLACEHOLDER in template:
        return template.replace(PLACEHOLDER, text)
    return (template.rstrip() + u" " + text).strip()


def zone_label(top_template, bottom_template, top_mm, bottom_mm):
    """Подпись зоны в две строки: верх, затем низ."""
    return label(top_template, top_mm) + u"\n" + label(bottom_template, bottom_mm)


def split_template(template):
    """Шаблон → (префикс, суффикс) для высотной отметки Revit: «Верх {h}» → («Верх», «»)."""
    template = template or PLACEHOLDER
    if PLACEHOLDER not in template:
        return template.strip(), u""
    before, after = template.split(PLACEHOLDER, 1)
    return before.strip(), after.strip()


def elevation_mm(z_mm, base_z_mm, base_shared_mm=0.0):
    """Отметка точки z_mm (внутренние координаты) от базы base_z_mm, у которой
    своя отметка base_shared_mm (0 — база и есть ±0,000)."""
    return float(z_mm) - float(base_z_mm) + float(base_shared_mm or 0.0)


def overlaps(bottom, top, range_bottom, range_top):
    """Отрезок [bottom, top] пересекает диапазон; None у границы диапазона — без ограничения."""
    if range_top is not None and bottom > range_top:
        return False
    if range_bottom is not None and top < range_bottom:
        return False
    return True
