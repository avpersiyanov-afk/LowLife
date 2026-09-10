# -*- coding: utf-8 -*-
u"""
Сечение кабельного лотка с фактической раскладкой кабелей — общая логика
кнопки «Сечение лотка» (ToolsTraySection.panel/TraySection.pushbutton).

Портировано со скрипта Dynamo (тот же состав входных данных и оформление
таблицы), с тремя отличиями от оригинала:

  - Excel читается через lowlife.xlsx_io, а не openpyxl — openpyxl в
    IronPython 2 недоступен (нет pip), как и у остальных кнопок обмена с
    Excel (см. ScheduleToExcel/ScheduleFromExcel). Из-за этого числовые
    ячейки приходят как unicode-строки, не float/int — отсюда _to_float/
    _to_int ниже (в Dynamo это делал openpyxl сам). Нужный лист
    («сводные данные для плагина») ищется по имени среди многих листов
    книги (find_data_sheet, терпит регистр/пробелы/«пагина»); не нашёлся —
    script.py спрашивает список. Участок в read_cables протягивается вниз
    по объединённым ячейкам.

  - Раскладка кругов (arrange_cables) — не перебор по сетке с шагом
    radius/5 (плотность/скорость зависели от масштаба), а bottom-left-fill:
    каждый кабель (от большего диаметра к меньшему) кладётся в самую
    низкую из возможных точек покоя, при равной высоте — в самую левую.
    Точки-кандидаты — это готовые пары (x, y): у обеих стенок и над
    центром каждого уложенного круга (вертикальное падение, _drop_y);
    НА ПОЛУ вплотную к уложенному кругу сбоку (y=r) — без этого кандидата
    _drop_y «цепляется» за плечо соседа, отдаёт высоту больше, чем у
    дальней стенки, и раскладка разваливается на две кучи с пустотой
    посередине; и в седле между двумя близкими по X кругами (_pair_xy).
    Кабели, которым не хватило места по высоте лотка, возвращаются
    отдельным списком, а не молча пропадают.

  - Режим раскладки (настройка кнопки). Оба варианта группируют кабели
    по типам (original_mark) и раскладывают типы слева направо полками —
    чтобы разные типы не сваливались в одну кучу. Отличие только в форме
    блока одного типа: LAYOUT_SOLID — плотная bottom-left-fill куча
    (_arrange_solid_by_type, per-тип через arrange_cables);
    LAYOUT_HONEYCOMB — треугольная горка (_pyramid_offsets): 2 — рядом,
    3 — пирамидка, 4 — 3+1, дальше широкий низ и ряды по убыванию, как
    складывают трубы руками.

  - Перегородка СОУЭ РО (настройка кнопки): если divide_soue_ro, кабели
    системы «СОУЭ РО» (is_soue_ro) уходят в отдельный отсек лотка,
    отделённый вертикальной перегородкой; ширины отсеков — по доле
    площади кабелей (15..50% под СОУЭ РО). plan_section возвращает X
    осевой линии перегородки, draw_section её рисует.

  - Файл, участки (список с галочками — можно несколько), режим и точка
    вставки выбираются интерактивно (pyrevit.forms + PickPoint), а не
    через позиционные входы IN[..]. Режим: сечение+таблица / только
    сечение / только таблица — рисование разбито на plan_section (только
    раскладка), draw_section и draw_table, чтобы сечение и таблицу можно
    было положить на разные чертёжные виды (запустить кнопку дважды).
    Несколько участков строятся стопкой сверху вниз от одной точки,
    внахлёст не заходят.

  - Масштаб. Контур лотка и кружки — реальный размер (масштабируются
    видом). Таблица, подписи и зазоры между блоками — "бумажные" мм,
    умноженные на view.Scale (paper_to_model), поэтому одинаково
    читаются при любом масштабе вида и на видах с разным масштабом.
"""

import math

try:
    from collections import OrderedDict
except ImportError:
    OrderedDict = dict

from Autodesk.Revit.DB import (
    Arc, ElementId, ElementTypeGroup, HorizontalTextAlignment, Line,
    TextNote, TextNoteOptions, TextNoteType, VerticalTextAlignment, XYZ,
)

from lowlife.xlsx_io import read_xlsx, list_sheet_names

