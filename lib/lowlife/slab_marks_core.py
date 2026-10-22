# -*- coding: utf-8 -*-
"""
Чистая логика кнопки «Извещатели на перекрытие» (SPS.panel/DetectorsToSlab):
разбор попаданий луча вверх/вниз, высоты от пола, подписи отметок и
отклонение от типовой высоты этажа. Revit-часть — slab_marks.py, настройки —
slab_marks_settings.py. Без Revit API, покрыт tests/test_slab_marks_core.py.

Все длины здесь — в миллиметрах.
"""

try:
    unicode
except NameError:
    unicode = str


SLAB = "slab"          # перекрытие/покрытие (категории «Перекрытия», «Крыши»)
CEILING = "ceiling"    # подвесной потолок (категория «Потолки»)


class Probe(object):
    """
    Что над/под точкой: высота низа перекрытия от пола (slab_mm), высота
    подвесного потолка от пола (ceiling_mm — None, если потолка под
    перекрытием нет) и отметка пола (floor_z_mm — в координатах модели).
    """

    def __init__(self, slab_mm, ceiling_mm, floor_z_mm, slab_z_mm):
        self.slab_mm = slab_mm
        self.ceiling_mm = ceiling_mm
        self.floor_z_mm = floor_z_mm
        self.slab_z_mm = slab_z_mm
        # над точкой отверстие: slab_z_mm — перекрытие вокруг него (replace_slab)
        self.through_opening = False
        # пол найден лучом вниз (False — луч ничего не встретил, floor_z_mm — уровень)
        self.floor_found = True

    @property
    def ceiling_z_mm(self):
        """Отметка низа подвесного потолка в координатах модели или None."""
        if self.ceiling_mm is None:
            return None
        return self.floor_z_mm + self.ceiling_mm


def nearest(hits, kind):
    """Наименьшее расстояние среди попаданий [(расстояние, вид)] нужного вида или None."""
    best = None
    for distance, hit_kind in hits:
        if hit_kind != kind or distance is None or distance <= 0:
            continue
        if best is None or distance < best:
            best = distance
    return best


def probe(origin_z_mm, up_hits, down_hits, level_z_mm):
    """
    Probe по попаданиям лучей из точки на высоте origin_z_mm: up_hits —
    вверх, down_hits — вниз, [(расстояние в мм, SLAB/CEILING/None)].
    Пол — ближайшее перекрытие снизу (нет — отметка уровня level_z_mm).
    Нет перекрытия сверху — None.
    """
    slab_up = nearest(up_hits, SLAB)
    if slab_up is None:
        return None
    floor_down = nearest(down_hits, SLAB)
    floor_z = origin_z_mm - floor_down if floor_down is not None else level_z_mm
    slab_z = origin_z_mm + slab_up
    ceiling_up = nearest(up_hits, CEILING)
    ceiling_mm = None
    if ceiling_up is not None and ceiling_up < slab_up:
        ceiling_mm = origin_z_mm + ceiling_up - floor_z
    result = Probe(slab_z - floor_z, ceiling_mm, floor_z, slab_z)
    result.floor_found = floor_down is not None
    return result


def round_to(value_mm, step_mm):
    """Округление до шага step_mm (не меньше 1 мм)."""
    step = max(1.0, float(step_mm or 1.0))
    return round(float(value_mm) / step) * step


def format_height(value_mm, signed=True):
    """3300 → «+3,300» (метры, три знака, запятая — как отметки по ГОСТ 21.101)."""
    meters = float(value_mm) / 1000.0
    text = u"{:.3f}".format(abs(meters)).replace(u".", u",")
    if not signed:
        return text
    if abs(meters) < 0.0005:
        return u"±" + text
    return (u"+" if meters > 0 else u"-") + text


def distinct_heights(values_mm, step_mm):
    """Разные округлённые высоты по возрастанию (None пропускаются)."""
    result = set()
    for value in values_mm:
        if value is not None:
            result.add(round_to(value, step_mm))
    return sorted(result)


def height_range_text(values_mm, step_mm):
    """«+3,300» или «+3,300…+3,750» для набора высот; пусто — нет высот."""
    heights = distinct_heights(values_mm, step_mm)
    if not heights:
        return u""
    if len(heights) == 1:
        return format_height(heights[0])
    return u"{}…{}".format(format_height(heights[0]), format_height(heights[-1]))


