# -*- coding: utf-8 -*-
"""
Чистая логика кнопки «Доступ к извещателям» (SPS.panel/DetectorAccess):
препятствия в плане (выпуклые многоугольники с диапазоном высот), проверка
зоны доступа под извещателем, поиск ближайшего свободного места и тексты
подписей. Revit-часть — detector_access.py, настройки —
detector_access_settings.py. Без Revit API, покрыт
tests/test_detector_access_core.py.

Все длины здесь — в миллиметрах, координаты — модели (план X/Y, высота Z).
"""

import math

try:
    unicode
except NameError:
    unicode = str


# Состояния извещателя
OK = "ok"                    # доступен с пола
BLOCKED = "blocked"          # зону доступа или сам извещатель перекрывают сети
NO_FLOOR = "no_floor"        # под извещателем нет пола этажа (шахта, проём, второй свет)
ABOVE_CEILING = "above"      # над подвесным потолком — с пола не достать
TOO_HIGH = "too_high"        # выше, чем достаёт стремянка (настройка)
NO_SLAB = "no_slab"          # над ним не найдено ни перекрытия, ни потолка
NOT_MOUNTED = "not_mounted"  # стоит у пола — ещё не поднят на перекрытие/потолок

STATUS_TEXT = {
    OK: u"доступен",
    BLOCKED: u"перекрыт инженерными сетями",
    NO_FLOOR: u"под ним нет пола этажа",
    ABOVE_CEILING: u"над подвесным потолком",
    TOO_HIGH: u"слишком высоко от пола",
    NO_SLAB: u"над ним нет перекрытия/потолка",
    NOT_MOUNTED: u"стоит у пола — сначала «Извещатели на перекрытие»",
}

# Для этих состояний ищется ближайшее место, куда перенести извещатель.
MOVABLE = (BLOCKED, NO_FLOOR)

# Радиус «самого извещателя» в плане: препятствие в этом круге под ним —
# извещатель перекрыт (а не только занята зона доступа вокруг него).
DETECTOR_RADIUS_MM = 100.0

# Нижняя граница проверяемого объёма над полом: ниже — отделка, плинтусы.
FLOOR_GAP_MM = 20.0

# Извещатель на подвесном потолке, если его точка не выше потолка больше чем на это.
CEILING_TOLERANCE_MM = 100.0

# Пол «пропал», если ближайшее перекрытие снизу ниже уровня больше чем на это
# (луч ушёл в шахту/проём до пола нижнего этажа).
FLOOR_DROP_MM = 1000.0

# Точка извещателя ниже этого над полом — он ещё не поднят на перекрытие/потолок.
MOUNTED_MIN_HEIGHT_MM = 500.0

# Новое место: поверхность установки и пол — на той же высоте с этим допуском.
SAME_SURFACE_MM = 100.0
SAME_FLOOR_MM = 300.0


# ------------------------------------------------------------
# Геометрия в плане
# ------------------------------------------------------------