MM_TO_FEET = 1.0 / 304.8
SQRT3 = math.sqrt(3.0)
SHEET_NAME = u"Сводный"  # старое имя из скрипта Dynamo (запасной вариант)

LAYOUT_SOLID = u"solid"          # bottom-left-fill, кабели вперемешку
LAYOUT_HONEYCOMB = u"honeycomb"  # по типам, каждый тип — сотовым блоком

_BLOCK_GAP_MM = 3.0        # зазор между сотовыми блоками разных типов
PARTITION_GAP_MM = 5.0     # ширина перегородки между отсеками (СОУЭ РО)


def _norm_sheet(s):
    return u" ".join(s.lower().split())


def find_data_sheet(names):
    u"""Ищет лист со сводными данными для плагина среди имён листов книги
    (их там бывает много): без учёта регистра/лишних пробелов, терпит
    написание «плагина»/«пагина». Возвращает точное имя листа или None."""
    wanted = _norm_sheet(u"сводные данные для плагина")
    for n in names:
        nn = _norm_sheet(n)
        if nn == wanted:
            return n
    for n in names:
        nn = _norm_sheet(n)
        if u"свод" in nn and (u"плагин" in nn or u"пагин" in nn):
            return n
    for n in names:
        if _norm_sheet(n) == _norm_sheet(SHEET_NAME):
            return n
    return None

# Ниже — размеры "на бумаге" (мм готового чертежа). Контур лотка и кружки
# кабелей рисуются в реальном размере и масштабируются видом; а таблица,
# подписи и зазоры между блоками должны на бумаге выглядеть одинаково при
# любом масштабе вида — поэтому их умножают на view.Scale (paper_to_model).
SECTION_GAP_MM = 30.0    # вертикальный зазор между блоками, когда их строят стопкой
TITLE_BAND_MM = 8.0      # запас над лотком под подпись участка
_TITLE_GAP_MM = 4.0      # отступ от верха лотка до подписи
_ROW_MM = 5.0            # высота строки таблицы
_COL_MM = 22.0           # ширина колонок №/Система/Диаметр/Кол-во
_MARK_CHAR_MM = 2.2      # ширина колонки «Марка» на символ
_INSET_MM = 1.2          # отступ текста от левой линии колонки


def paper_to_model(mm, scale):
    u"""мм на бумаге -> футы в модели на чертёжном виде с масштабом 1:scale."""
    return mm_to_feet(mm) * scale


def mm_to_feet(mm):
    return mm * MM_TO_FEET


def feet_to_mm(feet):
    return feet * 304.8


def round_half_up(x):
    u"""Обычное инженерное округление (<0.5 вниз, >=0.5 вверх), не Python-овское banker's rounding."""
    return int(math.floor(x + 0.5))


def format_number(v):
    u"""123.0 -> "123", 123.4 -> "123.4" — без лишних ".0" в отчётах/подписях."""
    if v == int(v):
        return u"{:.0f}".format(v)
    return u"{:g}".format(v)


def _to_float(value, default=0.0):
    if value is None:
        return default
    try:
        return float(unicode(value).strip().replace(u",", u"."))
    except (TypeError, ValueError):
        return default


def _to_int(value, default=0):
    if value is None:
        return default
    try:
        return int(float(unicode(value).strip().replace(u",", u".")))
    except (TypeError, ValueError):
        return default


class CableData(object):
    __slots__ = (
        "original_mark", "mark", "diameter", "section", "system",
        "quantity", "fill_percent", "tray_width", "tray_height",
    )

    def __init__(self, mark, diameter, section, system=u"", quantity=1,
                 fill_percent=0.0, tray_width=0.0, tray_height=0.0):
        self.original_mark = unicode(mark).strip() if mark is not None else u""
        self.mark = self.original_mark
        self.diameter = _to_float(diameter)
        self.section = unicode(section).strip() if section is not None else u""
        self.system = unicode(system).strip() if system is not None else u""
        self.quantity = max(1, _to_int(quantity, default=1))
        self.fill_percent = _to_float(fill_percent)
        self.tray_width = _to_float(tray_width)
        self.tray_height = _to_float(tray_height)


