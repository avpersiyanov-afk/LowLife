# -*- coding: utf-8 -*-
"""
Чистая логика кнопки «Отметки парковки» (Tools.panel/ParkingMarks), без
Revit API: к какой группе относится элемент «Парковки» (зона светильников,
проезд, машиноместо, прочее), текст подписи по шаблону, склейка подписей,
попавших в одну точку плана, попадание в секущий диапазон вида.
Revit-часть — parking_marks.py, настройки — parking_marks_settings.py.

Все отметки — в миллиметрах от уровня плана.
"""

from lowlife.slab_marks_core import split_words, has_word, format_height

__all__ = ["split_words", "has_word", "format_height", "GROUPS", "OTHER", "classify",
           "label", "overlaps", "cluster", "group_boxes", "outer_boxes"]


class Group(object):
    """Группа элементов: ключ (префикс ключей настроек), имя для отчёта,
    слова и шаблон подписи по умолчанию, штриховать ли по умолчанию, цвет штриховки."""

    def __init__(self, key, name, words, text_format, fill, color):
        self.key = key
        self.name = name
        self.words = words
        self.text_format = text_format
        self.fill = fill
        self.color = color


# Порядок важен: элемент относится к первой группе, чьё слово нашлось
# (в «Комментариях» зоны светильников бывает «...в зоне проезда»).
GROUPS = [
    Group("lights", u"Зона светильников", u"светильн",
          u"Светильники: низ {bottom}, верх {top}", "yes", (240, 140, 40)),
    Group("drive", u"Проезд", u"проезд",
          u"Проезд: верх {top}", "yes", (60, 150, 220)),
    Group("parking", u"Машиноместо", u"машиномест, машино-мест",
          u"М/м: верх {top}", "yes", (120, 180, 70)),
]
OTHER = Group("other", u"Прочее", u"", u"Верх {top}", "no", (150, 150, 150))


def classify(text, groups_words):
    """Ключ первой группы, слово которой есть в тексте; None — ни одной.
    groups_words — [(ключ, [слова]), ...] в порядке проверки."""
    for key, words in groups_words:
        if words and has_word(text, words):
            return key
    return None


def label(template, top_mm, bottom_mm):
    """«Проезд: верх {top}» → «Проезд: верх +2,450»; {h} — то же, что {top}.
    Нет ни одного поля — отметка верха дописывается в конец."""
    template = template or u"{top}"
    top = format_height(top_mm)
    bottom = format_height(bottom_mm)
    if not any(field in template for field in (u"{top}", u"{bottom}", u"{h}")):
        return (template.rstrip() + u" " + top).strip()
    return template.replace(u"{top}", top).replace(u"{h}", top).replace(u"{bottom}", bottom)


def overlaps(bottom, top, range_bottom, range_top):
    """Отрезок [bottom, top] пересекает диапазон; None у границы диапазона — без ограничения."""
    if range_top is not None and bottom > range_top:
        return False
    if range_bottom is not None and top < range_bottom:
        return False
    return True


def cluster(points, radius):
    """Индексы точек [(x, y)], сгруппированные так, что в группе каждая точка
    ближе radius к какой-нибудь другой (подписи в одном месте — одна подпись)."""
    groups = []
    for index, (x, y) in enumerate(points):
        joined = [g for g in groups
                  if any((points[j][0] - x) ** 2 + (points[j][1] - y) ** 2 <= radius ** 2 for j in g)]
        merged = [index]
        for g in joined:
            merged = g + merged
            groups.remove(g)
        groups.append(sorted(merged))
    return sorted(groups, key=lambda g: g[0])


def _touch(a, b, tol):
    return (a[0] <= b[2] + tol and b[0] <= a[2] + tol and
            a[1] <= b[3] + tol and b[1] <= a[3] + tol)


def group_boxes(boxes, tol=0.0):
    """Индексы прямоугольников (x0, y0, x1, y1), сгруппированные по
    пересечению (с допуском tol, транзитивно): тела одной зоны в плане."""
    groups = []
    for index, box in enumerate(boxes):
        joined = [g for g in groups if any(_touch(boxes[j], box, tol) for j in g)]
        merged = [index]
        for g in joined:
            merged = g + merged
            groups.remove(g)
        groups.append(sorted(merged))
    return sorted(groups, key=lambda g: g[0])


def _inside(inner, outer, tol=1e-9):
    return (inner[0] >= outer[0] - tol and inner[1] >= outer[1] - tol and
            inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol)


def outer_boxes(boxes):
    """Индексы прямоугольников, не лежащих целиком внутри другого (из равных
    остаётся первый): контуры штриховки без деталей внутри зоны."""
    result = []
    for i, box in enumerate(boxes):
        covered = False
        for j, other in enumerate(boxes):
            if i == j or not _inside(box, other):
                continue
            if not _inside(other, box) or j < i:
                covered = True
                break
        if not covered:
            result.append(i)
    return result
