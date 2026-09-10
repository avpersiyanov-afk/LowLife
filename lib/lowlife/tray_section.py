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
    _to_int ниже (в Dynamo это делал openpyxl сам). Лист по имени не
    угадываем (в Dynamo был жёсткий «Сводный» / активный лист) — script.py
    спрашивает лист, если их в книге несколько. Участок в read_cables
    протягивается вниз по объединённым ячейкам.

  - Раскладка кругов (arrange_cables) — не перебор по сетке с шагом
    radius/5 (итоговая плотность/скорость зависели от масштаба лотка и
    кабеля, а сам подбор мог давать кабели, которые визуально не
    касаются друг друга или пола), а точная «гравитационная» укладка:
    каждый следующий кабель (от большего диаметра к меньшему) ищет
    самую низкую точку, где он касается пола, стенки или уже уложенного
    кабеля, и не пересекает ничего. Кандидаты X для этой точки — обе
    стенки лотка, X над каждым уже уложенным кругом, X, где новый круг
    одновременно касается пола И одного уже уложенного круга (без этого
    кабели ложились только "точно сверху" соседа или у стены, оставляя
    большие пустые клинья между кабелями на полу), и точки одновременного
    касания пар БЛИЗКИХ по X уже уложенных кругов (физически только
    соседние по X круги
    вообще могут одновременно подпирать новый — дальним парам тратить
    время незачем). Кабели, которым не хватило места, возвращаются
    отдельным списком, а не молча пропускаются.

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

from Autodesk.Revit.DB import (
    Arc, ElementId, ElementTypeGroup, HorizontalTextAlignment, Line,
    TextNote, TextNoteOptions, TextNoteType, VerticalTextAlignment, XYZ,
)

from lowlife.xlsx_io import read_xlsx, list_sheet_names

MM_TO_FEET = 1.0 / 304.8
SHEET_NAME = u"Сводный"

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
        sheet_name = SHEET_NAME if SHEET_NAME in names else (names[0] if names else None)

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
# Укладка кругов ("гравитационная" — см. докстринг модуля)
# ------------------------------------------------------------

_NEIGHBOR_WINDOW = 8  # сколько соседей по X пробовать в парах-опорах


class _Placed(object):
    __slots__ = ("cx", "cy", "r", "cable")

    def __init__(self, cx, cy, r, cable):
        self.cx = cx
        self.cy = cy
        self.r = r
        self.cable = cable


def _rest_y(x, r, placed):
    u"""Самая низкая допустимая высота центра круга радиуса r при данном
    x: пол (y=r) либо верх уже уложенного круга, пересекающегося с новым по X."""
    y = r
    for p in placed:
        dx = x - p.cx
        reach = r + p.r
        if -reach < dx < reach:
            dy = math.sqrt(max(reach * reach - dx * dx, 0.0))
            top = p.cy + dy
            if top > y:
                y = top
    return y


def _circle_circle_x(p, q, r):
    u"""X центра нового круга радиуса r, одновременно касающегося кругов
    p и q (кабель, легший в седло между двумя уже уложенными) — 0, 1 или 2 решения."""
    dx0 = q.cx - p.cx
    dy0 = q.cy - p.cy
    d2 = dx0 * dx0 + dy0 * dy0
    if d2 < 1e-12:
        return []
    d = math.sqrt(d2)
    r1 = p.r + r
    r2 = q.r + r
    if d > r1 + r2 or d < abs(r1 - r2):
        return []
    a = (r1 * r1 - r2 * r2 + d2) / (2.0 * d)
    h2 = r1 * r1 - a * a
    if h2 < 0:
        return []
    h = math.sqrt(h2)
    ux, uy = dx0 / d, dy0 / d
    mx = p.cx + a * ux
    if h < 1e-9:
        return [mx]
    return [mx - h * uy, mx + h * uy]


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

        candidates = set([r, tray_w - r])
        for p in placed:
            candidates.add(min(max(p.cx, r), tray_w - r))
            # Круг лежит на полу (y=r) и одновременно касается уже
            # уложенного p сбоку — без этой пары кандидатов новые кабели
            # находили только "сверху предыдущего" или "у стены", и
            # никогда не ложились рядом с соседом на полу, оставляя
            # большие пустые клинья между кабелями.
            reach = r + p.r
            dy = r - p.cy
            if -reach <= dy <= reach:
                dx = math.sqrt(max(reach * reach - dy * dy, 0.0))
                candidates.add(p.cx - dx)
                candidates.add(p.cx + dx)

        by_x = sorted(placed, key=lambda p: p.cx)
        n = len(by_x)
        for i in range(n):
            for j in range(i + 1, min(i + 1 + _NEIGHBOR_WINDOW, n)):
                for x in _circle_circle_x(by_x[i], by_x[j], r):
                    if r - 1e-6 <= x <= tray_w - r + 1e-6:
                        candidates.add(x)

        best = None
        for x in candidates:
            x = min(max(x, r), tray_w - r)
            y = _rest_y(x, r, placed)
            if y + r > tray_h + 1e-6:
                continue
            if not _fits(x, y, r, tray_w, tray_h, placed):
                continue
            if best is None or y < best[1] - 1e-9:
                best = (x, y)

        if best is None:
            unplaced.append(cable)
            continue

        placed.append(_Placed(best[0], best[1], r, cable))

    return placed, unplaced


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


def plan_section(cables, tray_width_mm, tray_height_mm):
    u"""Раскладка без рисования. (placed, unplaced, fill_percent);
    fill_percent — по фактически уложенным кабелям."""
    placed, unplaced = arrange_cables(cables, tray_width_mm, tray_height_mm)
    tray_area_mm2 = tray_width_mm * tray_height_mm
    placed_area_mm2 = sum(math.pi * (feet_to_mm(p.r)) ** 2 for p in placed)
    fill_percent = (placed_area_mm2 / tray_area_mm2 * 100.0) if tray_area_mm2 > 0 else 0.0
    return placed, unplaced, fill_percent


def draw_section(doc, view, section_name, tray_width_mm, tray_height_mm,
                 placed, insertion_point, show_marks=True, scale=1.0):
    u"""Контур лотка (реальный размер — масштабируется видом) + подпись
    участка над ним + кружки кабелей из placed. insertion_point — левый
    нижний угол лотка. Вызывать в транзакции."""
    tray_w_ft = mm_to_feet(tray_width_mm)
    tray_h_ft = mm_to_feet(tray_height_mm)
    text_type_id = _text_note_type_id(doc)

    _draw_outline(doc, view, insertion_point, tray_w_ft, tray_h_ft)

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