def read_cables(path, sheet_name=None):
    u"""
    Читает лист sheet_name; если не задан — лист SHEET_NAME («Сводный»),
    а его нет — первый лист книги. Столбцы (0-based), как в исходном
    скрипте Dynamo:
      0 марка, 1 диаметр(мм), 2 участок, 3 кол-во, 5 система,
      6 % заполнения (справочно), 7 высота лотка(мм), 8 ширина лотка(мм).
    Столбец 4 в исходнике не задействован — оставлен пустым намеренно,
    чтобы не ломать уже существующие файлы выгрузки под этот формат.
    Первая строка — заголовок, пропускается.

    Участок протягивается вниз: если в строке кабеля ячейка «участок»
    пустая (обычно так выглядят объединённые по вертикали ячейки Excel —
    значение только в верхней строке блока), берётся последний
    непустой участок сверху.

    Возвращает (cables, error); error — текст ошибки или None.
    """
    if sheet_name is None:
        names = list_sheet_names(path)
        sheet_name = find_data_sheet(names) or (names[0] if names else None)

    rows = read_xlsx(path, sheet_name=sheet_name)

    if not rows or len(rows) < 2:
        return [], u"Лист пустой или не прочитался."

    def cell(row, i):
        return row[i] if i < len(row) else None

    cables = []
    last_section = u""
    for row in rows[1:]:
        if not row or cell(row, 0) is None:
            continue
        raw_section = cell(row, 2)
        section = unicode(raw_section).strip() if raw_section is not None else u""
        if section:
            last_section = section
        else:
            section = last_section
        cables.append(CableData(
            mark=cell(row, 0), diameter=cell(row, 1), section=section,
            quantity=cell(row, 3) or 1, system=cell(row, 5),
            fill_percent=cell(row, 6), tray_height=cell(row, 7), tray_width=cell(row, 8),
        ))

    return cables, None


def list_sections(cables):
    u"""Уникальные участки в порядке первого появления в файле."""
    seen_set = set()
    seen = []
    for c in cables:
        if c.section and c.section not in seen_set:
            seen_set.add(c.section)
            seen.append(c.section)
    return seen


def renumber_cables(cables):
    u"""Марка -> "1,2,3..." по порядку первого появления в переданном списке (как в Dynamo)."""
    mark_map = {}
    counter = 1
    for c in cables:
        if c.original_mark not in mark_map:
            mark_map[c.original_mark] = unicode(counter)
            counter += 1
        c.mark = mark_map[c.original_mark]


# ------------------------------------------------------------
# Укладка кругов (bottom-left-fill — см. докстринг модуля)
# ------------------------------------------------------------

_NEIGHBOR_WINDOW = 10  # сколько соседей по X пробовать в парах-опорах


class _Placed(object):
    __slots__ = ("cx", "cy", "r", "cable")

    def __init__(self, cx, cy, r, cable):
        self.cx = cx
        self.cy = cy
        self.r = r
        self.cable = cable


def _drop_y(x, r, placed):
    u"""Высота центра круга радиуса r при ВЕРТИКАЛЬНОМ падении в столбце x:
    пол (y=r) либо верх круга, оказавшегося под ним. Модель прямого
    падения — для кандидатов «у стены» и «над центром уже уложенного»."""
    y = r
    for p in placed:
        dx = x - p.cx
        reach = r + p.r
        if -reach < dx < reach:
            top = p.cy + math.sqrt(max(reach * reach - dx * dx, 0.0))
            if top > y:
                y = top
    return y


def _pair_xy(p, q, r):
    u"""Верхняя точка (x, y), где круг радиуса r касается сразу p и q
    (кабель, легший в седло между двумя уже уложенными). None — если
    такого положения нет."""
    dx0 = q.cx - p.cx
    dy0 = q.cy - p.cy
    d2 = dx0 * dx0 + dy0 * dy0
    if d2 < 1e-12:
        return None
    d = math.sqrt(d2)
    r1 = p.r + r
    r2 = q.r + r
    if d > r1 + r2 or d < abs(r1 - r2):
        return None
    a = (r1 * r1 - r2 * r2 + d2) / (2.0 * d)
    h2 = r1 * r1 - a * a
    if h2 < 0:
        return None
    h = math.sqrt(h2)
    ux, uy = dx0 / d, dy0 / d
    mx, my = p.cx + a * ux, p.cy + a * uy
    c1 = (mx - h * uy, my + h * ux)
    c2 = (mx + h * uy, my - h * ux)
    return c1 if c1[1] >= c2[1] else c2