def convex_hull(points):
    """Выпуклая оболочка [(x, y)] против часовой стрелки (монотонная цепь)."""
    pts = sorted(set((float(x), float(y)) for x, y in points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def segment_rect(x1, y1, x2, y2, half_width):
    """
    Прямоугольник вокруг отрезка (ось трубы/воздуховода/лотка в плане)
    шириной 2·half_width; короткий отрезок (стояк) — квадрат вокруг середины.
    """
    hw = float(half_width)
    length = math.hypot(x2 - x1, y2 - y1)
    if length < 1e-6:
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        return [(cx - hw, cy - hw), (cx + hw, cy - hw), (cx + hw, cy + hw), (cx - hw, cy + hw)]
    nx, ny = -(y2 - y1) / length * hw, (x2 - x1) / length * hw
    return [(x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x2 - nx, y2 - ny), (x2 + nx, y2 + ny)]


def _segment_distance(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def polygon_distance(px, py, polygon):
    """Расстояние от точки до выпуклого многоугольника (0 — точка внутри)."""
    n = len(polygon)
    if n == 0:
        return float("inf")
    if n == 1:
        return math.hypot(px - polygon[0][0], py - polygon[0][1])
    if n >= 3:
        sign = 0
        inside = True
        for i in range(n):
            ax, ay = polygon[i]
            bx, by = polygon[(i + 1) % n]
            c = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
            if abs(c) < 1e-9:
                continue
            s = 1 if c > 0 else -1
            if sign == 0:
                sign = s
            elif s != sign:
                inside = False
                break
        if inside:
            return 0.0
    best = float("inf")
    for i in range(n if n >= 3 else 1):
        ax, ay = polygon[i]
        bx, by = polygon[(i + 1) % n]
        best = min(best, _segment_distance(px, py, ax, ay, bx, by))
    return best


class Obstacle(object):
    """
    Препятствие: name — для отчёта и подписи (обычно категория), label —
    подробнее (тип, связь), polygon — выпуклый контур в плане, z0/z1 —
    низ/верх. key — для отчёта/выделения (Id связи или -1, Id элемента).
    """

    def __init__(self, name, polygon, z0, z1, label=u"", key=None):
        self.name = name
        self.label = label
        self.polygon = list(polygon)
        self.z0 = float(min(z0, z1))
        self.z1 = float(max(z0, z1))
        self.key = key
        xs = [p[0] for p in self.polygon] or [0.0]
        ys = [p[1] for p in self.polygon] or [0.0]
        self.box = (min(xs), min(ys), max(xs), max(ys))

    def overlaps_height(self, z0, z1):
        return self.z0 < z1 and self.z1 > z0

    def near_box(self, x, y, radius):
        x0, y0, x1, y1 = self.box
        return x0 - radius <= x <= x1 + radius and y0 - radius <= y <= y1 + radius

    def touches_circle(self, x, y, radius):
        """Контур в плане заходит в круг радиуса radius с центром (x, y)."""
        if not self.near_box(x, y, radius):
            return False
        return polygon_distance(x, y, self.polygon) < radius


class ObstacleIndex(object):
    """Сетка в плане: какие препятствия рядом с точкой — без перебора всех."""

    def __init__(self, cell_mm=2000.0):
        self.cell = float(cell_mm)
        self.cells = {}
        self.items = []

    def _range(self, a0, a1):
        return range(int(math.floor(a0 / self.cell)), int(math.floor(a1 / self.cell)) + 1)

    def add(self, obstacle):
        index = len(self.items)
        self.items.append(obstacle)
        x0, y0, x1, y1 = obstacle.box
        for i in self._range(x0, x1):
            for j in self._range(y0, y1):
                self.cells.setdefault((i, j), []).append(index)

    def near(self, x, y, radius):
        """Препятствия, чьи габариты в плане ближе radius к точке (без повторов)."""
        found = set()
        for i in self._range(x - radius, x + radius):
            for j in self._range(y - radius, y + radius):
                found.update(self.cells.get((i, j), ()))
        result = [self.items[k] for k in sorted(found)]
        return [o for o in result if o.near_box(x, y, radius)]

    def __len__(self):
        return len(self.items)


def blockers(obstacles, x, y, radius, z0, z1):
    """Препятствия из obstacles, которые заходят в цилиндр (x, y, radius) × [z0, z1]."""
    if z1 <= z0:
        return []
    return [o for o in obstacles
            if o.overlaps_height(z0, z1) and o.touches_circle(x, y, radius)]


# ------------------------------------------------------------
# Извещатель: где он, что над/под ним
# ------------------------------------------------------------

def mount_kind(detector_z_mm, ceiling_z_mm):
    """
    На чём извещатель: «ceiling» (подвесной потолок), «slab» (перекрытие)
    или «above» — над подвесным потолком (в запотолочном пространстве).
    Точка извещателя выше потолка не больше CEILING_TOLERANCE_MM — он на потолке.
    """
    if ceiling_z_mm is None:
        return "slab"
    if detector_z_mm <= ceiling_z_mm + CEILING_TOLERANCE_MM:
        return "ceiling"
    return "above"


def mount_z(kind, slab_z_mm, ceiling_z_mm):
    """Отметка поверхности установки для вида kind (None — её нет)."""
    if kind == "ceiling":
        return ceiling_z_mm
    if kind == "slab" and ceiling_z_mm is None:
        return slab_z_mm
    return None


def has_floor(floor_found, floor_z_mm, level_z_mm):
    """Пол этажа под точкой: перекрытие снизу найдено и не провалилось ниже уровня."""
    if not floor_found or floor_z_mm is None:
        return False
    return floor_z_mm >= level_z_mm - FLOOR_DROP_MM


def column_band(floor_z_mm, detector_z_mm, top_gap_mm):
    """
    Проверяемый по высоте объём под извещателем: от пола (+FLOOR_GAP_MM) до
    точки извещателя минус top_gap_mm — то, что висит у самого
    перекрытия/потолка (светильники, решётки), к извещателю не мешает.
    """
    return floor_z_mm + FLOOR_GAP_MM, detector_z_mm - float(top_gap_mm or 0.0)


def classify(floor_ok, kind, height_mm, max_height_mm, zone_blockers):
    """Состояние извещателя (OK/BLOCKED/NO_FLOOR/ABOVE_CEILING/TOO_HIGH/NOT_MOUNTED)."""
    if kind == "above":
        return ABOVE_CEILING
    if not floor_ok:
        return NO_FLOOR
    if height_mm is not None and height_mm < MOUNTED_MIN_HEIGHT_MM:
        return NOT_MOUNTED
    if zone_blockers:
        return BLOCKED
    if max_height_mm and height_mm is not None and height_mm > max_height_mm:
        return TOO_HIGH
    return OK


def same_surface(kind, original_z_mm, candidate_slab_z_mm, candidate_ceiling_z_mm):
    """На новом месте та же поверхность установки (того же вида, на той же высоте)."""
    z = mount_z(kind, candidate_slab_z_mm, candidate_ceiling_z_mm)
    if z is None or original_z_mm is None:
        return False
    return abs(z - original_z_mm) <= SAME_SURFACE_MM


# ------------------------------------------------------------
# Поиск нового места
# ------------------------------------------------------------

def ring_offsets(step_mm, max_radius_mm):
    """
    Смещения (dx, dy) по возрастанию расстояния: кольца через step_mm до
    max_radius_mm, на каждом — точки не реже step_mm по окружности.
    """
    step = max(10.0, float(step_mm or 100.0))
    rings = int(float(max_radius_mm or 0.0) // step)
    for k in range(1, rings + 1):
        radius = k * step
        count = max(8, int(math.ceil(2.0 * math.pi * radius / step)))
        for i in range(count):
            angle = 2.0 * math.pi * i / count
            yield radius * math.cos(angle), radius * math.sin(angle)


def find_spot(x, y, obstacles, zone_radius_mm, z0, z1, step_mm, max_radius_mm,
              accept=None, max_checks=60):
    """
    Ближайшая к (x, y) точка, где зона доступа (круг zone_radius_mm в плане,
    высоты z0..z1) свободна от obstacles и которую принимает accept(x, y)
    (проверки по модели: внутри помещения, есть пол и та же поверхность
    установки). accept вызывается не больше max_checks раз — он дорогой.
    Возвращает (x, y) или None.
    """
    checks = 0
    for dx, dy in ring_offsets(step_mm, max_radius_mm):
        cx, cy = x + dx, y + dy
        if blockers(obstacles, cx, cy, zone_radius_mm, z0, z1):
            continue
        if accept is not None:
            if checks >= max_checks:
                return None
            checks += 1
            if not accept(cx, cy):
                continue
        return cx, cy
    return None


# ------------------------------------------------------------
# Тексты
# ------------------------------------------------------------

def _fill(template, **values):
    try:
        return unicode(template).format(**values)
    except Exception:
        return unicode(template) + u" " + u" ".join(values[k] for k in sorted(values))


def obstacle_names(obstacles, limit=3):
    """«Воздуховоды ×2, Трубы» — имена препятствий по частоте, не больше limit."""
    counts = {}
    order = []
    for obstacle in obstacles:
        name = obstacle.name or u"?"
        if name not in counts:
            order.append(name)
            counts[name] = 0
        counts[name] += 1
    first = dict((name, i) for i, name in enumerate(order))
    order.sort(key=lambda name: (-counts[name], first[name]))
    parts = [name if counts[name] == 1 else u"{} ×{}".format(name, counts[name])
             for name in order[:limit]]
    if len(order) > limit:
        parts.append(u"…")
    return u", ".join(parts)


def reason_text(status, zone_blockers, detector_blockers):
    """Почему нет доступа: «перекрыт: Воздуховоды» / «зона доступа: Трубы» / состояние."""
    if status == BLOCKED:
        if detector_blockers:
            return u"перекрыт: " + obstacle_names(detector_blockers)
        return u"зона доступа: " + obstacle_names(zone_blockers)
    return STATUS_TEXT.get(status, u"")


def blocked_label(template, reason):
    """Подпись у недоступного извещателя по шаблону ({r} — причина)."""
    return _fill(template or u"Нет доступа: {r}", r=reason)


def move_distance(dx_mm, dy_mm, step_mm=10.0):
    """Длина переноса в плане, округлённая до step_mm."""
    step = max(1.0, float(step_mm))
    return int(round(math.hypot(dx_mm, dy_mm) / step) * step)


def move_label(template, dx_mm, dy_mm):
    """Подпись переноса по шаблону ({d} — расстояние в плане, мм; направление — стрелка на плане)."""
    return _fill(template or u"Перенести ПИ на {d} мм", d=unicode(move_distance(dx_mm, dy_mm)))
