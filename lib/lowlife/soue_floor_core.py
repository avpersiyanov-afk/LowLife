# -*- coding: utf-8 -*-
"""
Чистая логика кнопки «СОУЭ — расстановка типовой этаж»
(SOUE.panel/PlaceTypicalFloor) без Revit API — покрыта тестами
(tests/test_soue_floor_core.py). Revit-часть — soue_floor.py.

Координаты — в одной системе (футы, план XY), какие именно — решает
вызывающий код (soue_floor.py работает в координатах связи).
"""

import math
import re

from lowlife.ss1_easy_core import normalize, split_names  # noqa: F401 — реэкспорт

try:
    _to_text = unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3 (тесты)
    _to_text = str

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")

# Роли помещений: квартира (одно помещение на лот) и любое другое помещение
# объекта (оповещатели по акустическому расчёту).
ROLE_APARTMENT = "apartment"
ROLE_ROOM = "room"
ROLES = (ROLE_APARTMENT, ROLE_ROOM)

# Способ установки.
MOUNT_WALL = "wall"
MOUNT_CEILING = "ceiling"

# ------------------------------------------------------------
# Исходные данные расчёта («Расчёт СОУЭ.xlsx», лист «Справочник»)
# ------------------------------------------------------------

# Превышение уровня оповещения над шумом, ослабление на границе ШДН (1 кГц),
# ослабление через препятствие, высота расчётной точки над полом.
EXCESS_DB = 15.0
DN_LOSS_DB = 6.0
OBSTACLE_DB = 0.0
CALC_HEIGHT_M = 1.5

# Категории помещений и уровень звука постоянного шума N, дБА («Стандарт на
# проектные решения по слаботочным системам», разд. 3.3.4).
CATEGORY_APARTMENT = u"Помещения лотов (квартир/апартаментов)"
CATEGORY_MOP = u"МОП"
NOISE_CATEGORIES = [
    (CATEGORY_APARTMENT, 40.0),
    (CATEGORY_MOP, 50.0),
    (u"ПСН (торговля/ретейл)", 60.0),
    (u"ПСН (кафе, рестораны)", 65.0),
    (u"Санитарно-бытовые помещения", 50.0),
    (u"Технические помещения вентмашин и насосных", 80.0),
    (u"Технические помещения серверных и кроссовых", 65.0),
    (u"Склады, кладовые и подсобные помещения, ПУИ", 55.0),
    (u"Парковки", 70.0),
    (u"Помещения диспетчерских служб", 70.0),
    (u"Помещения УК (принято как МОП, требует согласования)", 50.0),
]

# Части имени помещения → категория (проверяются по порядку, первая
# подходящая). Только подсказка для новой строки таблицы — пользователь
# проверяет и правит.
CATEGORY_KEYWORDS = [
    (u"Парковки", [u"паркинг", u"автостоян", u"стоянк", u"парковк", u"рамп"]),
    (u"Технические помещения вентмашин и насосных",
     [u"венткамер", u"вентиляцион", u"насосн", u"итп", u"тепловой пункт", u"тепловой узел",
      u"дгу", u"дизел", u"холодильн", u"чиллер", u"компрессор"]),
    (u"Технические помещения серверных и кроссовых",
     [u"сервер", u"кроссов", u"слаботоч", u"щитов", u"грщ", u"аппаратн", u"связи", u"трансформатор"]),
    (u"Помещения диспетчерских служб", [u"диспетчер", u"охран", u"пожарн", u"цпу"]),
    (u"Помещения УК (принято как МОП, требует согласования)", [u"управляющ", u"ук "]),
    (u"ПСН (кафе, рестораны)", [u"кафе", u"ресторан", u"столов", u"бар ", u"кухня ресторан"]),
    (u"ПСН (торговля/ретейл)", [u"псн", u"магазин", u"торгов", u"коммерч", u"свободного назначения", u"офис"]),
    (u"Санитарно-бытовые помещения",
     [u"санузел", u"сан. узел", u"с/у", u"су ", u"туалет", u"уборная", u"душ", u"умывальн", u"мма"]),
    (u"Склады, кладовые и подсобные помещения, ПУИ",
     [u"кладов", u"склад", u"пуи", u"уборочн", u"подсобн", u"хозяйств", u"мусор", u"инвентар"]),
    (CATEGORY_APARTMENT,
     [u"прихож", u"кухн", u"спальн", u"гостин", u"комнат", u"жилая", u"гардеробн", u"детская"]),
    (CATEGORY_MOP,
     [u"коридор", u"холл", u"лифт", u"вестибюл", u"лестни", u"тамбур", u"лобби", u"колясочн",
      u"фойе", u"моп", u"переход", u"галере", u"шлюз", u"зона ожидани", u"консьерж"]),
]