def _fits(x, y, r, tray_w, tray_h, placed):
    if x - r < -1e-6 or x + r > tray_w + 1e-6:
        return False
    if y - r < -1e-6 or y + r > tray_h + 1e-6:
        return False
    for p in placed:
        min_dist = r + p.r - 1e-6
        if (x - p.cx) ** 2 + (y - p.cy) ** 2 < min_dist * min_dist:
            return False
    return True


def arrange_cables(cables, tray_width_mm, tray_height_mm):
    u"""
    Раскладывает по одному экземпляру каждого кабеля (Quantity штук
    каждой строки), от большего диаметра к меньшему — самые толстые
    кабели оказываются внизу лотка, как на реальных исполнительных
    чертежах. Возвращает (placed, unplaced): placed — список _Placed
    (позиции в футах относительно левого нижнего угла лотка), unplaced —
    кабели, для которых не нашлось места по высоте лотка.
    """
    tray_w = mm_to_feet(tray_width_mm)
    tray_h = mm_to_feet(tray_height_mm)

    all_cables = []
    for c in cables:
        all_cables.extend([c] * c.quantity)
    all_cables.sort(key=lambda c: c.diameter, reverse=True)

    placed = []
    unplaced = []

    for cable in all_cables:
        r = mm_to_feet(cable.diameter) / 2.0
        if r <= 0 or 2 * r > tray_w + 1e-6:
            unplaced.append(cable)
            continue

        # Кандидаты — готовые точки покоя (x, y), а не только x:
        #   • у обеих стенок — вертикальное падение (_drop_y);
        #   • над центром каждого уже уложенного круга — тоже падение;
        #   • НА ПОЛУ вплотную к уже уложенному кругу сбоку (y=r) — именно
        #     этой точки не хватало: _drop_y в такой x «цепляется» за плечо
        #     соседа и отдаёт высоту больше, чем у дальней стенки, поэтому
        #     кабель улетал к стенке и раскладка разваливалась на две кучи;
        #   • в седле между двумя близкими по X кругами (_pair_xy).
        cands = []
        for wx in (r, tray_w - r):
            cands.append((wx, _drop_y(wx, r, placed)))
        for p in placed:
            cx = min(max(p.cx, r), tray_w - r)
            cands.append((cx, _drop_y(cx, r, placed)))
            reach = r + p.r
            dyf = r - p.cy
            if -reach <= dyf <= reach:
                dxf = math.sqrt(max(reach * reach - dyf * dyf, 0.0))
                for fx in (p.cx - dxf, p.cx + dxf):
                    if r - 1e-6 <= fx <= tray_w - r + 1e-6:
                        cands.append((fx, r))

        by_x = sorted(placed, key=lambda p: p.cx)
        n = len(by_x)
        for i in range(n):
            for j in range(i + 1, min(i + 1 + _NEIGHBOR_WINDOW, n)):
                xy = _pair_xy(by_x[i], by_x[j], r)
                if xy and r - 1e-6 <= xy[0] <= tray_w - r + 1e-6 and xy[1] >= r - 1e-6:
                    cands.append(xy)

        # bottom-left-fill: ниже — лучше, при равной высоте — левее; берём
        # первую точку, которая помещается.
        best = None
        for x, y in sorted(cands, key=lambda c: (c[1], c[0])):
            x = min(max(x, r), tray_w - r)
            if y + r > tray_h + 1e-6:
                continue
            if _fits(x, y, r, tray_w, tray_h, placed):
                best = (x, y)
                break

        if best is None:
            unplaced.append(cable)
            continue

        placed.append(_Placed(best[0], best[1], r, cable))

    return placed, unplaced


def _group_by_type(cables):
    u"""Списки CableData по типам (original_mark); тип с самым толстым
    кабелем — первым, внутри группы — порядок как во входе."""
    groups = OrderedDict()
    for c in cables:
        groups.setdefault(c.original_mark, []).append(c)
    return sorted(groups.values(), key=lambda g: (-g[0].diameter, g[0].original_mark))


def _expand(cables):
    out = []
    for c in cables:
        out.extend([c] * c.quantity)
    return out


