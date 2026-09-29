# -*- coding: utf-8 -*-
"""
Раскладка марок оборудования без пересечений — чистая 2D-геометрия, без
Revit API (поэтому модуль можно гонять и проверять вне Revit). Всю
работу с Revit (сбор элементов, размеры марок, запись позиций) делает
``equipment_tags.py``, сюда приходят уже прямоугольники в координатах
вида (u — вправо по экрану, v — вверх, единицы — футы модели).

Как раскладывается (см. :func:`layout`):

  1. **Кучки.** Оборудование, стоящее ближе ``cluster_dist`` друг к другу
     (по зазору между габаритами), объединяется в одну кучку — у кучки
     марки ставятся одним согласованным блоком, а не каждая сама по себе.
  2. **Форма блока** зависит от формы кучки:
       - «столбик» (кучка выше, чем шире — оборудование стоит одно над
         другим): марки в колонку сбоку, на ОДНОМ отступе от кучки,
         каждая напротив своего элемента; если соседние марки не влезают
         по высоте, они раздвигаются с зазором ``gap`` (минимально
         отходя от своих элементов). Выноска — наклонная от элемента до
         полки длиной ``shelf`` перед маркой;
       - «стопка» (одиночный элемент или оборудование рядом по
         горизонтали): марки стопкой друг над другом над (или под)
         кучкой, выноски прямоугольные — вертикально вверх от элемента,
         затем горизонтальная полка к марке. Порядок марок в стопке
         подобран так, чтобы выноски не пересекались: ближайшая к
         кучке марка — у крайнего к колонке марок элемента.
  3. **Выбор стороны.** Для каждой кучки перебираются варианты (справа/
     слева, вверх/вниз, 1×/2×/3× отступ, запасная форма блока) и
     выбирается вариант с наименьшим штрафом: наложение марок на уже
     поставленные марки и на оборудование, пересечение выносок с
     марками/выносками/чужим оборудованием, дальность. Кучки
     обрабатываются от самых больших к одиночным — большим блокам
     сложнее найти место.
"""


# ------------------------------------------------------------
# ПРЯМОУГОЛЬНИКИ И ОТРЕЗКИ
# ------------------------------------------------------------

def rect_w(r):
    return r[2] - r[0]


def rect_h(r):
    return r[3] - r[1]


def rect_center(r):
    return ((r[0] + r[2]) * 0.5, (r[1] + r[3]) * 0.5)


def rect_union(rects):
    rects = list(rects)
    return (min(r[0] for r in rects), min(r[1] for r in rects),
            max(r[2] for r in rects), max(r[3] for r in rects))


def rect_gap(a, b):
    """Расстояние между прямоугольниками (0, если касаются/перекрываются)."""
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return (dx * dx + dy * dy) ** 0.5


def rect_overlap_area(a, b):
    dx = min(a[2], b[2]) - max(a[0], b[0])
    dy = min(a[3], b[3]) - max(a[1], b[1])
    if dx <= 0 or dy <= 0:
        return 0.0
    return dx * dy


def rect_inflate(r, d):
    return (r[0] - d, r[1] - d, r[2] + d, r[3] + d)


def segment_hits_rect(p, q, r):
    """Проходит ли отрезок p-q через внутренность прямоугольника r
    (Лианг–Барски; касание границы не считается)."""
    x0, y0 = p
    dx, dy = q[0] - x0, q[1] - y0
    t0, t1 = 0.0, 1.0
    for pk, qk in ((-dx, x0 - r[0]), (dx, r[2] - x0),
                   (-dy, y0 - r[1]), (dy, r[3] - y0)):
        if abs(pk) < 1e-12:
            if qk <= 0:
                return False
            continue
        t = float(qk) / pk
        if pk < 0:
            if t > t1:
                return False
            if t > t0:
                t0 = t
        else:
            if t < t0:
                return False
            if t < t1:
                t1 = t
    return t1 - t0 > 1e-9


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def segments_cross(p1, p2, q1, q2):
    """Строгое пересечение отрезков (общие концы/касание не считаются)."""
    d1 = _cross(q1, q2, p1)
    d2 = _cross(q1, q2, p2)
    d3 = _cross(p1, p2, q1)
    d4 = _cross(p1, p2, q2)
    return (((d1 > 1e-12 and d2 < -1e-12) or (d1 < -1e-12 and d2 > 1e-12)) and
            ((d3 > 1e-12 and d4 < -1e-12) or (d3 < -1e-12 and d4 > 1e-12)))