# Части имени, при которых помещение по умолчанию исключается (новая строка
# таблицы): шахты, каналы, ниши, открытые пространства.
EXCLUDE_KEYWORDS = [u"шахт", u"канал", u"ниш", u"лоджи", u"балкон", u"террас", u"кровл",
                    u"техпростр", u"подполь", u"чердак"]


def category_noise(category):
    """Уровень шума категории или None."""
    wanted = normalize(category)
    for name, noise in NOISE_CATEGORIES:
        if normalize(name) == wanted:
            return noise
    return None


def match_category(text):
    """Категория из справочника по тексту (без учёта регистра; можно начало имени) или None."""
    wanted = normalize(text)
    if not wanted:
        return None
    for name, _ in NOISE_CATEGORIES:
        if normalize(name) == wanted:
            return name
    for name, _ in NOISE_CATEGORIES:
        if normalize(name).startswith(wanted):
            return name
    return None


def guess_category(room_name):
    """Категория по части имени помещения (CATEGORY_KEYWORDS) или None."""
    text = u" " + normalize(room_name) + u" "
    for category, keywords in CATEGORY_KEYWORDS:
        for keyword in keywords:
            if keyword in text:
                return category
    return None


def guess_exclude(room_name):
    text = normalize(room_name)
    return any(keyword in text for keyword in EXCLUDE_KEYWORDS)