def _pyramid_offsets(n, r, avail_w, avail_h):
    u"""Смещения (dx, dy) центров n кругов радиуса r в треугольной горке:
    широкий низ, каждый ряд на 1 короче, верхний (неполный) ряд — по
    центру; ряды со сдвигом на радиус, шаг по высоте r*SQRT3. Так руками
    и складывают трубы/кабели: 2 — рядом, 3 — пирамидкой, 4 — 3 и 1
    сверху и т.д. Кладёт столько, сколько влезает в avail_w x avail_h;
    возвращает (offsets, block_w, block_h)."""
    if n <= 0 or r <= 0:
        return [], 0.0, 0.0

    # низ горки b: минимальное треугольное число >= n
    b = 1
    while b * (b + 1) // 2 < n:
        b += 1
    b = min(b, max(1, int((avail_w + 1e-9) / (2.0 * r))))       # не шире отсека
    max_rows = max(1, int((avail_h - 2.0 * r) / (r * SQRT3) + 1e-9) + 1)  # не выше отсека

    def capacity(bb, rows):
        rows = min(rows, bb)
        return rows * bb - rows * (rows - 1) // 2

    b_lim = max(1, int((avail_w + 1e-9) / (2.0 * r)))
    while capacity(b, max_rows) < n and b < b_lim:
        b += 1

    remaining = n
    rows = []
    w = b
    while remaining > 0 and w > 0 and len(rows) < max_rows:
        take = min(w, remaining)
        rows.append(take)
        remaining -= take
        w -= 1

    offsets = []
    for j, cnt in enumerate(rows):
        full = b - j
        # неполный верхний ряд центрируем, но сдвигом кратным 2r — иначе
        # он встаёт РОВНО над нижним рядом (тот же x) вместо сёдел -> нахлёст
        base_x = r + j * r + ((full - cnt) // 2) * 2.0 * r
        y = r + j * r * SQRT3
        for k in range(cnt):
            offsets.append((base_x + k * 2.0 * r, y))

    block_w = 2.0 * r * b
    block_h = 2.0 * r + (len(rows) - 1) * r * SQRT3
    return offsets, block_w, block_h


def _shelf_pack(groups, tray_w, tray_h, block_fn):
    u"""Общая раскладка блоков по типам полками слева направо; block_fn(g,
    avail_w) -> (offsets, block_w, block_h) относительно левого нижнего
    угла блока."""
    gap = mm_to_feet(_BLOCK_GAP_MM)
    placed, unplaced = [], []
    shelf_x = shelf_y = shelf_h = 0.0

    for g in groups:
        r = mm_to_feet(g[0].diameter) / 2.0
        inst = _expand(g)
        if r <= 0 or 2.0 * r > tray_w + 1e-6:
            unplaced.extend(inst)
            continue

        avail_w = tray_w - shelf_x if shelf_x > 1e-9 else tray_w
        offs, bw, bh = block_fn(inst, r, avail_w, tray_h - shelf_y)
        if shelf_x > 1e-9 and (not offs or shelf_x + bw > tray_w + 1e-6):
            shelf_y += shelf_h + gap
            shelf_x = shelf_h = 0.0
            offs, bw, bh = block_fn(inst, r, tray_w, tray_h - shelf_y)

        if not offs or shelf_y + bh > tray_h + 1e-6:
            unplaced.extend(inst)
            continue

        for idx, (dx, dy) in enumerate(offs):
            placed.append(_Placed(shelf_x + dx, shelf_y + dy, r, inst[idx]))
        if len(offs) < len(inst):
            unplaced.extend(inst[len(offs):])
        shelf_x += bw + gap
        shelf_h = max(shelf_h, bh)

    return placed, unplaced


def _arrange_honeycomb(cables, tray_width_mm, tray_height_mm):
    u"""«Сотами по типам»: каждый тип — треугольной горкой (_pyramid_offsets),
    горки идут слева направо полками, при нехватке ширины — новая полка выше."""
    tray_w = mm_to_feet(tray_width_mm)
    tray_h = mm_to_feet(tray_height_mm)

    def block_fn(inst, r, avail_w, avail_h):
        return _pyramid_offsets(len(inst), r, avail_w, avail_h)

    return _shelf_pack(_group_by_type(cables), tray_w, tray_h, block_fn)


def _arrange_solid_by_type(cables, tray_width_mm, tray_height_mm):
    u"""«Сплошняком, но по типам»: каждый тип плотно упаковывается
    bottom-left-fill (arrange_cables) в свою КОМПАКТНУЮ полосу справа от
    предыдущей — чтобы типы не сваливались в одну кучу и не растекались
    по всему дну лотка одним рядом. Ширина полосы типа — по числу
    кабелей и высоте лотка (примерно квадратная куча, но не ниже, чем
    нужно, чтобы всё уместилось)."""
    tray_w = mm_to_feet(tray_width_mm)
    gap = mm_to_feet(_BLOCK_GAP_MM)

    placed, unplaced = [], []
    x_cursor = 0.0
    for g in _group_by_type(cables):
        d = g[0].diameter
        n = sum(c.quantity for c in g)
        remaining_mm = feet_to_mm(tray_w - x_cursor)
        if remaining_mm <= 0 or d <= 0 or n <= 0:
            unplaced.extend(_expand(g))
            continue

        rows_avail = max(1, int(tray_height_mm / d))
        cols = max(1, int(math.ceil(n / float(rows_avail))), int(math.ceil(math.sqrt(n))))
        region_mm = min(remaining_mm, max(d, cols * d * 1.15))

        sub_placed, sub_un = arrange_cables(g, region_mm, tray_height_mm)
        right = x_cursor
        for p in sub_placed:
            p.cx += x_cursor
            right = max(right, p.cx + p.r)
        placed.extend(sub_placed)
        unplaced.extend(sub_un)
        x_cursor = right + gap

    return placed, unplaced


def _pack_region(cables, region_width_mm, region_height_mm, layout):
    if layout == LAYOUT_HONEYCOMB:
        return _arrange_honeycomb(cables, region_width_mm, region_height_mm)
    return _arrange_solid_by_type(cables, region_width_mm, region_height_mm)


def is_soue_ro(system):
    u"""True для системы «СОУЭ РО» (в любом написании: «СОУЭ РО», «СОУЭ-РО»,
    «СОУЭ(РО)»…). Такие кабели по требованию кладут в отдельный отсек лотка."""
    n = u"".join(ch for ch in (system or u"").lower() if ch.isalnum())
    return n.startswith(u"соуэро")


def group_for_table(placed):
    u"""Кабели placed, сгруппированные по (марка, система, диаметр) — строки сводной таблицы."""
    counts = {}
    order = []
    for p in placed:
        key = (p.cable.mark, p.cable.system, p.cable.diameter, p.cable.original_mark)
        if key not in counts:
            counts[key] = 0
            order.append(key)
        counts[key] += 1

    rows = []
    for mark, system, diameter, original_mark in order:
        rows.append({
            "number": mark, "system": system, "mark": original_mark,
            "diameter": diameter, "count": counts[(mark, system, diameter, original_mark)],
        })
    return sorted(rows, key=lambda row: int(row["number"]) if row["number"].isdigit() else 0)


# ------------------------------------------------------------
# Построение геометрии на чертёжном виде
# ------------------------------------------------------------

def _text_note_type_id(doc):
    type_id = doc.GetDefaultElementTypeId(ElementTypeGroup.TextNoteType)
    if type_id == ElementId.InvalidElementId:
        default_type = TextNoteType.GetDefaultTextNoteType(doc)
        type_id = default_type.Id if default_type else ElementId.InvalidElementId
    return type_id


def _draw_outline(doc, view, insertion_point, tray_w_ft, tray_h_ft):
    corners = [
        insertion_point,
        XYZ(insertion_point.X + tray_w_ft, insertion_point.Y, 0),
        XYZ(insertion_point.X + tray_w_ft, insertion_point.Y + tray_h_ft, 0),
        XYZ(insertion_point.X, insertion_point.Y + tray_h_ft, 0),
    ]
    for i in range(4):
        doc.Create.NewDetailCurve(view, Line.CreateBound(corners[i], corners[(i + 1) % 4]))


def _draw_cables(doc, view, insertion_point, placed, text_type_id, show_marks):
    opts = TextNoteOptions(text_type_id)
    opts.HorizontalAlignment = HorizontalTextAlignment.Center
    opts.VerticalAlignment = VerticalTextAlignment.Middle

    for p in placed:
        center = XYZ(insertion_point.X + p.cx, insertion_point.Y + p.cy, 0)
        circle = Arc.Create(center, p.r, 0, 2 * math.pi, XYZ.BasisX, XYZ.BasisY)
        doc.Create.NewDetailCurve(view, circle)
        if show_marks:
            TextNote.Create(doc, view.Id, center, p.cable.mark, opts)


def _fill_percent(placed, tray_width_mm, tray_height_mm):
    tray_area = tray_width_mm * tray_height_mm
    placed_area = sum(math.pi * (feet_to_mm(p.r)) ** 2 for p in placed)
    return (placed_area / tray_area * 100.0) if tray_area > 0 else 0.0


def plan_section(cables, tray_width_mm, tray_height_mm,
                 layout=LAYOUT_SOLID, divide_soue_ro=False):
    u"""Раскладка без рисования.

    layout — LAYOUT_SOLID (вперемешку, bottom-left-fill) или
    LAYOUT_HONEYCOMB (по типам, сотами).
    divide_soue_ro — кабели системы «СОУЭ РО» (is_soue_ro) кладутся в
    отдельный отсек лотка, отделённый перегородкой от остальных; ширина
    отсеков — по доле площади кабелей (15..50% под СОУЭ РО).

    Возвращает (placed, unplaced, fill_percent, partition_x_ft):
    partition_x_ft — X осевой линии перегородки от левой стенки лотка
    (в футах) либо None, если перегородки нет.
    """
    partition_x_ft = None

    ro = [c for c in cables if is_soue_ro(c.system)] if divide_soue_ro else []
    ro_ids = set(id(c) for c in ro)
    rest = [c for c in cables if id(c) not in ro_ids] if ro else cables

    if ro and rest:
        gap_mm = PARTITION_GAP_MM
        usable = max(0.0, tray_width_mm - gap_mm)

        def _area(cs):
            return sum(math.pi * (c.diameter / 2.0) ** 2 * c.quantity for c in cs)

        a_ro, a_rest = _area(ro), _area(rest)
        frac = (a_ro / (a_ro + a_rest)) if (a_ro + a_rest) > 0 else 0.3
        frac = min(0.5, max(0.15, frac))
        w_ro = usable * frac
        w_rest = usable - w_ro

        placed_rest, un_rest = _pack_region(rest, w_rest, tray_height_mm, layout)
        placed_ro, un_ro = _pack_region(ro, w_ro, tray_height_mm, layout)
        dx = mm_to_feet(w_rest + gap_mm)
        for p in placed_ro:
            p.cx += dx
        placed = placed_rest + placed_ro
        unplaced = un_rest + un_ro
        partition_x_ft = mm_to_feet(w_rest + gap_mm / 2.0)
    else:
        placed, unplaced = _pack_region(cables, tray_width_mm, tray_height_mm, layout)

    return placed, unplaced, _fill_percent(placed, tray_width_mm, tray_height_mm), partition_x_ft


def draw_section(doc, view, section_name, tray_width_mm, tray_height_mm,
                 placed, insertion_point, show_marks=True, scale=1.0, partition_x_ft=None):
    u"""Контур лотка (реальный размер — масштабируется видом) + подпись
    участка над ним + кружки кабелей из placed + перегородка отсека
    (если partition_x_ft задан). insertion_point — левый нижний угол
    лотка. Вызывать в транзакции."""
    tray_w_ft = mm_to_feet(tray_width_mm)
    tray_h_ft = mm_to_feet(tray_height_mm)
    text_type_id = _text_note_type_id(doc)

    _draw_outline(doc, view, insertion_point, tray_w_ft, tray_h_ft)

    if partition_x_ft is not None:
        half = mm_to_feet(PARTITION_GAP_MM) / 2.0
        for px in (partition_x_ft - half, partition_x_ft + half):
            x = insertion_point.X + px
            doc.Create.NewDetailCurve(view, Line.CreateBound(
                XYZ(x, insertion_point.Y, 0), XYZ(x, insertion_point.Y + tray_h_ft, 0)))

    if section_name:
        opts = TextNoteOptions(text_type_id)
        opts.HorizontalAlignment = HorizontalTextAlignment.Center
        opts.VerticalAlignment = VerticalTextAlignment.Bottom
        TextNote.Create(doc, view.Id, XYZ(
            insertion_point.X + tray_w_ft / 2.0,
            insertion_point.Y + tray_h_ft + paper_to_model(_TITLE_GAP_MM, scale), 0
        ), section_name, opts)

    _draw_cables(doc, view, insertion_point, placed, text_type_id, show_marks)


def draw_table(doc, view, section_name, tray_width_mm, tray_height_mm,
               placed, fill_percent, top_left, scale=1.0):
    u"""Сводная таблица (марка/система/диаметр/кол-во) + строки про
    заполнение и размер лотка. Размеры — "бумажные" (умножены на scale),
    чтобы таблица одинаково читалась при любом масштабе вида. top_left —
    левый ВЕРХНИЙ угол таблицы. Возвращает Y самой нижней нарисованной
    точки. Вызывать в транзакции."""
    rows = group_for_table(placed)
    text_type_id = _text_note_type_id(doc)

    row_h = paper_to_model(_ROW_MM, scale)
    inset = paper_to_model(_INSET_MM, scale)
    start_x, start_y = top_left.X, top_left.Y

    max_mark_len = max([len(r["mark"]) for r in rows]) if rows else 5
    col_w = [
        paper_to_model(_COL_MM, scale),
        paper_to_model(_COL_MM, scale),
        paper_to_model(max(max_mark_len, 5) * _MARK_CHAR_MM, scale),
        paper_to_model(_COL_MM, scale),
        paper_to_model(_COL_MM, scale),
    ]

    opts = TextNoteOptions(text_type_id)
    opts.HorizontalAlignment = HorizontalTextAlignment.Left
    opts.VerticalAlignment = VerticalTextAlignment.Middle

    def put(col, row_idx, text):
        x = start_x + sum(col_w[:col]) + inset
        y = start_y - row_idx * row_h - row_h / 2.0
        TextNote.Create(doc, view.Id, XYZ(x, y, 0), text, opts)

    if section_name:
        title_opts = TextNoteOptions(text_type_id)
        title_opts.HorizontalAlignment = HorizontalTextAlignment.Left
        title_opts.VerticalAlignment = VerticalTextAlignment.Bottom
        TextNote.Create(
            doc, view.Id, XYZ(start_x, start_y + paper_to_model(1.5, scale), 0),
            u"Сводная таблица кабелей на участке {}".format(section_name), title_opts
        )

    headers = [u"№", u"Система", u"Марка", u"Диаметр, мм", u"Кол-во"]
    for col, header in enumerate(headers):
        put(col, 0, header)
    for row_idx, row in enumerate(rows, 1):
        put(0, row_idx, row["number"])
        put(1, row_idx, row["system"])
        put(2, row_idx, row["mark"])
        put(3, row_idx, u"{:.1f}".format(row["diameter"]))
        put(4, row_idx, unicode(row["count"]))

    total_width = sum(col_w)
    total_rows = len(rows) + 1
    bottom_y = start_y - total_rows * row_h

    for i in range(total_rows + 1):
        y = start_y - i * row_h
        doc.Create.NewDetailCurve(view, Line.CreateBound(XYZ(start_x, y, 0), XYZ(start_x + total_width, y, 0)))

    xs = [start_x + sum(col_w[:i]) for i in range(len(col_w) + 1)]
    for x in xs:
        doc.Create.NewDetailCurve(view, Line.CreateBound(XYZ(x, start_y, 0), XYZ(x, bottom_y, 0)))

    info_y1 = bottom_y - row_h * 0.7
    info_y2 = info_y1 - row_h
    info_opts = TextNoteOptions(text_type_id)
    info_opts.HorizontalAlignment = HorizontalTextAlignment.Left
    info_opts.VerticalAlignment = VerticalTextAlignment.Middle
    TextNote.Create(doc, view.Id, XYZ(start_x + inset, info_y1, 0),
                     u"Заполнение лотка: {}%".format(round_half_up(fill_percent)), info_opts)
    TextNote.Create(doc, view.Id, XYZ(start_x + inset, info_y2, 0),
                     u"Размер лотка: {}×{} мм".format(format_number(tray_width_mm), format_number(tray_height_mm)),
                     info_opts)

    return info_y2 - row_h * 0.5
