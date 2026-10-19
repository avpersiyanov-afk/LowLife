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
