# -*- coding: utf-8 -*-
"""
Чистая логика кнопки «СОУЭ — расстановка типовой этаж»
(SOUE.panel/PlaceTypicalFloor) без Revit API — покрыта тестами
(tests/test_soue_floor_core.py). Revit-часть — soue_floor.py.

Координаты — в одной системе (футы, план XY), какие именно — решает
вызывающий код (soue_floor.py работает в координатах связи).
"""

import math

from lowlife.ss1_easy_core import normalize, split_names  # noqa: F401 — реэкспорт

# Роли помещений.
ROLE_APARTMENT = "apartment"
ROLE_CORRIDOR = "corridor"
ROLE_LIFT_HALL = "lift_hall"
ROLES = (ROLE_APARTMENT, ROLE_CORRIDOR, ROLE_LIFT_HALL)

# Способ установки.
MOUNT_WALL = "wall"
MOUNT_CEILING = "ceiling"


def name_rank(name, names):
    """Место имени помещения в списке names (без учёта регистра) или None."""
    wanted = normalize(name)
    for index, candidate in enumerate(names):
        if normalize(candidate) == wanted:
            return index
    return None


def classify_rooms(rooms, apartment_names, corridor_names, lift_hall_names):
    """
    Какие помещения оснащаются и чем.

    rooms — [(ключ, имя помещения, имя лота, отметка или None)].

    Квартиры: в каждом лоте — одно помещение из apartment_names (список по
    приоритету: «Прихожая, Холл» — сначала прихожая, нет её — холл), из
    равных по приоритету — с минимальной отметкой (у двухуровневой
    квартиры — нижнее). Помещение квартиры без имени лота ставится само по
    себе — с предупреждением (ключ в no_lot).

    МОП: помещения из corridor_names / lift_hall_names, кроме лежащих в
    лоте квартиры (коридор внутри квартиры с её именем лота — не МОП).
    Если имя есть и в списке квартир, и в списке МОП, помещение без имени
    лота считается МОП.

    Возвращает (назначения {ключ: роль}, no_lot [ключи]).
    """
    groups = {}
    no_lot = []
    mop_names = list(corridor_names) + list(lift_hall_names)
    for key, name, lot, elevation in rooms:
        rank = name_rank(name, apartment_names)
        if rank is None:
            continue
        lot_norm = normalize(lot)
        if not lot_norm:
            if name_rank(name, mop_names) is None:
                no_lot.append(key)
            continue
        groups.setdefault(lot_norm, []).append((rank, elevation, key))

    result = {}
    for entries in groups.values():
        def sort_key(entry):
            rank, elevation, _ = entry
            return (rank, elevation is None, elevation if elevation is not None else 0.0)
        result[min(entries, key=sort_key)[2]] = ROLE_APARTMENT
    for key in no_lot:
        result[key] = ROLE_APARTMENT

    apartment_lots = set(groups)
    for key, name, lot, elevation in rooms:
        if key in result:
            continue
        if normalize(lot) in apartment_lots:
            continue
        if name_rank(name, corridor_names) is not None:
            result[key] = ROLE_CORRIDOR
        elif name_rank(name, lift_hall_names) is not None:
            result[key] = ROLE_LIFT_HALL
    return result, no_lot


def grid_cells(min_x, min_y, max_x, max_y, step):
    """
    Деление габарита помещения на клетки со стороной не больше step (по
    каждой оси — поровну). step <= 0 — одна клетка на весь габарит (один
    оповещатель на помещение). Возвращает [(x0, y0, x1, y1)].
    """
    width = max(0.0, max_x - min_x)
    height = max(0.0, max_y - min_y)
    if step and step > 0:
        nx = max(1, int(math.ceil(width / step - 1e-9)))
        ny = max(1, int(math.ceil(height / step - 1e-9)))
    else:
        nx = ny = 1
    dx = width / nx
    dy = height / ny
    cells = []
    for j in range(ny):
        for i in range(nx):
            cells.append((min_x + dx * i, min_y + dy * j,
                          min_x + dx * (i + 1), min_y + dy * (j + 1)))
    return cells