def main_height(values_mm, step_mm):
    """Чаще всего встречающаяся округлённая высота (при равенстве — меньшая) или None."""
    counts = {}
    for value in values_mm:
        if value is None:
            continue
        key = round_to(value, step_mm)
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def typical_height(room_heights, step_mm):
    """
    Типовая высота перекрытия на виде: самая частая основная высота
    помещений. room_heights — [основная высота помещения или None].
    """
    return main_height(room_heights, step_mm)


def _fill(template, **values):
    try:
        return unicode(template).format(**values)
    except Exception:
        return unicode(template) + u" " + u" ".join(values[k] for k in sorted(values))


def room_label(slab_values, ceiling_values, typical_mm, step_mm,
               slab_format, ceiling_format, delta_format):
    """
    Текст подписи помещения (строки через перевод строки) или пусто:
      «Пер. +3,300» (или диапазон) — высота низа перекрытия от пола;
      «Δ +0,450» — если основная высота помещения отличается от типовой;
      «ПП +2,700» — если есть подвесной потолок.
    """
    lines = []
    slab_text = height_range_text(slab_values, step_mm)
    if slab_text:
        lines.append(_fill(slab_format, h=slab_text))
        main = main_height(slab_values, step_mm)
        if typical_mm is not None and main is not None and main != typical_mm:
            lines.append(_fill(delta_format, d=format_height(main - typical_mm)))
    ceiling_text = height_range_text(ceiling_values, step_mm)
    if ceiling_text:
        lines.append(_fill(ceiling_format, h=ceiling_text))
    return u"\n".join(lines)


def has_ceiling(ceiling_values):
    """Подвесной потолок есть хотя бы в одной точке помещения."""
    return any(value is not None for value in ceiling_values)


def split_words(text):
    """«дым, тепл;пламен» → ['дым', 'тепл', 'пламен'] (нижний регистр, ё → е)."""
    result = []
    for chunk in (text or u"").replace(u";", u",").replace(u"\n", u",").split(u","):
        word = chunk.strip().lower().replace(u"ё", u"е")
        if word and word not in result:
            result.append(word)
    return result


def is_detector(names, include_words, exclude_words):
    """
    Подходит ли устройство по именам семейства/типа: есть хотя бы одно слово
    из include_words (пустой список — подходит любое) и нет ни одного из
    exclude_words. Без учёта регистра.
    """
    text = u" ".join(unicode(n or u"") for n in names).lower().replace(u"ё", u"е")
    if any(word in text for word in exclude_words):
        return False
    if not include_words:
        return True
    return any(word in text for word in include_words)


def move_delta(current_z_mm, slab_z_mm, offset_mm):
    """Сдвиг по Z, чтобы точка вставки встала на offset_mm ниже низа перекрытия."""
    return (slab_z_mm - float(offset_mm or 0.0)) - current_z_mm