def _seg_len(p, q):
    return ((q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2) ** 0.5


# ------------------------------------------------------------
# ВХОД / ВЫХОД
# ------------------------------------------------------------

class TagItem(object):
    """
    Один элемент под марку.

    key       — что угодно, по чему вызывающий потом найдёт свою марку;
    anchor    — (u, v) точка, куда смотрит выноска (центр/точка вставки);
    elem_rect — габарит элемента на виде (u0, v0, u1, v1);
    size      — (w, h) габарит самой марки без выноски.
    """

    def __init__(self, key, anchor, elem_rect, size):
        self.key = key
        self.anchor = anchor
        self.elem_rect = elem_rect
        self.size = size


class Placement(object):
    """
    Результат для одного элемента: tag_rect — где должен оказаться
    габарит марки; elbow — точка излома выноски; end — конец выноски у
    элемента; attach — точка, где выноска подходит к марке (край марки).
    """

    def __init__(self, key, tag_rect, elbow, end, attach):
        self.key = key
        self.tag_rect = tag_rect
        self.elbow = elbow
        self.end = end
        self.attach = attach

    def leader_segments(self):
        return [(self.end, self.elbow), (self.elbow, self.attach)]


# ------------------------------------------------------------
# КУЧКИ
# ------------------------------------------------------------

def find_clusters(items, cluster_dist):
    """Объединение-поиск по зазору между габаритами элементов."""
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if rect_gap(items[i].elem_rect, items[j].elem_rect) <= cluster_dist:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj

    groups = {}
    for i, it in enumerate(items):
        groups.setdefault(find(i), []).append(it)
    result = []
    for g in groups.values():
        result.extend(_split_2d(g))
    return result


def _split_2d(cluster):
    """
    Кучку, где оборудование стоит не в одну линию, а «сеткой» (несколько
    рядов и столбцов), режет на ряды — ряд потом раскладывается стопкой,
    как обычное «рядом по горизонтали». Одной колонкой/стопкой на всю
    сетку марки не поставить без длинных выносок через чужое оборудование.
    """
    if len(cluster) < 3:
        return [cluster]
    xs = [it.anchor[0] for it in cluster]
    ys = [it.anchor[1] for it in cluster]
    size = max(max(rect_w(it.elem_rect), rect_h(it.elem_rect)) for it in cluster)
    if min(max(xs) - min(xs), max(ys) - min(ys)) <= size:
        return [cluster]

    def lines(axis):
        tol = sum((rect_h(it.elem_rect) if axis == 1 else rect_w(it.elem_rect))
                  for it in cluster) / float(len(cluster)) * 0.75
        ordered = sorted(cluster, key=lambda it: it.anchor[axis])
        groups = [[ordered[0]]]
        for it in ordered[1:]:
            if it.anchor[axis] - groups[-1][-1].anchor[axis] > tol:
                groups.append([])
            groups[-1].append(it)
        return groups

    rows = lines(1)
    cols = lines(0)
    return rows if len(rows) <= len(cols) else cols


def _is_column(cluster):
    """Кучка — «столбик» (оборудование одно над другим)?"""
    if len(cluster) < 2:
        return False
    xs = [it.anchor[0] for it in cluster]
    ys = [it.anchor[1] for it in cluster]
    return (max(ys) - min(ys)) > (max(xs) - min(xs))


# ------------------------------------------------------------
# ВАРИАНТЫ БЛОКА МАРОК
# ------------------------------------------------------------

def _spread_1d(desired, sizes, gap):
    """
    Раздвигает отрезки вдоль оси так, чтобы они не перекрывались (с
    зазором gap) и центры отошли от желаемых как можно меньше.
    desired — желаемые центры (уже по возрастанию), sizes — длины.
    Классика: сливаем налезающие группы и центрируем каждую группу на
    среднем желаемом положении.
    """
    # блок: индексы членов, их смещения от начала блока, начало, длина
    blocks = []
    for i, c in enumerate(desired):
        blocks.append({"idx": [i], "start": c - sizes[i] * 0.5,
                       "offsets": [0.0], "length": sizes[i]})
        while len(blocks) > 1:
            b = blocks[-1]
            a = blocks[-2]
            if a["start"] + a["length"] + gap <= b["start"] + 1e-12:
                break
            # слить b в a
            shift = a["length"] + gap
            for k, off in zip(b["idx"], b["offsets"]):
                a["idx"].append(k)
                a["offsets"].append(off + shift)
            a["length"] = a["length"] + gap + b["length"]
            blocks.pop()
            # начало блока — среднее по «желаемому началу» всех членов
            wants = []
            for k, off in zip(a["idx"], a["offsets"]):
                wants.append(desired[k] - sizes[k] * 0.5 - off)
            a["start"] = sum(wants) / float(len(wants))

    centers = [0.0] * len(desired)
    for b in blocks:
        for k, off in zip(b["idx"], b["offsets"]):
            centers[k] = b["start"] + off + sizes[k] * 0.5
    return centers


def _layout_side(cluster, side, off, gap, shelf):
    """Колонка марок сбоку кучки, каждая напротив своего элемента."""
    items = sorted(cluster, key=lambda it: it.anchor[1])
    box = rect_union(it.elem_rect for it in cluster)
    desired = [it.anchor[1] for it in items]
    shelf = min(shelf, off)
    elbow_x = box[2] + off - shelf if side == "right" else box[0] - off + shelf

    def slots(order):
        return _spread_1d(desired, [it.size[1] for it in order], gap)

    # Порядок по высоте не гарантирует, что наклонные выноски не
    # пересекутся (элементы стоят не строго в линию). Распутываем:
    # пересекающиеся выноски меняются местами — суммарная длина при этом
    # строго падает, так что цикл конечен.
    for _ in range(len(items) * len(items)):
        centers = slots(items)
        swapped = False
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                if segments_cross(items[i].anchor, (elbow_x, centers[i]),
                                  items[j].anchor, (elbow_x, centers[j])):
                    items[i], items[j] = items[j], items[i]
                    swapped = True
                    break
            if swapped:
                break
        if not swapped:
            break
    centers = slots(items)

    result = []
    for it, cy in zip(items, centers):
        w, h = it.size
        if side == "right":
            x0 = box[2] + off
            rect = (x0, cy - h * 0.5, x0 + w, cy + h * 0.5)
            attach = (x0, cy)
            elbow = (x0 - shelf, cy)
        else:
            x1 = box[0] - off
            rect = (x1 - w, cy - h * 0.5, x1, cy + h * 0.5)
            attach = (x1, cy)
            elbow = (x1 + shelf, cy)
        result.append(Placement(it.key, rect, elbow, it.anchor, attach))
    return result


def _layout_stack(cluster, vdir, hdir, off, gap, shelf):
    """Стопка марок над/под кучкой, выноски вертикаль + полка."""
    box = rect_union(it.elem_rect for it in cluster)
    # ближайшая к кучке марка — у элемента, ближайшего к колонке марок
    if hdir == "right":
        items = sorted(cluster, key=lambda it: -it.anchor[0])
        col_x = max(it.anchor[0] for it in cluster) + shelf
    else:
        items = sorted(cluster, key=lambda it: it.anchor[0])
        col_x = min(it.anchor[0] for it in cluster) - shelf

    result = []
    if vdir == "up":
        cursor = box[3] + off
    else:
        cursor = box[1] - off

    for it in items:
        w, h = it.size
        if vdir == "up":
            y0, y1 = cursor, cursor + h
            cursor = y1 + gap
        else:
            y0, y1 = cursor - h, cursor
            cursor = y0 - gap
        cy = (y0 + y1) * 0.5
        if hdir == "right":
            rect = (col_x, y0, col_x + w, y1)
            attach = (col_x, cy)
        else:
            rect = (col_x - w, y0, col_x, y1)
            attach = (col_x, cy)
        elbow = (it.anchor[0], cy)
        result.append(Placement(it.key, rect, elbow, it.anchor, attach))
    return result


def _candidates(cluster, off, gap, shelf):
    """(штраф за «неприоритетность», раскладка) — все варианты для кучки."""
    column = _is_column(cluster)
    out = []
    for k in (1, 2, 3):
        o = off * k
        dist_pen = (k - 1) * 3.0
        side_pen = 0.0 if column else 6.0
        stack_pen = 6.0 if column else 0.0
        for side, pen in (("right", 0.0), ("left", 0.5)):
            out.append((side_pen + pen + dist_pen,
                        _layout_side(cluster, side, o, gap, shelf)))
        for vdir, vpen in (("up", 0.0), ("down", 1.0)):
            for hdir, hpen in (("right", 0.0), ("left", 0.5)):
                out.append((stack_pen + vpen + hpen + dist_pen,
                            _layout_stack(cluster, vdir, hdir, o, gap, shelf)))
    return out


# ------------------------------------------------------------
# ШТРАФ И ВЫБОР
# ------------------------------------------------------------

W_TAG_ON_TAG = 1000.0      # марка на марке — хуже всего
W_TAG_ON_ELEM = 200.0      # марка на оборудовании
W_TAG_ON_OBST = 100.0      # марка на прочем (чужие марки/тексты)
W_LEADER_THRU_TAG = 60.0   # выноска через марку
W_LEADER_CROSS = 40.0      # выноска через выноску
W_LEADER_THRU_ELEM = 8.0   # выноска через другое оборудование
W_LENGTH = 0.5             # за длину выноски (в долях высоты марки)


def _score(placements, elem_rects, obstacles, placed, placed_leaders, unit):
    s = 0.0
    for p in placements:
        tag_area = max(rect_w(p.tag_rect) * rect_h(p.tag_rect), 1e-9)
        for r in placed:
            s += W_TAG_ON_TAG * rect_overlap_area(p.tag_rect, r) / tag_area
        for key, r in elem_rects:
            s += W_TAG_ON_ELEM * rect_overlap_area(p.tag_rect, r) / tag_area
        for r in obstacles:
            s += W_TAG_ON_OBST * rect_overlap_area(p.tag_rect, r) / tag_area

        for a, b in p.leader_segments():
            if _seg_len(a, b) < 1e-9:
                continue
            for r in placed:
                if segment_hits_rect(a, b, r):
                    s += W_LEADER_THRU_TAG
            for c, d in placed_leaders:
                if segments_cross(a, b, c, d):
                    s += W_LEADER_CROSS
            for key, r in elem_rects:
                if key == p.key:
                    continue
                if segment_hits_rect(a, b, r):
                    s += W_LEADER_THRU_ELEM
            s += W_LENGTH * _seg_len(a, b) / unit
    return s


def layout(items, obstacles=None, offset=1.0, gap=0.2, shelf=0.5, cluster_dist=1.0):
    """
    Раскладывает марки. items — список :class:`TagItem`; obstacles —
    прямоугольники, на которые марки лучше не ставить (прочее
    оборудование на виде, чужие марки, тексты). Все размеры — в тех же
    единицах, что и координаты. Возвращает список :class:`Placement` в
    том же порядке, что items.
    """
    obstacles = list(obstacles or [])
    if not items:
        return []

    elem_rects = [(it.key, it.elem_rect) for it in items]
    unit = max(sum(it.size[1] for it in items) / float(len(items)), 1e-6)

    clusters = find_clusters(items, cluster_dist)
    # большие кучки первыми; при равенстве — слева направо, сверху вниз
    clusters.sort(key=lambda c: (-len(c),
                                 min(it.anchor[0] for it in c),
                                 -max(it.anchor[1] for it in c)))

    placed_rects = []
    placed_leaders = []
    by_key = {}

    for cluster in clusters:
        # проверяем только то, до чего марки кучки вообще могут дотянуться
        # (3× отступ + вся стопка + самая широкая марка) — на виде с сотнями
        # элементов иначе перебор заметно тормозит
        reach = (3 * offset + shelf + max(it.size[0] for it in cluster) +
                 sum(it.size[1] + gap for it in cluster))
        zone = rect_inflate(rect_union(it.elem_rect for it in cluster), reach)
        near_elems = [(k, r) for k, r in elem_rects if rect_gap(r, zone) == 0.0]
        near_obst = [r for r in obstacles if rect_gap(r, zone) == 0.0]
        near_placed = [r for r in placed_rects if rect_gap(r, zone) == 0.0]

        best = None
        for pref_pen, cand in _candidates(cluster, offset, gap, shelf):
            sc = pref_pen + _score(cand, near_elems, near_obst,
                                   near_placed, placed_leaders, unit)
            if best is None or sc < best[0]:
                best = (sc, cand)
        for p in best[1]:
            by_key[p.key] = p
            placed_rects.append(rect_inflate(p.tag_rect, gap * 0.5))
            placed_leaders.extend(p.leader_segments())

    return [by_key[it.key] for it in items]


def count_conflicts(placements, items):
    """Для отчёта: сколько пар марок перекрываются и сколько пар выносок
    пересекается после раскладки (в идеале 0 и 0)."""
    overlaps = 0
    crossings = 0
    for i in range(len(placements)):
        for j in range(i + 1, len(placements)):
            a, b = placements[i], placements[j]
            if rect_overlap_area(a.tag_rect, b.tag_rect) > 1e-9:
                overlaps += 1
            hit = False
            for s1 in a.leader_segments():
                for s2 in b.leader_segments():
                    if segments_cross(s1[0], s1[1], s2[0], s2[1]):
                        hit = True
            if hit:
                crossings += 1
    return overlaps, crossings