def cell_samples(cell, count=7):
    """
    Точки клетки для поиска точки внутри помещения: сначала центр, дальше —
    узлы сетки count×count по удалению от центра (для Г-образных коридоров,
    где центр клетки вне помещения).
    """
    x0, y0, x1, y1 = cell
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    points = []
    for j in range(count):
        for i in range(count):
            px = x0 + (x1 - x0) * (i + 0.5) / count
            py = y0 + (y1 - y0) * (j + 0.5) / count
            points.append((px, py))
    points.sort(key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
    return [(cx, cy)] + points


def _free_intervals(length, margin, blocked):
    """Отрезок [margin, length - margin] за вычетом интервалов blocked."""
    start, end = margin, length - margin
    if end < start:
        if length <= 0:
            return []
        start = end = length / 2.0
    free = [(start, end)]
    for b0, b1 in sorted(blocked):
        next_free = []
        for f0, f1 in free:
            if b1 <= f0 or b0 >= f1:
                next_free.append((f0, f1))
                continue
            if b0 > f0:
                next_free.append((f0, b0))
            if b1 < f1:
                next_free.append((b1, f1))
        free = next_free
    return free


def wall_point(segments, target, obstacles, margin):
    """
    Точка на стене помещения для настенного оповещателя: ближайшая к
    target (центр помещения или клетки) точка его границы, не ближе margin
    к углам сегмента и вне зон obstacles (двери, окна).

    segments  — [(x1, y1, x2, y2)] сегменты границы помещения;
    target    — (x, y);
    obstacles — [(x, y, радиус)]: точка стены ближе радиуса к ним не годится.

    Возвращает (x, y, nx, ny, свободна) — точку, единичную нормаль к стене
    в сторону target и признак, что точка вне зон obstacles (False — все
    стены заняты, взята ближайшая точка без учёта препятствий) — или None,
    если сегментов нет.
    """
    tx, ty = target
    best = None
    fallback = None
    for x1, y1, x2, y2 in segments:
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 1e-9:
            continue
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        t_target = (tx - x1) * ux + (ty - y1) * uy

        def at(t):
            return x1 + ux * t, y1 + uy * t

        # нормаль в сторону target
        nx, ny = -uy, ux
        if (tx - x1) * nx + (ty - y1) * ny < 0:
            nx, ny = -nx, -ny

        t_plain = min(max(t_target, 0.0), length)
        px, py = at(t_plain)
        distance = math.hypot(px - tx, py - ty)
        if fallback is None or distance < fallback[0]:
            fallback = (distance, (px, py, nx, ny, False))

        blocked = []
        for ox, oy, radius in obstacles:
            along = (ox - x1) * ux + (oy - y1) * uy
            across = abs((ox - x1) * -uy + (oy - y1) * ux)
            if across >= radius:
                continue
            half = math.sqrt(radius * radius - across * across)
            blocked.append((along - half, along + half))

        for f0, f1 in _free_intervals(length, margin, blocked):
            t = min(max(t_target, f0), f1)
            px, py = at(t)
            distance = math.hypot(px - tx, py - ty)
            if best is None or distance < best[0]:
                best = (distance, (px, py, nx, ny, True))

    if best is not None:
        return best[1]
    if fallback is not None:
        return fallback[1]
    return None



# ------------------------------------------------------------
# Акустический расчёт МОП (методика из «Расчёт СОУЭ.xlsx»)
# ------------------------------------------------------------

def acoustic_reach(spl_db, power_w, noise_dba, excess_db, dn_loss_db, obstacle_db,
                   mount_h, calc_h):
    """
    Предельные расстояния одного оповещателя (м):
      P0   = SPL + 10·lg(P) — уровень на 1 м по оси;
      Nтр  = N + превышение (15 дБ);
      rmax = 10^((P0 − ослабление ШДН (6) − ΔLпр − Nтр)/20) — наклонная
             дальность, на которой уровень ещё не ниже Nтр;
      R    = √(rmax² − (h − hрасч)²) — дальность в плане на высоте
             расчётной точки (1,5 м): для потолочного — радиус озвучивания,
             для настенного — L до самой дальней точки.
    Возвращает (rmax, R); R = 0, если оповещатель не дотягивает до
    расчётной плоскости.
    """
    if power_w <= 0:
        return 0.0, 0.0
    p0 = spl_db + 10.0 * math.log10(power_w)
    rmax = 10.0 ** ((p0 - dn_loss_db - obstacle_db - (noise_dba + excess_db)) / 20.0)
    dh = mount_h - calc_h
    return rmax, math.sqrt(max(0.0, rmax * rmax - dh * dh))


def sample_step(width, height, base, max_samples=600):
    """Шаг сетки расчётных точек: base, но не больше max_samples точек на габарит."""
    area = max(0.0, width) * max(0.0, height)
    if area <= 0 or base <= 0:
        return base
    return max(base, math.sqrt(area / float(max_samples)))


class SampleGrid(object):
    """
    Расчётные точки помещения — узлы сетки с шагом step, попавшие внутрь
    помещения (их отбирает вызывающий код). Служит и для проверки прямой
    видимости: отрезок не должен выходить за помещение (огибать угол
    Г-образного коридора).
    """

    def __init__(self, origin_x, origin_y, step, nodes):
        """nodes — [(i, j)] индексы узлов внутри помещения; точка узла — origin + (i, j)·step."""
        self.x0 = origin_x
        self.y0 = origin_y
        self.step = step
        self.nodes = list(nodes)
        self._set = set(self.nodes)
        self.full = False  # все узлы габарита внутри (прямоугольник) — ставит вызывающий

    def point(self, node):
        i, j = node
        return self.x0 + i * self.step, self.y0 + j * self.step

    def points(self):
        return [self.point(node) for node in self.nodes]

    def inside(self, x, y):
        fi = (x - self.x0) / self.step
        fj = (y - self.y0) / self.step
        i0, j0 = int(math.floor(fi)), int(math.floor(fj))
        # точка внутри, если рядом (в соседних узлах клетки) есть узел помещения
        for i in (i0, i0 + 1):
            for j in (j0, j0 + 1):
                if (i, j) in self._set:
                    return True
        return False

    def visible(self, ax, ay, bx, by):
        """Отрезок a→b не выходит из помещения (проверка с шагом step/2, без концов)."""
        length = math.hypot(bx - ax, by - ay)
        count = int(length / (self.step / 2.0))
        for k in range(1, count):
            t = float(k) / count
            if not self.inside(ax + (bx - ax) * t, ay + (by - ay) * t):
                return False
        return True


def wall_candidates(segments, obstacles, margin, step):
    """
    Точки-кандидаты для настенных оповещателей вдоль стен с шагом step.

    segments  — [(x1, y1, x2, y2, nx, ny)]: сегменты границы и единичные
                нормали внутрь помещения;
    obstacles — [(x, y, радиус)] двери и окна;
    margin    — отступ от концов сегмента.
    Возвращает [(x, y, nx, ny)].
    """
    result = []
    for x1, y1, x2, y2, nx, ny in segments:
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 1e-9:
            continue
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        blocked = []
        for ox, oy, radius in obstacles:
            along = (ox - x1) * ux + (oy - y1) * uy
            across = abs((ox - x1) * -uy + (oy - y1) * ux)
            if across >= radius:
                continue
            half = math.sqrt(radius * radius - across * across)
            blocked.append((along - half, along + half))
        for f0, f1 in _free_intervals(length, margin, blocked):
            count = max(1, int(math.ceil((f1 - f0) / step - 1e-9)) + 1) if f1 > f0 else 1
            for k in range(count):
                t = f0 + (f1 - f0) * (k / float(count - 1) if count > 1 else 0.5)
                result.append((x1 + ux * t, y1 + uy * t, nx, ny))
    return result


def coverage(candidates, samples, reach, grid=None, wall=False):
    """
    Какие расчётные точки озвучивает каждый кандидат: в плане не дальше
    reach, в прямой видимости (grid.visible), у настенного — перед стеной.
    candidates — [(x, y)] или [(x, y, nx, ny)]. Возвращает [set индексов].
    """
    reach2 = reach * reach
    result = []
    for cand in candidates:
        cx, cy = cand[0], cand[1]
        covered = set()
        for index, (px, py) in enumerate(samples):
            dx, dy = px - cx, py - cy
            if dx * dx + dy * dy > reach2:
                continue
            if wall and dx * cand[2] + dy * cand[3] < -1e-6:
                continue
            if grid is not None and not grid.visible(cx, cy, px, py):
                continue
            covered.add(index)
        result.append(covered)
    return result


def greedy_cover(candidates, sets, samples):
    """
    Небольшой набор кандидатов, озвучивающий все расчётные точки (жадно):
    каждый раз берётся ещё не озвученная точка, которую может озвучить
    меньше всего кандидатов (угол, торец коридора), и из озвучивающих её —
    кандидат, покрывающий больше всего ещё не озвученных точек; из равных —
    ближайший к центру тяжести этих точек (оповещатель встаёт посередине
    своей зоны). В конце убираются оповещатели, без которых всё озвучено.
    Возвращает (индексы выбранных, число точек, которые не озвучить).
    """
    covering = [[] for _ in samples]
    for index, covered in enumerate(sets):
        for k in covered:
            covering[k].append(index)

    left = set(k for k in range(len(samples)) if covering[k])
    unreachable = len(samples) - len(left)
    chosen = []
    while left:
        target = min(left, key=lambda k: (len(covering[k]), k))
        best = None
        for index in covering[target]:
            gain = sets[index] & left
            gx = sum(samples[k][0] for k in gain) / float(len(gain))
            gy = sum(samples[k][1] for k in gain) / float(len(gain))
            off = (candidates[index][0] - gx) ** 2 + (candidates[index][1] - gy) ** 2
            key = (len(gain), -off)
            if best is None or key > best[0]:
                best = (key, index, gain)
        chosen.append(best[1])
        left -= best[2]

    for index in list(chosen):
        others = set()
        for other in chosen:
            if other != index:
                others |= sets[other]
        if sets[index] <= others:
            chosen.remove(index)
    return chosen, unreachable


def lattice(min_x, min_y, max_x, max_y, reach):
    """
    Регулярная сетка потолочных оповещателей на прямоугольник: наименьшее
    nx·ny, при котором самая дальняя точка клетки (её угол) не дальше reach
    от центра: √((W/2nx)² + (H/2ny)²) ≤ R. Квадратная клетка даёт шаг R·√2,
    один ряд в узком коридоре — шаг почти 2R (как в расчёте). Возвращает
    центры клеток [(x, y)] или [], если reach <= 0.
    """
    if reach <= 0:
        return []
    width = max(0.0, max_x - min_x)
    height = max(0.0, max_y - min_y)
    best = None
    nx = 1
    while True:
        half_x = width / (2.0 * nx)
        if half_x < reach:
            half_y = math.sqrt(reach * reach - half_x * half_x)
            ny = max(1, int(math.ceil(height / (2.0 * half_y) - 1e-9)))
            if best is None or nx * ny < best[0] * best[1]:
                best = (nx, ny)
            if ny == 1:
                break
        nx += 1
        if best is not None and nx > best[0] * best[1]:
            break
    nx, ny = best
    return [(min_x + width * (i + 0.5) / nx, min_y + height * (j + 0.5) / ny)
            for j in range(ny) for i in range(nx)]


def classify_ceiling(hits):
    """
    Что над помещением по лучу вверх: hits — [(расстояние, вид)], вид —
    "ceiling" (подвесной потолок), "slab" (перекрытие/кровля) или другое
    (пропускается). Возвращает (вид, расстояние) ближайшего потолка или
    перекрытия, иначе (None, None).
    """
    for distance, kind in sorted(hits, key=lambda hit: hit[0]):
        if kind in (CEILING_SUSPENDED, CEILING_SLAB):
            return kind, distance
    return None, None


CEILING_SUSPENDED = "ceiling"
CEILING_SLAB = "slab"