def grid_steps(size_mm, max_count=3, min_cell_mm=3000.0):
    """
    Сколько точек проверки брать по одной стороне помещения: 1 для
    небольших, до max_count для больших (не чаще одной на min_cell_mm).
    """
    count = int(float(size_mm) // float(min_cell_mm)) + 1
    return max(1, min(max_count, count))


# ------------------------------------------------------------
# Перепады плиты: края нижних граней перекрытий с разной отметкой
# ------------------------------------------------------------

def _offset_and_param(ax, ay, ux, uy, px, py):
    """(параметр вдоль прямой a+t·u, знаковое расстояние от неё) для точки p."""
    dx, dy = px - ax, py - ay
    return dx * ux + dy * uy, ux * dy - uy * dx


def step_segments(edges, plan_tol_mm, z_step_mm, min_len_mm=100.0, angle_deg=2.0):
    """
    Линии перепада плиты в плане. edges — края нижних граней перекрытий
    [(x1, y1, x2, y2, z)] в мм. Перепад — два почти параллельных края
    с отметками, различающимися не меньше z_step_mm, лежащие в плане не
    дальше plan_tol_mm друг от друга и перекрывающиеся на min_len_mm и
    больше. Возвращает [(x1, y1, x2, y2, dz)] — средняя линия общего
    участка, dz — разница отметок (вторая минус первая).
    """
    import bisect
    import math
    sin_tol = math.sin(math.radians(angle_deg))
    prepared = []
    for x1, y1, x2, y2, z in edges:
        length = math.hypot(x2 - x1, y2 - y1)
        if length < min_len_mm:
            continue
        prepared.append((min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2),
                         x1, y1, x2, y2, z, length))
    prepared.sort(key=lambda e: e[0])

    # Сравниваются только почти параллельные края: корзины по направлению
    # (градусы 0–179, края сравниваются со своей и соседними корзинами),
    # внутри корзины — по возрастанию x (дальше по x — уже не пересекутся).
    def bucket_of(e):
        angle = math.degrees(math.atan2(e[7] - e[5], e[6] - e[4])) % 180.0
        return int(angle // max(1.0, angle_deg)) % int(180.0 // max(1.0, angle_deg))

    bucket_count = int(180.0 // max(1.0, angle_deg))
    buckets = {}
    for index, e in enumerate(prepared):
        buckets.setdefault(bucket_of(e), []).append((e[0], index))

    result = []
    seen = set()
    for i, a in enumerate(prepared):
        ax0, ax1, ay0, ay1, x1, y1, x2, y2, za, la = a
        ux, uy = (x2 - x1) / la, (y2 - y1) / la
        own = bucket_of(a)
        others = []
        for b_key in set(((own - 1) % bucket_count, own, (own + 1) % bucket_count)):
            members = buckets.get(b_key, [])
            start = bisect.bisect_left(members, (ax0, i + 1))
            for x0, j in members[start:]:
                if x0 > ax1 + plan_tol_mm:
                    break
                if j > i:
                    others.append(j)
        for j in sorted(others):
            b = prepared[j]
            bx0, bx1, by0, by1, bx1_, by1_, bx2_, by2_, zb, lb = b
            if by0 > ay1 + plan_tol_mm or by1 < ay0 - plan_tol_mm:
                continue
            if abs(zb - za) < z_step_mm:
                continue
            vx, vy = (bx2_ - bx1_) / lb, (by2_ - by1_) / lb
            if abs(ux * vy - uy * vx) > sin_tol:
                continue
            t1, d1 = _offset_and_param(x1, y1, ux, uy, bx1_, by1_)
            t2, d2 = _offset_and_param(x1, y1, ux, uy, bx2_, by2_)
            if abs(d1) > plan_tol_mm or abs(d2) > plan_tol_mm:
                continue
            t_start = max(0.0, min(t1, t2))
            t_end = min(la, max(t1, t2))
            if t_end - t_start < min_len_mm:
                continue
            shift = (d1 + d2) / 4.0   # половина среднего смещения — средняя линия
            nx, ny = -uy * shift, ux * shift
            p = (x1 + ux * t_start + nx, y1 + uy * t_start + ny)
            q = (x1 + ux * t_end + nx, y1 + uy * t_end + ny)
            key = tuple(sorted([(round(p[0] / 10.0), round(p[1] / 10.0)),
                                (round(q[0] / 10.0), round(q[1] / 10.0))]))
            if key in seen:
                continue
            seen.add(key)
            result.append((p[0], p[1], q[0], q[1], zb - za))
    return result


def group_by_height(changed):
    """
    [(имя помещения, высота мм)] → [(высота, [(имя, сколько)])] по
    возрастанию высоты, имена — по убыванию количества, затем по алфавиту.
    Для отчёта: сотни помещений с одной высотой — одна строка.
    """
    groups = {}
    for name, height in changed:
        names = groups.setdefault(height, {})
        names[name] = names.get(name, 0) + 1
    result = []
    for height in sorted(groups):
        names = sorted(groups[height].items(), key=lambda item: (-item[1], item[0]))
        result.append((height, names))
    return result


def mount_surface(found, ceiling_mount):
    """
    Куда ставить извещатель: (отметка поверхности в мм или None, причина
    пропуска или None). Обычный — на низ перекрытия; встраиваемый
    (ceiling_mount) — на низ подвесного потолка, а без потолка над ним не
    переносится (встраиваемый на плиту не ставят).
    """
    if not ceiling_mount:
        return found.slab_z_mm, None
    if found.ceiling_z_mm is None:
        return None, u"встраиваемый, но подвесного потолка над ним нет"
    return found.ceiling_z_mm, None


def opening_slab_z(found_slab_z_mm, neighbor_slab_z_mm, step_mm=20.0):
    """
    Луч прошёл в отверстие перекрытия? found_slab_z_mm — найденный низ
    перекрытия над точкой, neighbor_slab_z_mm — то же в точках вокруг неё
    (None — там перекрытия нет: за пределами здания). Отверстие — если хотя
    бы в двух точках вокруг перекрытие найдено и везде, где найдено, оно
    ниже найденного над точкой (точка окружена плитой). Возвращает низ
    перекрытия вокруг отверстия (самый высокий из более низких) или None,
    если это не отверстие (высокая зона, край перекрытия).
    """
    found = [z for z in neighbor_slab_z_mm if z is not None]
    if len(found) < 2:
        return None
    if any(z > found_slab_z_mm - step_mm for z in found):
        return None
    return max(found)


def replace_slab(found, slab_z_mm):
    """Тот же Probe, но с низом перекрытия slab_z_mm (потолок выше него отбрасывается)."""
    ceiling_mm = found.ceiling_mm
    if ceiling_mm is not None and found.floor_z_mm + ceiling_mm >= slab_z_mm:
        ceiling_mm = None
    result = Probe(slab_z_mm - found.floor_z_mm, ceiling_mm, found.floor_z_mm, slab_z_mm)
    result.through_opening = True
    result.floor_found = found.floor_found
    return result


def merge_collinear(segments, tol_mm=50.0, angle_deg=1.0):
    """
    Склеить куски одной линии: [(x1, y1, x2, y2, dz)] → то же, где
    параллельные (до angle_deg) отрезки на одной прямой (смещение до
    tol_mm) с перекрытием или зазором до tol_mm — один отрезок. dz —
    наибольший по модулю. Кандидаты перепада от step_segments — это
    часто десятки кусков одной линии (каждая пара краёв даёт свой), а
    каждый кандидат потом проверяется лучами — без склейки это часы.
    """
    import math
    step = max(0.1, float(angle_deg))
    groups = {}
    for x1, y1, x2, y2, dz in segments:
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0
        a_key = int(round(angle / step)) % int(round(180.0 / step))
        rep = math.radians(a_key * step)
        ux, uy = math.cos(rep), math.sin(rep)
        c = -uy * (x1 + x2) / 2.0 + ux * (y1 + y2) / 2.0
        key = (a_key, int(round(c / max(1.0, tol_mm))))
        t1, t2 = x1 * ux + y1 * uy, x2 * ux + y2 * uy
        groups.setdefault(key, []).append((min(t1, t2), max(t1, t2), c, dz))
    result = []
    for (a_key, _c_key), items in sorted(groups.items()):
        rep = math.radians(a_key * step)
        ux, uy = math.cos(rep), math.sin(rep)
        items.sort()
        run = None
        for t0, t1, c, dz in items:
            if run is not None and t0 <= run[1] + tol_mm:
                run[1] = max(run[1], t1)
                run[2].append(c)
                if abs(dz) > abs(run[3]):
                    run[3] = dz
                continue
            if run is not None:
                result.append(_run_segment(run, ux, uy))
            run = [t0, t1, [c], dz]
        if run is not None:
            result.append(_run_segment(run, ux, uy))
    return result


def _run_segment(run, ux, uy):
    t0, t1, cs, dz = run
    c = sum(cs) / float(len(cs))
    nx, ny = -uy, ux
    return (ux * t0 + nx * c, uy * t0 + ny * c, ux * t1 + nx * c, uy * t1 + ny * c, dz)


def split_segment(segment, piece_mm=3000.0, max_pieces=8):
    """Отрезок → до max_pieces равных частей не короче ~piece_mm (для проверки по частям)."""
    import math
    x1, y1, x2, y2, dz = segment
    length = math.hypot(x2 - x1, y2 - y1)
    count = max(1, min(int(max_pieces), int(length // max(1.0, piece_mm))))
    pieces = []
    for i in range(count):
        a, b = float(i) / count, float(i + 1) / count
        pieces.append((x1 + (x2 - x1) * a, y1 + (y2 - y1) * a,
                       x1 + (x2 - x1) * b, y1 + (y2 - y1) * b, dz))
    return pieces


# ------------------------------------------------------------
# Заливки плит: многоугольники нижних граней перекрытий
# ------------------------------------------------------------

def polygon_area(points):
    """Площадь многоугольника [(x, y)] со знаком (против часовой — плюс)."""
    area = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def point_in_polygon(x, y, points):
    inside = False
    n = len(points)
    j = n - 1
    for i in range(n):
        xi, yi = points[i]
        xj, yj = points[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def split_outer(loops):
    """[[(x, y)]] → (внешний контур — наибольший по площади, [отверстия])."""
    loops = [loop for loop in loops if len(loop) >= 3]
    if not loops:
        return None, []
    ordered = sorted(loops, key=lambda loop: -abs(polygon_area(loop)))
    return ordered[0], ordered[1:]


def region_area(outer, holes):
    """Площадь контура без отверстий (мм²)."""
    return abs(polygon_area(outer)) - sum(abs(polygon_area(h)) for h in holes)


def _inside_region(x, y, outer, holes):
    return point_in_polygon(x, y, outer) and not any(point_in_polygon(x, y, h) for h in holes)


def interior_point(outer, holes, grid=9):
    """
    Точка внутри контура (не в отверстии) для подписи и проверки лучом:
    центр тяжести, если он внутри, иначе ближайший к нему узел сетки
    grid×grid по габариту. None — не нашлось.
    """
    area = polygon_area(outer)
    if abs(area) > 1e-9:
        cx = cy = 0.0
        n = len(outer)
        for i in range(n):
            x1, y1 = outer[i]
            x2, y2 = outer[(i + 1) % n]
            cross = x1 * y2 - x2 * y1
            cx += (x1 + x2) * cross
            cy += (y1 + y2) * cross
        cx /= 6.0 * area
        cy /= 6.0 * area
    else:
        cx = sum(p[0] for p in outer) / float(len(outer))
        cy = sum(p[1] for p in outer) / float(len(outer))
    if _inside_region(cx, cy, outer, holes):
        return cx, cy
    xs = [p[0] for p in outer]
    ys = [p[1] for p in outer]
    best = None
    for i in range(grid):
        for j in range(grid):
            x = min(xs) + (max(xs) - min(xs)) * (i + 0.5) / grid
            y = min(ys) + (max(ys) - min(ys)) * (j + 0.5) / grid
            if _inside_region(x, y, outer, holes):
                d = (x - cx) ** 2 + (y - cy) ** 2
                if best is None or d < best[0]:
                    best = (d, x, y)
    return None if best is None else (best[1], best[2])


def loop_edges(loops, z_mm):
    """Рёбра контуров [(x1, y1, x2, y2, z)] — для step_segments."""
    edges = []
    for loop in loops:
        n = len(loop)
        for i in range(n):
            x1, y1 = loop[i]
            x2, y2 = loop[(i + 1) % n]
            edges.append((x1, y1, x2, y2, z_mm))
    return edges


def typical_by_area(heights_areas, step_mm):
    """Типовая высота — с наибольшей суммарной площадью: [(высота, площадь)] → высота или None."""
    totals = {}
    for height, area in heights_areas:
        if height is None:
            continue
        key = round_to(height, step_mm)
        totals[key] = totals.get(key, 0.0) + area
    if not totals:
        return None
    return sorted(totals.items(), key=lambda item: (-item[1], item[0]))[0][0]


def slab_label(height_mm, typical_mm, step_mm, slab_format, delta_format):
    """Подпись заливки плиты: «Пер. +4,400» и, если не типовая, «Δ +0,650»."""
    height = round_to(height_mm, step_mm)
    lines = [_fill(slab_format, h=format_height(height))]
    if typical_mm is not None and height != typical_mm:
        lines.append(_fill(delta_format, d=format_height(height - typical_mm)))
    return u"\n".join(lines)


def ceiling_label(ceiling_values, step_mm, ceiling_format):
    """Подпись помещения с подвесным потолком: «ПП +2,700» или пусто."""
    text = height_range_text(ceiling_values, step_mm)
    return _fill(ceiling_format, h=text) if text else u""


def has_word(text, words):
    """Есть ли в тексте одно из слов (без учёта регистра, ё = е)."""
    low = unicode(text or u"").lower().replace(u"ё", u"е")
    return any(word in low for word in words)


def polygon_bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def lowest_face_at(x, y, regions):
    """
    Индекс самой низкой области, в которую попадает точка, или None.
    regions — [(z, внешний контур, [отверстия], габарит контура)] —
    нижние грани плит: снизу видна та, что ниже всех в этой точке.
    """
    best = None
    for index, (z, outer, holes, bbox) in enumerate(regions):
        if not (bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]):
            continue
        if best is not None and z >= regions[best][0]:
            continue
        if _inside_region(x, y, outer, holes):
            best = index
    return best


def interior_points(outer, holes, grid=9, count=5):
    """
    До count точек внутри контура (не в отверстиях): сначала interior_point,
    дальше узлы сетки grid×grid по удалённости от неё. Запасные точки — на
    случай, если в первой луч до пола проваливается (колонна, отверстие).
    """
    first = interior_point(outer, holes, grid)
    if first is None:
        return []
    xs = [p[0] for p in outer]
    ys = [p[1] for p in outer]
    nodes = []
    for i in range(grid):
        for j in range(grid):
            x = min(xs) + (max(xs) - min(xs)) * (i + 0.5) / grid
            y = min(ys) + (max(ys) - min(ys)) * (j + 0.5) / grid
            if (x, y) != first and _inside_region(x, y, outer, holes):
                nodes.append(((x - first[0]) ** 2 + (y - first[1]) ** 2, x, y))
    nodes.sort()
    # не подряд соседние узлы: берём через один, чтобы точки разошлись
    spread = nodes[1::2] + nodes[0::2]
    return [first] + [(x, y) for _d, x, y in spread[:max(0, count - 1)]]


def median(values):
    """Медиана (None пропускаются) или None."""
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2.0


def duplicate_faces(faces, z_tol=5.0, xy_tol=50.0, area_tol=0.01):
    """
    Индексы граней-дублей: та же отметка, габарит и площадь, что у грани
    раньше в списке (одна и та же плита в АР и КР). faces —
    [(z, (xmin, ymin, xmax, ymax), площадь)].
    """
    kept = []
    duplicates = set()
    for index, (z, bbox, area) in enumerate(faces):
        for other in kept:
            oz, obox, oarea = faces[other]
            if abs(z - oz) <= z_tol and \
                    all(abs(a - b) <= xy_tol for a, b in zip(bbox, obox)) and \
                    abs(area - oarea) <= area_tol * max(area, oarea, 1.0):
                duplicates.add(index)
                break
        else:
            kept.append(index)
    return duplicates


class BandPolygon(object):
    """
    Многоугольник для быстрых проверок «точка внутри»: рёбра заранее
    разложены по горизонтальным полосам (band мм), точка проверяется только
    против рёбер своей полосы — у плиты на всё здание тысячи вершин.
    """

    def __init__(self, points, band=1000.0):
        self.band = float(band)
        self.bands = {}
        n = len(points)
        for i in range(n):
            a = points[i]
            b = points[i - 1]
            lo, hi = min(a[1], b[1]), max(a[1], b[1])
            if hi == lo:
                continue   # горизонтальное ребро лучом вдоль X не пересекается
            for key in range(int(lo // self.band), int(hi // self.band) + 1):
                self.bands.setdefault(key, []).append((a[0], a[1], b[0], b[1]))

    def contains(self, x, y):
        inside = False
        for xi, yi, xj, yj in self.bands.get(int(y // self.band), ()):
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
        return inside


class RegionIndex(object):
    """
    lowest_face_at с сеткой по габаритам: точка проверяется только против
    областей, чей габарит задевает её ячейку (cell мм). На плане из тысяч
    граней — в разы быстрее перебора всех.
    """

    def __init__(self, regions, cell=5000.0):
        self.regions = regions
        self.cell = float(cell)
        self.grid = {}
        self.shapes = [(BandPolygon(outer), [BandPolygon(h) for h in holes])
                       for _z, outer, holes, _bbox in regions]
        for index, (_z, _outer, _holes, bbox) in enumerate(regions):
            for key in self._cells(bbox):
                self.grid.setdefault(key, []).append(index)

    def _cells(self, bbox):
        x0, y0 = int(bbox[0] // self.cell), int(bbox[1] // self.cell)
        x1, y1 = int(bbox[2] // self.cell), int(bbox[3] // self.cell)
        for i in range(x0, x1 + 1):
            for j in range(y0, y1 + 1):
                yield (i, j)

    def lowest_at(self, x, y):
        """Индекс самой низкой области в точке или None (как lowest_face_at)."""
        best = None
        for index in self.grid.get((int(x // self.cell), int(y // self.cell)), ()):
            z, outer, holes, bbox = self.regions[index]
            if not (bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]):
                continue
            if best is not None and z >= self.regions[best][0]:
                continue
            outer_shape, hole_shapes = self.shapes[index]
            if outer_shape.contains(x, y) and not any(h.contains(x, y) for h in hole_shapes):
                best = index
        return best

    def z_at(self, x, y):
        index = self.lowest_at(x, y)
        return None if index is None else self.regions[index][0]


def step_confirmed(segment, side_mm, z_at, min_dz):
    """
    Перепад подтверждён: по обе стороны линии (на side_mm от её середины)
    есть плита и отметки различаются не меньше min_dz. z_at(x, y) — отметка
    видимой снизу плиты в точке или None.
    """
    import math
    x1, y1, x2, y2 = segment[:4]
    length = math.hypot(x2 - x1, y2 - y1)
    if length <= 0:
        return False
    nx, ny = -(y2 - y1) / length * side_mm, (x2 - x1) / length * side_mm
    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    left = z_at(mx + nx, my + ny)
    right = z_at(mx - nx, my - ny)
    return left is not None and right is not None and abs(left - right) >= min_dz


class BoxGrid(object):
    """
    Сетка габаритов в плане: add(значение, (xmin, ymin, xmax, ymax)), at(x, y)
    — значения, чей габарит содержит точку. Для отбора перекрытий над точкой
    без запроса к Revit на каждую точку.
    """

    def __init__(self, cell=5000.0):
        self.cell = float(cell)
        self.grid = {}
        self.boxes = []

    def add(self, value, bbox):
        index = len(self.boxes)
        self.boxes.append((value, bbox))
        x0, y0 = int(bbox[0] // self.cell), int(bbox[1] // self.cell)
        x1, y1 = int(bbox[2] // self.cell), int(bbox[3] // self.cell)
        for i in range(x0, x1 + 1):
            for j in range(y0, y1 + 1):
                self.grid.setdefault((i, j), []).append(index)

    def at(self, x, y):
        result = []
        for index in self.grid.get((int(x // self.cell), int(y // self.cell)), ()):
            value, bbox = self.boxes[index]
            if bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]:
                result.append(value)
        return result


class FlatFace(object):
    """
    Горизонтальная грань для быстрых проверок «точка на грани»: отметка
    (мм), нижняя ли (нормаль вниз), контур и отверстия (BandPolygon).
    """

    def __init__(self, z_mm, is_bottom, outer, holes):
        self.z_mm = z_mm
        self.is_bottom = is_bottom
        self.bbox = polygon_bbox(outer)
        self.outer = BandPolygon(outer)
        self.holes = [BandPolygon(h) for h in holes]

    def contains(self, x, y):
        bbox = self.bbox
        if not (bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]):
            return False
        return self.outer.contains(x, y) and not any(h.contains(x, y) for h in self.holes)


def vertical_hits(faces, x, y, origin_z_mm):
    """
    По горизонтальным граням одного элемента: (вверх, вниз) — расстояния
    (мм) от точки на высоте origin_z_mm до нижних граней над ней и до
    верхних граней под ней, в которые попадает точка (x, y).
    """
    up = []
    down = []
    for face in faces:
        if not face.contains(x, y):
            continue
        if face.is_bottom and face.z_mm > origin_z_mm:
            up.append(face.z_mm - origin_z_mm)
        elif not face.is_bottom and face.z_mm < origin_z_mm:
            down.append(origin_z_mm - face.z_mm)
    return up, down
