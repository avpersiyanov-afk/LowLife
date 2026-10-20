# -*- coding: utf-8 -*-
u"""
Чистая геометрия кнопки «Лючки на уровнях» (ToolsTraySection.panel/TrayHatches):
где кабельный лоток пересекает уровень и какого размера там нужен лючок.

Без Revit API — точки и направления здесь обычные кортежи (x, y, z) в одних
единицах (кнопка передаёт футы), поэтому всё покрыто тестами
(tests/test_tray_hatch_core.py). Сбор лотков, уровней и вставка семейства —
lowlife.tray_hatch.

Лючок — прямоугольник в плане по сечению лотка горизонтальной плоскостью
уровня: у вертикального лотка это ширина × высота лотка; у наклонного —
описанный прямоугольник вокруг косого сечения (вытягивается вдоль уклона).
Ось лючка «ширина» идёт вдоль ширины лотка, «длина» — вдоль его высоты.
"""

import math

# лотки положе этого (синус угла к горизонту) не считаются проходящими через
# уровень: сечение почти горизонтального лотка уровнем — длинная полоса, а не
# проём под лючок
MIN_STEEPNESS = math.sin(math.radians(30.0))


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _length(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _unit(v):
    n = _length(v)
    if n < 1e-12:
        return None
    return (v[0] / n, v[1] / n, v[2] / n)


def steepness(p0, p1):
    u"""Синус угла оси лотка к горизонту (0 — горизонтальный, 1 — вертикальный)."""
    d = _unit(_sub(p1, p0))
    return 0.0 if d is None else abs(d[2])


def crossings(p0, p1, plane_zs, tol, connected=(False, False), min_steepness=MIN_STEEPNESS):
    u"""
    Пересечения оси лотка p0→p1 с горизонтальными плоскостями plane_zs.

    Возвращает [(индекс плоскости, (x, y, z))]. Плоскость строго между
    концами — пересечение. Конец, лежащий на плоскости (в пределах tol),
    считается пересечением, только если этот конец к чему-то присоединён
    (connected = (начало, конец)) — значит, трасса продолжается через уровень
    (соседний участок даст ту же точку, повторы убирает dedupe). Свободный
    конец на уровне — лоток просто начинается/кончается там.
    """
    if steepness(p0, p1) < min_steepness:
        return []
    z0, z1 = p0[2], p1[2]
    result = []
    for index, z in enumerate(plane_zs):
        if abs(z - z0) <= tol:
            if connected[0]:
                result.append((index, (p0[0], p0[1], z)))
            continue
        if abs(z - z1) <= tol:
            if connected[1]:
                result.append((index, (p1[0], p1[1], z)))
            continue
        if min(z0, z1) < z < max(z0, z1):
            t = (z - z0) / (z1 - z0)
            result.append((index, (
                p0[0] + (p1[0] - p0[0]) * t,
                p0[1] + (p1[1] - p0[1]) * t,
                z,
            )))
    return result


def _horizontal(v, d):
    u"""Вектор v, сдвинутый вдоль оси d до горизонтальной плоскости."""
    k = v[2] / d[2]
    return (v[0] - d[0] * k, v[1] - d[1] * k)


def footprint(axis, width_dir, height_dir, width, height):
    u"""
    Прямоугольник сечения лотка горизонтальной плоскостью.

    axis — направление оси лотка, width_dir/height_dir — направления ширины
    и высоты его сечения, width/height — размеры. Возвращает
    (угол оси «ширина» в плане, радианы; размер вдоль неё; размер поперёк)
    или None, если лоток горизонтальный.
    """
    d = _unit(axis)
    if d is None or abs(d[2]) < 1e-9:
        return None
    w = _horizontal(width_dir, d)
    h = _horizontal(height_dir, d)
    w_len = math.hypot(w[0], w[1])
    if w_len > 1e-9:
        u = (w[0] / w_len, w[1] / w_len)
    else:  # ширина вдоль оси — не бывает у настоящего лотка, но не падаем
        h_len = math.hypot(h[0], h[1])
        if h_len < 1e-9:
            return None
        u = (-h[1] / h_len, h[0] / h_len)
    v = (-u[1], u[0])

    def extent(a):
        return (abs(width * (w[0] * a[0] + w[1] * a[1]))
                + abs(height * (h[0] * a[0] + h[1] * a[1])))

    return math.atan2(u[1], u[0]), extent(u), extent(v)


def dedupe(points, tol):
    u"""
    Убирает повторы [(ключ, (x, y, z), ...)] — одинаковый ключ (уровень) и
    точки ближе tol в плане; остаётся первая.
    """
    kept = []
    for item in points:
        key, p = item[0], item[1]
        if any(k[0] == key and math.hypot(k[1][0] - p[0], k[1][1] - p[1]) <= tol for k in kept):
            continue
        kept.append(item)
    return kept


def rotation_delta(current, target):
    u"""
    Поворот (радианы, от −π/2 до π/2) от угла current к target с точностью
    до 180°: прямоугольник лючка симметричен, разворачивать его на пол-оборота
    незачем.
    """
    delta = (target - current) % math.pi
    if delta > math.pi / 2.0:
        delta -= math.pi
    return delta


def size_label(width_mm, length_mm):
    u"""«300×200» — для имени типа лючка с таким размером."""
    return u"{}×{}".format(int(round(width_mm)), int(round(length_mm)))
