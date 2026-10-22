# -*- coding: utf-8 -*-
u"""
Чистая геометрия кнопки «Боксы на лотки» (Tools.panel/TrayOpeningBoxes),
без Revit API — покрыта tests/test_tray_boxes_core.py. Revit-часть —
tray_boxes.py, настройки — tray_boxes_settings.py.

Векторы — кортежи (x, y, z), длины — в одних единицах (кнопка передаёт
футы). Бокс всегда стоит «ровно» (его ось Z вертикальна) и поворачивается
только вокруг вертикали:

  * лоток проходит сквозь стену — X бокса идёт вдоль стены, Y — поперёк
    (по толщине стены), Z — вверх. Ширина (X) — след лотка на стене плюс
    запас, высота (Z) — высота лотка плюс запас, глубина (Y) — толщина
    стены плюс запас по глубине;
  * лоток (вертикальный) проходит сквозь перекрытие — X бокса идёт вдоль
    ширины лотка, Y — вдоль его высоты, Z — вверх. Ширина — ширина лотка
    плюс запас, глубина — высота лотка плюс запас, высота — толщина
    перекрытия плюс запас по глубине.
"""

import math

WALL = u"wall"
FLOOR = u"floor"

# Причины, по которым бокс не ставится (для отчёта).
SKIP_SLOPED = u"лоток идёт наклонно"
SKIP_ANGLE = u"лоток проходит слишком наискось"


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _len(a):
    return math.sqrt(_dot(a, a))


def unit(a):
    n = _len(a)
    if n < 1e-12:
        return None
    return (a[0] / n, a[1] / n, a[2] / n)


def horizontal(a):
    u"""Горизонтальная составляющая, единичная (None — вектор вертикален)."""
    return unit((a[0], a[1], 0.0))


def merge_intervals(intervals, tol=1e-6):
    u"""[(a, b), ...] → объединённые отрезки по возрастанию; смыкающиеся
    (зазор не больше tol) — один отрезок. Куски одной стены/перекрытия
    (слои, части тела) сливаются в одно пересечение."""
    spans = sorted((min(a, b), max(a, b)) for a, b in intervals)
    result = []
    for a, b in spans:
        if result and a <= result[-1][1] + tol:
            if b > result[-1][1]:
                result[-1] = (result[-1][0], b)
        else:
            result.append((a, b))
    return result


class Box(object):
    u"""Где и какого размера бокс.

    center — середина бокса; x_dir — горизонтальное направление оси X
    бокса; width/depth/height — вдоль X/Y/Z бокса; thickness — толщина
    пересечённого элемента (по нормали)."""

    def __init__(self, kind, center, x_dir, width, depth, height, thickness):
        self.kind = kind
        self.center = center
        self.x_dir = x_dir
        self.width = width
        self.depth = depth
        self.height = height
        self.thickness = thickness

    def angle(self):
        u"""Поворот оси X бокса от оси X модели вокруг вертикали, радианы."""
        return math.atan2(self.x_dir[1], self.x_dir[0])

    def origin(self, at_bottom):
        u"""Точка вставки: середина бокса или середина его низа."""
        if not at_bottom:
            return self.center
        x, y, z = self.center
        return (x, y, z - self.height / 2.0)


def wall_box(center, tray_dir, wall_dir, crossing_len, tray_width, tray_height,
             extra, depth_extra, max_slope_deg, max_angle_deg):
    u"""Бокс в стене. tray_dir — ось лотка, wall_dir — направление стены в
    этой точке, crossing_len — длина оси лотка внутри стены.

    Возвращает (Box, None) или (None, причина пропуска)."""
    d = unit(tray_dir)
    if d is None or abs(d[2]) > math.sin(math.radians(max_slope_deg)):
        return None, SKIP_SLOPED
    d_h = horizontal(d)
    w = horizontal(wall_dir)
    if d_h is None or w is None:
        return None, SKIP_SLOPED
    normal = (-w[1], w[0], 0.0)
    cos_a = abs(_dot(d_h, normal))
    if cos_a < math.cos(math.radians(max_angle_deg)) or cos_a < 1e-6:
        return None, SKIP_ANGLE
    tan_a = math.sqrt(max(0.0, 1.0 - cos_a * cos_a)) / cos_a
    thickness = crossing_len * cos_a
    width = tray_width / cos_a + thickness * tan_a + extra
    return Box(WALL, center, w, width, thickness + depth_extra,
               tray_height + extra, thickness), None


def floor_box(center, tray_dir, width_dir, crossing_len, tray_width, tray_height,
              extra, depth_extra, max_slope_deg):
    u"""Бокс в перекрытии. tray_dir — ось лотка (должна быть вертикальной),
    width_dir — направление ширины сечения лотка, crossing_len — длина оси
    лотка внутри перекрытия.

    Возвращает (Box, None) или (None, причина пропуска)."""
    d = unit(tray_dir)
    if d is None or abs(d[2]) < math.cos(math.radians(max_slope_deg)):
        return None, SKIP_SLOPED
    x_dir = horizontal(width_dir) or (1.0, 0.0, 0.0)
    thickness = crossing_len * abs(d[2])
    return Box(FLOOR, center, x_dir, tray_width + extra, tray_height + extra,
               thickness + depth_extra, thickness), None


def sized_type_name(base, width_mm, depth_mm, height_mm):
    u"""Имя типоразмера под размеры бокса — когда размеры в семействе —
    параметры типа: «<исходный тип> 350x250x150» (ширина×глубина×высота)."""
    return u"{} {:.0f}x{:.0f}x{:.0f}".format(
        base, float(width_mm), float(depth_mm), float(height_mm))


def creation_comment(user, when):
    u"""Текст для «Комментариев» нового бокса: кто и когда его создал.
    when — datetime."""
    return u"{} {}".format(user or u"", when.strftime("%d.%m.%Y %H:%M")).strip()


def name_has(name, words):
    u"""Есть ли в имени хотя бы одно из слов (без учёта регистра). Пустой
    список — подходит любое имя."""
    words = [w.strip().lower() for w in words if w and w.strip()]
    if not words:
        return True
    name = (name or u"").lower()
    return any(w in name for w in words)


def split_words(text):
    return [w.strip() for w in (text or u"").split(u",") if w.strip()]