def parse_number(text):
    """Число из текста («1,5 Вт», «87 дБ», 50) или None."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    match = _NUMBER.search(_to_text(text).replace(u",", u"."))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def parse_numbers(text):
    """Все числа из текста: «1,5 / 3 / 6 Вт» → [1.5, 3.0, 6.0]; число → [число]."""
    if text is None:
        return []
    if isinstance(text, (int, float)):
        return [float(text)]
    raw = _to_text(text)
    # «1,5 / 3» — запятая как десятичный разделитель только между цифрами
    raw = re.sub(r"(?<=\d),(?=\d)", u".", raw)
    return [float(m) for m in _NUMBER.findall(raw)]


# Исполнение оповещателя.
KIND_WALL = "wall"
KIND_CEILING = "ceiling"
KIND_PENDANT = "pendant"

_KIND_WORDS = [
    (KIND_PENDANT, [u"подвес", u"pendant"]),
    (KIND_CEILING, [u"потол", u"ceiling", u"встраив"]),
    (KIND_WALL, [u"настен", u"стен", u"wall"]),
]


def speaker_kind(*texts):
    """
    Исполнение по тексту (значение параметра «исполнение», имя семейства,
    имя типа — по порядку, первое распознанное): KIND_* или None.
    """
    for text in texts:
        value = normalize(text)
        if not value:
            continue
        for kind, words in _KIND_WORDS:
            if any(word in value for word in words):
                return kind
    return None


def parse_flag(text):
    """«да», «yes», «1», «x», «+», True → True."""
    if text is True:
        return True
    return normalize(text) in (u"да", u"yes", u"y", u"1", u"x", u"х", u"+", u"true", u"исключить")


# ------------------------------------------------------------
# Таблица помещений объекта: имя → категория, шум, исключить
# ------------------------------------------------------------

class RoomRow(object):
    """Строка таблицы уникальных имён помещений."""

    def __init__(self, name, count=0, category=u"", noise=None, exclude=False):
        self.name = name
        self.count = count
        self.category = category or u""
        self.noise = noise
        self.exclude = bool(exclude)

    @property
    def key(self):
        return normalize(self.name)

    def effective_noise(self):
        """Шум: заданный вручную, иначе — по категории, иначе None."""
        if self.noise is not None:
            return self.noise
        return category_noise(self.category)

    def to_dict(self):
        return {"name": self.name, "category": self.category, "noise": self.noise,
                "exclude": self.exclude}


def table_from_saved(saved):
    """{ключ: dict} из настроек → {ключ: RoomRow}."""
    result = {}
    for key, item in (saved or {}).items():
        try:
            result[key] = RoomRow(item.get("name") or key, 0, item.get("category") or u"",
                                  parse_number(item.get("noise")), item.get("exclude"))
        except Exception:
            continue
    return result


def table_to_saved(rows):
    return dict((row.key, row.to_dict()) for row in rows)


def merge_room_table(saved_rows, counts):
    """
    Таблица для показа/выгрузки: все имена объекта (counts — {имя: число
    помещений}) с сохранёнными значениями; у новых имён категория и
    «исключить» угаданы по имени (guess_category/guess_exclude). Имена,
    которых в объекте уже нет, но что-то заполнено, остаются в конце (count 0).
    Возвращает [RoomRow], отсортированный по имени.
    """
    rows = {}
    for name, count in counts.items():
        key = normalize(name)
        if not key:
            continue
        old = saved_rows.get(key)
        if key in rows:
            rows[key].count += count
            continue
        if old is not None:
            rows[key] = RoomRow(name, count, old.category, old.noise, old.exclude)
        else:
            rows[key] = RoomRow(name, count, guess_category(name) or u"", None, guess_exclude(name))
    for key, old in saved_rows.items():
        if key not in rows and (old.category or old.noise is not None or old.exclude):
            rows[key] = RoomRow(old.name, 0, old.category, old.noise, old.exclude)
    return sorted(rows.values(), key=lambda row: (row.count == 0, normalize(row.name)))


TABLE_HEADER = [u"Помещение", u"Кол-во", u"Категория", u"Шум N, дБА", u"Исключить"]


def table_to_sheet(rows):
    """[RoomRow] → строки листа Excel (заголовок + данные + справочник справа)."""
    sheet = [TABLE_HEADER + [u"", u"Категории (справочник)", u"N, дБА"]]
    for index, row in enumerate(rows):
        line = [row.name, row.count, row.category,
                row.noise if row.noise is not None else None,
                u"да" if row.exclude else u""]
        if index < len(NOISE_CATEGORIES):
            line += [u"", NOISE_CATEGORIES[index][0], NOISE_CATEGORIES[index][1]]
        sheet.append(line)
    for index in range(len(rows), len(NOISE_CATEGORIES)):
        sheet.append([None] * 5 + [u"", NOISE_CATEGORIES[index][0], NOISE_CATEGORIES[index][1]])
    return sheet


def table_from_sheet(sheet):
    """
    Строки листа Excel → [RoomRow]. Столбцы ищутся по заголовку (первая
    строка): «Помещение», «Категория», «Шум», «Исключить». Категория
    сопоставляется со справочником (можно начало названия); неизвестная
    оставляется как есть. Шум пустой — берётся по категории при расчёте.
    """
    if not sheet:
        return []
    header = [normalize(cell) for cell in sheet[0]]

    def column(*prefixes):
        for index, title in enumerate(header):
            if any(title.startswith(prefix) for prefix in prefixes):
                return index
        return None

    name_col = column(u"помещение", u"имя")
    if name_col is None:
        return []
    category_col = column(u"категория")
    noise_col = column(u"шум", u"n,", u"уровень")
    exclude_col = column(u"исключ")

    def cell(line, index):
        if index is None or index >= len(line):
            return None
        return line[index]

    rows = []
    for line in sheet[1:]:
        name = cell(line, name_col)
        if name is None or not _to_text(name).strip():
            continue
        category = cell(line, category_col)
        category_text = _to_text(category).strip() if category is not None else u""
        rows.append(RoomRow(
            _to_text(name).strip(), 0,
            match_category(category_text) or category_text,
            parse_number(cell(line, noise_col)),
            parse_flag(cell(line, exclude_col))))
    return rows


def name_rank(name, names):
    """Место имени помещения в списке names (без учёта регистра) или None."""
    wanted = normalize(name)
    for index, candidate in enumerate(names):
        if normalize(candidate) == wanted:
            return index
    return None


def classify_rooms(rooms, apartment_names, excluded=()):
    """
    Какие помещения оснащаются и как.

    rooms — [(ключ, имя помещения, имя лота, отметка или None)];
    excluded — нормализованные имена исключённых помещений.

    Квартиры: в каждом лоте — одно помещение из apartment_names (список по
    приоритету: «Прихожая, Холл» — сначала прихожая, нет её — холл), из
    равных по приоритету — с минимальной отметкой (у двухуровневой
    квартиры — нижнее); остальные помещения лота квартиры не оснащаются.
    Помещение из списка квартир без имени лота ставится само по себе — с
    предупреждением (ключ в no_lot).

    Остальные помещения объекта (не в лоте квартиры, не исключённые) —
    ROLE_ROOM: оповещатели по акустическому расчёту.

    Возвращает (назначения {ключ: роль}, no_lot [ключи]).
    """
    excluded = set(excluded)
    groups = {}
    no_lot = []
    for key, name, lot, elevation in rooms:
        if normalize(name) in excluded:
            continue
        rank = name_rank(name, apartment_names)
        if rank is None:
            continue
        lot_norm = normalize(lot)
        if not lot_norm:
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
        if key in result or normalize(name) in excluded:
            continue
        if normalize(lot) in apartment_lots:
            continue
        result[key] = ROLE_ROOM
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
# Акустический расчёт (методика из «Расчёт СОУЭ.xlsx»)
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


def room_reach(spl_db, power_w, noise_dba, mount_h):
    """acoustic_reach с постоянными расчёта (EXCESS_DB, DN_LOSS_DB, ...)."""
    return acoustic_reach(spl_db, power_w, noise_dba, EXCESS_DB, DN_LOSS_DB, OBSTACLE_DB,
                          mount_h, CALC_HEIGHT_M)


def sample_step(width, height, base, max_samples=1500):
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


def coverage_pairs(candidates, samples, max_reach, grid=None, wall=False):
    """
    Как coverage, но один раз на наибольшую дальность: для каждого кандидата
    — [(индекс точки, расстояние в плане)] точек не дальше max_reach (в
    прямой видимости, у настенного — перед стеной). Наборы для меньших
    дальностей — sets_within.
    """
    reach2 = max_reach * max_reach
    result = []
    for cand in candidates:
        cx, cy = cand[0], cand[1]
        pairs = []
        for index, (px, py) in enumerate(samples):
            dx, dy = px - cx, py - cy
            d2 = dx * dx + dy * dy
            if d2 > reach2:
                continue
            if wall and dx * cand[2] + dy * cand[3] < -1e-6:
                continue
            if grid is not None and not grid.visible(cx, cy, px, py):
                continue
            pairs.append((index, math.sqrt(d2)))
        result.append(pairs)
    return result


def sets_within(pairs, reach):
    """Наборы озвучиваемых точек для дальности reach из coverage_pairs."""
    return [set(index for index, distance in item if distance <= reach) for item in pairs]


def option_score(uncovered, count, power_w):
    """
    Ключ выбора варианта (меньше — лучше): сначала меньше неозвученных
    точек, потом меньше оповещателей, потом меньше суммарная мощность
    (нагрузка на усилитель), потом меньше мощность одного.
    """
    return (uncovered, count, round(count * power_w, 6), power_w)


def reduce_options(options):
    """
    Варианты [(ключ, мощность, дальность)] без заведомо худших: при той же
    или большей мощности и не большей дальности вариант не нужен.
    Порядок — по убыванию дальности.
    """
    kept = []
    for option in sorted(options, key=lambda o: (-o[2], o[1])):
        if any(other[1] <= option[1] and other[2] >= option[2] for other in kept):
            continue
        kept.append(option)
    return kept


def column_faces(min_x, min_y, max_x, max_y):
    """Грани колонны по её габариту в плане: [(x1, y1, x2, y2, nx, ny)], нормали наружу."""
    return [
        (min_x, min_y, max_x, min_y, 0.0, -1.0),
        (max_x, min_y, max_x, max_y, 1.0, 0.0),
        (max_x, max_y, min_x, max_y, 0.0, 1.0),
        (min_x, max_y, min_x, min_y, -1.0, 0.0),
    ]


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
