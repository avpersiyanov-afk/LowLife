# -*- coding: utf-8 -*-
"""
Логика кнопки BuildSotSchematic ("Структурная схема СОТ"): раскладка
устройств сеткой по этажам и помещениям — рамка на каждую группу
"этаж/помещение" линиями детализации, подпись помещения текстом, подпись
этажа вертикальным текстом слева, схемное семейство на месте каждого
реального устройства (тип — по категории устройства, из настроек СОТ), и
марка (IndependentTag) над каждым узлом — сама читает "Обозначение"/"Адрес"
с помеченного схемного семейства через свои поля-метки (см.
place_node_annotation), ничего в код для этого зашивать не нужно.

Кнопка работает инкрементально (см. sync_levels): при повторном запуске
раскладка не строится с нуля, а сравнивается с сохранённой в параметре
вида (lib/lowlife/sot_layout_state.py) — трогаются (двигаются/
перерисовываются) только этаж/помещение, где реально что-то изменилось,
остальное остаётся как было, теми же элементами. Первый запуск (state
пустой) — частный случай той же логики: всё считается "новым".

Портировано из рабочего Dynamo-скрипта построения структурной схемы СОТ:
геометрия (шаги, отступы, длины линий) сохранена без изменений — это
чисто чертёжные константы, не связанные с настройками проекта.
"""

import math
import re
import time

from Autodesk.Revit.DB import (
    XYZ, Line, ElementId, TextNote, TextNoteType, TextNoteOptions,
    HorizontalTextAlignment, VerticalTextAlignment, FilteredElementCollector,
    ElementTransformUtils, IndependentTag, TagOrientation, Reference
)

from lowlife.params import get_string_param, set_param_any

MM_TO_FT = 1.0 / 304.8

STEP_MM = 20.0
GROUP_GAP_MM = 5.0
LINE_OFFSET_MM = 10.0
BOTTOM_LINE_MM = -10.0
TOP_LINE_MM = 20.0
TEXT_Y_MM = 23.0
HEADER_TOP_LINE_MM = 26.0
TEXT_MARGIN_MM = 3.0

# Зеркальная TEXT_Y_MM позиция подписи помещения — под нижней линией
# рамки (BOTTOM_LINE_MM), а не над верхней (TOP_LINE_MM) — для строк,
# перенесённых по ширине (см. ROW_WRAP_STEP_MM/sync_rooms_in_level),
# у которых марки узлов и соединительные линии тоже отзеркалены (вниз/
# вверх соответственно), чтобы не пересекать подпись своей же строки.
TEXT_Y_BELOW_MM = BOTTOM_LINE_MM - TEXT_MARGIN_MM
LEVEL_SEPARATOR_OFFSET_MM = 10.0
LEVEL_NEXT_GAP_MM = 5.0
LEVEL_LINE_1_OFFSET_MM = 5.0
LEVEL_LINE_2_OFFSET_MM = 20.0
LEVEL_LINE_3_OFFSET_MM = 10.0
LEVEL_VERTICAL_LINE_LENGTH_MM = 51.0
CONTINUOUS_TOP_LINE_OFFSET_MM = 5.0
RIGHT_VERTICAL_LINE_OFFSET_MM = 5.0

# Насколько мм под уровнем содержимого этажа (current_level_y) обычно
# зарезервировано до нижней границы рамки (см. _draw_level_frame) — без
# extra_bottom_mm. Экспортируется, чтобы вызывающий код (например СКС —
# BuildScsSchematic) мог посчитать, сколько extra_bottom_mm ему нужно
# добавить, не дублируя формулу BOTTOM_LINE_MM/LEVEL_SEPARATOR_OFFSET_MM.
RESERVED_BOTTOM_MM = -BOTTOM_LINE_MM + LEVEL_SEPARATOR_OFFSET_MM

# X линий "устройство -> шкаф" на вертикальном участке (стояк) — центр
# незанятого "коридора" рамки уровня между первой и второй левыми
# вертикальными линиями (first_level_line_x..second_level_line_x, при
# group_left=0, а он всегда 0 — см. sync_cable_connections): это
# и есть место, зарезервированное под стояк — соседний коридор, между
# второй и третьей линией, уже занят подписью этажа. Так вертикальный
# участок идёт ровно посередине стояка, а не по его краю.
CABLE_RISER_OFFSET_MM = LEVEL_LINE_1_OFFSET_MM + LEVEL_LINE_2_OFFSET_MM / 2.0

# Насколько ниже узлов проходит общий горизонтальный сборный участок
# (коллектор) на каждом этаже — см. sync_cable_connections. Уже с запасом
# больше -BOTTOM_LINE_MM (10мм) — коллектор проходит НИЖЕ нижней линии
# рамки помещения, не задевая её (5мм зазора).
CABLE_DROP_OFFSET_MM = 15.0

# Зеркало CABLE_DROP_OFFSET_MM для строк, перенесённых по ширине и
# отзеркаленных (см. sync_rooms_in_level/_node_top_y) — коллектор ВЫШЕ
# верхней линии рамки помещения (TOP_LINE_MM), с тем же запасом (5мм),
# что и у обычного коллектора относительно нижней линии.
CABLE_DROP_OFFSET_UP_MM = TOP_LINE_MM + (CABLE_DROP_OFFSET_MM + BOTTOM_LINE_MM)

# Вертикальный шаг между "начальной" Y одного этажа и следующего — не
# зависит от содержимого (только от констант выше), поэтому вставка/
# удаление целого этажа — это ровно сдвиг нижестоящих на этот шаг, без
# пересчёта позиций внутри них. См. sync_levels.
LEVEL_STEP_MM = (-BOTTOM_LINE_MM) + LEVEL_SEPARATOR_OFFSET_MM + LEVEL_NEXT_GAP_MM + HEADER_TOP_LINE_MM

# Зазор между двумя СТРОКАМИ помещений ВНУТРИ одного этажа (перенос по
# ширине — см. max_row_width_mm у sync_rooms_in_level/sync_levels) — не
# путать с LEVEL_NEXT_GAP_MM (тот между РАЗНЫМИ этажами, со своей рамкой
# и подписью между ними; тут ни рамки, ни подписи по отдельности нет —
# все строки одного этажа делят одну общую рамку). Достаточно большой,
# чтобы между строками уместились ещё и соединительные линии "устройство
# -> шкаф/панель" — нечётные строки отзеркалены (см. sync_rooms_in_level:
# марка снизу узла, линия от верхнего края узла, подпись помещения снизу
# рамки), и линии соседних строк сходятся в ОДНОМ общем зазоре между
# ними (чётная строка сверху — линии вниз, нечётная снизу — линии вверх),
# а не расходятся каждая в свою сторону — 10мм (место только под рамки)
# для этого было мало, линии соседней строки утыкались в подпись.
ROW_WRAP_GAP_MM = 30.0

# Вертикальный шаг между началом одной строки помещений этажа и
# следующей (при переносе по ширине) — включает высоту самой строки
# (от подписи наверху, HEADER_TOP_LINE_MM, до нижней линии рамки
# помещения, BOTTOM_LINE_MM) плюс зазор ROW_WRAP_GAP_MM. Один и тот же
# шаг для всех строк (не только "линейных" зазоров между чётной и
# нечётной строкой, но и "подписных" между нечётной и следующей чётной)
# — с запасом, но проще и без риска накладок, чем разная ширина зазора
# через один.
ROW_WRAP_STEP_MM = HEADER_TOP_LINE_MM + (-BOTTOM_LINE_MM) + ROW_WRAP_GAP_MM

_ROOM_NUMBER_RE = re.compile(r"\((\d+)\)\s*$")
_ANY_NUMBER_RE = re.compile(r"\d+")
_SPLIT_NUMBER_RE = re.compile(r"(\d+)")

_TOLERANCE_FT = 1e-6


def _natural_sort_key(text):
    """
    Ключ "естественной" сортировки текста адреса: числовые куски
    сравниваются как числа, а не как строки, поэтому адрес "3.1.10" идёт
    после "3.1.2", а не перед ним (как было бы при обычном строковом
    сравнении — "1" < "2" посимвольно). Нечисловые куски сравниваются
    как есть.
    """
    parts = _SPLIT_NUMBER_RE.split(text or u"")
    return tuple(int(part) if part.isdigit() else part for part in parts)


def _room_sort_key(room_key):
    """
    Ключ сортировки групп помещений внутри этажа: сначала помещения с
    номером — по возрастанию (номер берётся из хвостового "(Номер)", как
    пишет room_info.format_room_value, иначе — первое число в строке),
    затем всё остальное (включая "(пусто)") — по алфавиту.
    """
    text = room_key or u""

    match = _ROOM_NUMBER_RE.search(text)
    if match:
        return (0, int(match.group(1)), text)

    match = _ANY_NUMBER_RE.search(text)
    if match:
        return (0, int(match.group(0)), text)

    return (1, 0, text)


# ------------------------------------------------------------
# ТИП ТЕКСТА
# ------------------------------------------------------------

def get_text_note_type(doc):
    try:
        types = FilteredElementCollector(doc).OfClass(TextNoteType).WhereElementIsElementType().ToElements()
        if types:
            return types[0]
    except:
        pass
    return None


# ------------------------------------------------------------
# ТЕКСТ
# ------------------------------------------------------------

def create_room_text(doc, view, text, x, y):
    if view is None or not text:
        return None

    text_type = get_text_note_type(doc)
    if text_type is None:
        return None

    try:
        point = XYZ(x, y, 0.0)
        text_note = TextNote.Create(doc, view.Id, point, text, text_type.Id)
        try:
            text_note.HorizontalAlignment = HorizontalTextAlignment.Center
        except:
            pass
        try:
            # Без этого y — верхняя граница текста (Revit по умолчанию
            # анкерит TextNote сверху), а TEXT_Y_MM подобран как раз
            # СЕРЕДИНА (TOP_LINE_MM..HEADER_TOP_LINE_MM) — с анкером
            # "сверху" текст визуально сдвинут вниз от реального центра
            # строки на половину своей высоты, а не стоит по центру.
            text_note.VerticalAlignment = VerticalTextAlignment.Middle
        except:
            pass
        return text_note
    except:
        return None


def create_level_text(doc, view, text, x, y):
    if view is None or not text:
        return None

    text_type = get_text_note_type(doc)
    if text_type is None:
        return None

    try:
        point = XYZ(x, y, 0.0)
        options = TextNoteOptions(text_type.Id)
        try:
            options.HorizontalAlignment = HorizontalTextAlignment.Center
        except:
            pass
        options.Rotation = math.pi / 2.0
        try:
            options.KeepRotatedTextReadable = False
        except:
            pass
        return TextNote.Create(doc, view.Id, point, text, options)
    except:
        return None


def get_text_width(doc, text_note, view):
    if text_note is None:
        return 0.0
    try:
        doc.Regenerate()
        bbox = text_note.get_BoundingBox(view)
        if bbox is None:
            return 0.0
        width = bbox.Max.X - bbox.Min.X
        return width if width > 0 else 0.0
    except:
        return 0.0


def move_text_to(doc, text_note, x, y):
    if text_note is None:
        return False
    try:
        old_point = text_note.Coord
        new_point = XYZ(x, y, 0.0)
        vector = new_point - old_point
        if vector.GetLength() > 0.000001:
            ElementTransformUtils.MoveElement(doc, text_note.Id, vector)
        return True
    except:
        return False


def center_text_in_frame(doc, text_note, view, frame_left, frame_right, target_y):
    """
    Ставит текст (маркировку помещения) в расчётный центр рамки — без
    doc.Regenerate()/BoundingBox: create_room_text создаёт TextNote с
    HorizontalAlignment.Center, поэтому Coord и есть визуальный центр
    текста по X, разметка готова сразу же, "перед вставкой" устройств, а
    не подгоняется по факту после неё. Раньше здесь читался реальный
    BoundingBox (нужен Regenerate()) для подгонки на случай, если оценка
    ширины текста не совсем точна — на моделях, где Regenerate() стоит
    заметное время, это давало один такой вызов на КАЖДОЕ новое помещение
    и стоило минут на схему; отказались от него как от ненужной точности
    ценой самой длительной части построения.
    """
    if text_note is None:
        return False
    try:
        frame_center_x = (frame_left + frame_right) / 2.0
        return move_text_to(doc, text_note, frame_center_x, target_y)
    except:
        return False


def center_level_text(doc, text_note, view, left_x, right_x, bottom_y, top_y):
    """Маркировка этажа — см. center_text_in_frame."""
    if text_note is None:
        return False
    try:
        center_x = (left_x + right_x) / 2.0
        center_y = (bottom_y + top_y) / 2.0
        return move_text_to(doc, text_note, center_x, center_y)
    except:
        return False


# ------------------------------------------------------------
# ЛИНИИ (возвращают созданный DetailCurve/None — id нужен для state)
# ------------------------------------------------------------

def draw_vertical_line(doc, view, x, y_offset=0.0):
    if view is None:
        return None
    try:
        y_min = y_offset + BOTTOM_LINE_MM * MM_TO_FT
        y_max = y_offset + HEADER_TOP_LINE_MM * MM_TO_FT
        start = XYZ(x, y_min, 0.0)
        end = XYZ(x, y_max, 0.0)
        if start.DistanceTo(end) < 0.001:
            return None
        return doc.Create.NewDetailCurve(view, Line.CreateBound(start, end))
    except:
        return None


def draw_level_vertical_line(doc, view, x, bottom_y):
    if view is None:
        return None
    try:
        start = XYZ(x, bottom_y, 0.0)
        end = XYZ(x, bottom_y + LEVEL_VERTICAL_LINE_LENGTH_MM * MM_TO_FT, 0.0)
        if start.DistanceTo(end) < 0.001:
            return None
        return doc.Create.NewDetailCurve(view, Line.CreateBound(start, end))
    except:
        return None


def draw_horizontal_line(doc, view, x_start, x_end, y):
    if view is None:
        return None
    try:
        start = XYZ(x_start, y, 0.0)
        end = XYZ(x_end, y, 0.0)
        if start.DistanceTo(end) < 0.001:
            return None
        return doc.Create.NewDetailCurve(view, Line.CreateBound(start, end))
    except:
        return None


def draw_segment(doc, view, x1, y1, x2, y2):
    """Произвольный отрезок между двумя точками (для линий "устройство -> шкаф")."""
    if view is None:
        return None
    try:
        start = XYZ(x1, y1, 0.0)
        end = XYZ(x2, y2, 0.0)
        if start.DistanceTo(end) < 0.001:
            return None
        return doc.Create.NewDetailCurve(view, Line.CreateBound(start, end))
    except:
        return None


# ------------------------------------------------------------
# МАРКА УЗЛА (аннотация "Обозначение, Адрес" над схемным семейством)
# ------------------------------------------------------------

def place_node_annotation(doc, view, node_instance, annotation_symbol, x, current_level_y, label_offset_mm,
                           below=False):
    """
    Ставит марку (IndependentTag) типа annotation_symbol на node_instance —
    марка сама читает "Обозначение"/"Адрес" с помеченного элемента через
    свои поля-метки, ничего сюда передавать/копировать не нужно. Марка —
    горизонтальная (TagOrientation.Horizontal), без выноски, головка по
    центру узла на label_offset_mm выше точки вставки (настройка СОТ
    "Смещение марки узла вверх от точки вставки, мм"), либо ниже, если
    below=True (по умолчанию False, поведение как раньше) — для строк
    помещений, перенесённых по ширине и отзеркаленных (см.
    sync_rooms_in_level): там и соединительная линия идёт от верхнего
    края узла, а не от нижнего, так что марка снизу не мешает ей.
    """
    if annotation_symbol is None or node_instance is None:
        return None

    try:
        if not annotation_symbol.IsActive:
            annotation_symbol.Activate()
            doc.Regenerate()

        offset_ft = -label_offset_mm * MM_TO_FT if below else label_offset_mm * MM_TO_FT
        point = XYZ(x, current_level_y + offset_ft, 0.0)

        return IndependentTag.Create(
            doc, annotation_symbol.Id, view.Id, Reference(node_instance),
            False, TagOrientation.Horizontal, point
        )
    except:
        return None


# ------------------------------------------------------------
# ЭЛЕМЕНТЫ ПО ID (для инкрементальной синхронизации)
# ------------------------------------------------------------

def _resolve(doc, id_int):
    if id_int is None:
        return None
    try:
        return doc.GetElement(ElementId(int(id_int)))
    except:
        return None


def translate_elements(doc, element_ids, dx, dy):
    """
    Двигает элементы (список int id) на вектор (dx, dy), в футах.
    Нерезолвящиеся id пропускает. Марки (IndependentTag) без выноски не
    переезжают вместе с помеченным элементом через ElementTransformUtils
    (их позиция — TagHeadPosition, отдельное свойство, а не Location) —
    поэтому для них сдвигается TagHeadPosition, а не Location.
    """
    if abs(dx) < _TOLERANCE_FT and abs(dy) < _TOLERANCE_FT:
        return

    vector = XYZ(dx, dy, 0.0)

    for id_int in element_ids:
        el = _resolve(doc, id_int)
        if el is None:
            continue
        try:
            if isinstance(el, IndependentTag):
                el.TagHeadPosition = el.TagHeadPosition + vector
            else:
                ElementTransformUtils.MoveElement(doc, el.Id, vector)
        except:
            pass


def delete_elements(doc, element_ids):
    """Удаляет элементы (список int id). Нерезолвящиеся id пропускает."""
    for id_int in element_ids:
        el = _resolve(doc, id_int)
        if el is None:
            continue
        try:
            doc.Delete(el.Id)
        except:
            pass


def _bump(stats, key):
    if stats is not None:
        stats[key] = stats.get(key, 0) + 1


def _bump_time(timing, key, seconds):
    """Накапливает время (сек.) по ключу — тот же приём, что _bump, только сумма, не счётчик."""
    if timing is not None:
        timing[key] = timing.get(key, 0.0) + seconds


def _room_record_element_ids(room_record):
    """Все id, принадлежащие записи помещения (рамка+текст+узлы+марки), одним списком."""
    ids = list(room_record.get("line_ids", []))

    if room_record.get("text_id") is not None:
        ids.append(room_record["text_id"])

    for dev in room_record.get("devices", {}).values():
        ids.append(dev["instance_id"])
        if dev.get("tag_id") is not None:
            ids.append(dev["tag_id"])

    return ids


def _level_frame_element_ids(level_record):
    ids = list(level_record.get("line_ids", []))
    if level_record.get("text_id") is not None:
        ids.append(level_record["text_id"])
    return ids


def _room_group_width_ft(room_key, valid_devices):
    """
    Ширина рамки помещения (в футах) — по числу устройств (STEP_MM между
    ними, LINE_OFFSET_MM с каждого края) ИЛИ по ширине текста подписи
    (грубая оценка по числу символов — точного измерения без реального
    BoundingBox всё равно нет, см. center_text_in_frame), смотря что
    больше. Ширину подписи одно время убирали отсюда совсем (рамка для
    ОДНОГО устройства в помещении с длинным именем становилась неоправданно
    широкой) — но без нижней границы по тексту соседние узкие помещения
    (мало устройств, длинное имя) вставали почти впритык, и подписи
    налезали друг на друга нечитаемой кашей, особенно при переносе по
    строкам (max_row_width_mm), где узких однодевайсных помещений в ряд
    обычно много. Оценка "на глаз" всё же лучше, чем совсем без неё.

    Чистая функция — нужна и для самого рисования (_place_room_group), и
    для переноса помещений по строкам при ограничении ширины этажа (см.
    max_row_width_mm у sync_rooms_in_level).
    """
    offset = LINE_OFFSET_MM * MM_TO_FT
    step = STEP_MM * MM_TO_FT
    text_margin = TEXT_MARGIN_MM * MM_TO_FT

    nodes_width = 2.0 * offset + (len(valid_devices) - 1) * step
    text_width = len(room_key) * 2.5 * MM_TO_FT
    text_required_width = text_width + 2.0 * text_margin

    return max(nodes_width, text_required_width)


# ------------------------------------------------------------
# ГРУППА ПОМЕЩЕНИЯ (ряд узлов + рамка) — рисование "с нуля"
# ------------------------------------------------------------

def _place_room_group(doc, view, x_pos, room_key, valid_devices, room_param_name,
                       address_param_name, device_uid_param_name, annotation_symbol,
                       label_offset_mm, current_level_y, timing=None, flipped=False):
    """
    Рисует помещение с нуля в позиции x_pos — используется и для первой
    постройки схемы, и для перерисовки помещения, чьё содержимое
    изменилось (sync_rooms_in_level). valid_devices — [(device, symbol), ...],
    уже отсортированные вызывающим кодом по адресу устройства (стабильный
    порядок слотов между запусками).

    flipped=True — для строк помещений, перенесённых по ширине (см.
    max_row_width_mm/ROW_WRAP_STEP_MM у sync_rooms_in_level) через одну:
    подпись помещения снизу рамки (не сверху), марка узла снизу узла (не
    сверху, place_node_annotation(below=True)) — соединительная линия
    "устройство -> шкаф/панель" (рисуется отдельно, вызывающим кодом типа
    sot_schematic.sync_cable_connections/scs_schematic.sync_panel_buses,
    от bbox узла — см. _node_top_y вместо _node_bottom_y) в таком случае
    идёт от ВЕРХНЕГО края узла, а не от нижнего — соседние строки сходятся
    линиями в один общий зазор между ними, а не расходятся каждая в свою
    сторону, и линия не пересекает подпись помещения своей же строки
    (см. sync_rooms_in_level докстринг).

    timing — если передан словарь, копит в нём суммарное время (сек.) по
    видам операций ("text"/"lines"/"symbol_activate"/"instance"/"params"/
    "tag") — диагностика, откуда реально уходит время на конкретной
    модели (см. _bump_time). None по умолчанию — без замеров.

    Возвращает (room_record, report_rows) — room_record идёт в state
    (см. sot_layout_state), report_rows — [(room_key, address), ...].
    """
    step = STEP_MM * MM_TO_FT
    text_y = (TEXT_Y_BELOW_MM if flipped else TEXT_Y_MM) * MM_TO_FT

    # group_width — по числу устройств ИЛИ по ширине подписи, смотря что
    # больше (см. _room_group_width_ft) — подпись центрируется по X
    # независимо от неё (HorizontalAlignment.Center, см.
    # center_text_in_frame).
    group_width = _room_group_width_ft(room_key, valid_devices)
    preliminary_center_x = x_pos + group_width / 2.0

    _t0 = time.time()
    text_note = create_room_text(doc, view, room_key, preliminary_center_x, current_level_y + text_y)

    group_left_x = x_pos
    group_right_x = x_pos + group_width
    group_center_x = (group_left_x + group_right_x) / 2.0

    if text_note is not None:
        center_text_in_frame(doc, text_note, view, group_left_x, group_right_x, current_level_y + text_y)
    _bump_time(timing, "text", time.time() - _t0)

    _t0 = time.time()
    line_ids = []
    for elem in (
        draw_vertical_line(doc, view, group_left_x, current_level_y),
        draw_vertical_line(doc, view, group_right_x, current_level_y),
        draw_horizontal_line(doc, view, group_left_x, group_right_x, current_level_y + BOTTOM_LINE_MM * MM_TO_FT),
        draw_horizontal_line(doc, view, group_left_x, group_right_x, current_level_y + TOP_LINE_MM * MM_TO_FT),
        draw_horizontal_line(doc, view, group_left_x, group_right_x, current_level_y + HEADER_TOP_LINE_MM * MM_TO_FT),
    ):
        if elem is not None:
            line_ids.append(elem.Id.IntegerValue)
    _bump_time(timing, "lines", time.time() - _t0)

    nodes_center_width = (len(valid_devices) - 1) * step
    nodes_start_x = group_center_x - nodes_center_width / 2.0
    x_elem = nodes_start_x

    devices_state = {}
    report_rows = []

    for device, symbol in valid_devices:
        if not symbol.IsActive:
            _t0 = time.time()
            symbol.Activate()
            doc.Regenerate()
            _bump_time(timing, "symbol_activate", time.time() - _t0)

        _t0 = time.time()
        placement_point = XYZ(x_elem, current_level_y, 0.0)
        node_instance = doc.Create.NewFamilyInstance(placement_point, symbol, view)
        _bump_time(timing, "instance", time.time() - _t0)

        if node_instance is not None:
            _t0 = time.time()
            address_value = get_string_param(device, address_param_name)
            if address_value:
                set_param_any(node_instance, address_param_name, address_value)

            room_value = get_string_param(device, room_param_name)
            if room_value:
                set_param_any(node_instance, room_param_name, room_value)

            uid = device.UniqueId
            if device_uid_param_name:
                set_param_any(node_instance, device_uid_param_name, uid)
            _bump_time(timing, "params", time.time() - _t0)

            _t0 = time.time()
            tag = place_node_annotation(
                doc, view, node_instance, annotation_symbol, x_elem, current_level_y, label_offset_mm,
                below=flipped
            )
            _bump_time(timing, "tag", time.time() - _t0)

            devices_state[uid] = {
                "x": x_elem,
                "instance_id": node_instance.Id.IntegerValue,
                "tag_id": (tag.Id.IntegerValue if tag is not None else None)
            }
            report_rows.append((room_key, address_value or u""))

        x_elem += step

    room_record = {
        "x_left": group_left_x,
        "x_right": group_right_x,
        "y": current_level_y,
        "flipped": flipped,
        "text_id": (text_note.Id.IntegerValue if text_note is not None else None),
        "line_ids": line_ids,
        "devices": devices_state
    }

    return room_record, report_rows


# ------------------------------------------------------------
# РАМКА УРОВНЯ — рисование "с нуля" / удаление
# ------------------------------------------------------------

def _draw_level_frame(doc, view, level_label, current_level_y, group_left, group_right,
                       extra_bottom_mm=0.0, extra_left_mm=0.0):
    """
    Рисует рамку этажа (3 левые вертикальные линии, правая вертикальная,
    2 горизонтальные, вертикальный текст этажа). group_left/group_right —
    границы содержимого этажа (level_group_left/level_group_right из
    sync_rooms_in_level). extra_bottom_mm — на сколько мм дополнительно
    опустить нижнюю границу рамки ниже обычного (по умолчанию 0 — ничего
    не меняется); нужно вызывающему коду, которому под рамкой этажа надо
    больше места, чем обычно (например СКС — несколько линий шины друг
    под другом, см. BuildScsSchematic). extra_left_mm — аналогично, но
    влево: на сколько мм дополнительно расширить КОРИДОР МЕЖДУ ПЕРВОЙ И
    ВТОРОЙ ЛИНИЕЙ рамки (по умолчанию 0); нужно, если между помещениями
    и подписью этажа рисуется что-то ещё, чем обычная ширина коридора не
    рассчитана (например СКС — несколько стояков панелей и дорожки
    магистралей, см. BuildScsSchematic). Вторая и третья линия (и подпись
    этажа между ними) сдвигаются влево вместе, на то же extra_left_mm —
    сама подпись остаётся в коридоре неизменной ширины, просто дальше от
    содержимого, а не "растягивается" вместе с ним (иначе при большом
    extra_left_mm подпись оказалась бы неоправданно далеко от второй
    линии, а стояки/дорожки — наоборот, залезали бы за вторую линию,
    в коридор подписи, из-за фиксированной ширины первого коридора).
    Возвращает (text_id, line_ids).
    """
    line_ids = []

    # base_bottom_y/level_lines_top_y — обычная (extra_bottom_mm=0) высота
    # рамки, верх (level_lines_top_y) всегда остаётся здесь же — растягиваем
    # только вниз, на extra_bottom_mm, а не сдвигаем всю рамку целиком
    # (иначе верх рамки оторвался бы от рамок помещений над ним).
    base_bottom_y = current_level_y + BOTTOM_LINE_MM * MM_TO_FT - LEVEL_SEPARATOR_OFFSET_MM * MM_TO_FT
    level_lines_top_y = base_bottom_y + LEVEL_VERTICAL_LINE_LENGTH_MM * MM_TO_FT
    bottom_level_line_y = base_bottom_y - extra_bottom_mm * MM_TO_FT

    # Аналогично extra_bottom_mm: первая линия (ближе к помещениям)
    # остаётся на обычном месте, растягиваем коридор ПЕРЕД второй линией
    # (первая-вторая) — вторая и третья линия (и подпись этажа между
    # ними, свой коридор неизменной ширины) сдвигаются вместе, дальше
    # влево, а не остаются на месте (иначе содержимое первого коридора
    # при росте залезало бы за вторую линию, в коридор подписи).
    first_level_line_x = group_left - LEVEL_LINE_1_OFFSET_MM * MM_TO_FT
    second_level_line_x = first_level_line_x - (LEVEL_LINE_2_OFFSET_MM + extra_left_mm) * MM_TO_FT
    third_level_line_x = second_level_line_x - LEVEL_LINE_3_OFFSET_MM * MM_TO_FT
    right_level_line_x = group_right + RIGHT_VERTICAL_LINE_OFFSET_MM * MM_TO_FT

    for x in (first_level_line_x, second_level_line_x, third_level_line_x, right_level_line_x):
        elem = draw_segment(doc, view, x, bottom_level_line_y, x, level_lines_top_y)
        if elem is not None:
            line_ids.append(elem.Id.IntegerValue)

    elem = draw_horizontal_line(doc, view, third_level_line_x, right_level_line_x, bottom_level_line_y)
    if elem is not None:
        line_ids.append(elem.Id.IntegerValue)

    continuous_top_line_y = current_level_y + (HEADER_TOP_LINE_MM + CONTINUOUS_TOP_LINE_OFFSET_MM) * MM_TO_FT
    elem = draw_horizontal_line(doc, view, third_level_line_x, right_level_line_x, continuous_top_line_y)
    if elem is not None:
        line_ids.append(elem.Id.IntegerValue)

    level_text_x = (second_level_line_x + third_level_line_x) / 2.0
    level_text_y = (level_lines_top_y + bottom_level_line_y) / 2.0

    text_id = None
    level_text_note = create_level_text(doc, view, level_label, level_text_x, level_text_y)
    if level_text_note is not None:
        center_level_text(
            doc, level_text_note, view,
            second_level_line_x, third_level_line_x,
            bottom_level_line_y, level_lines_top_y
        )
        text_id = level_text_note.Id.IntegerValue

    return text_id, line_ids


# ------------------------------------------------------------
# ПОМЕЩЕНИЯ ВНУТРИ ОДНОГО ЭТАЖА — инкрементальная синхронизация
# ------------------------------------------------------------

def sync_rooms_in_level(doc, view, level_label, current_level_y, level_dy, room_groups,
                         category_symbols, category_for_device, room_param_name, address_param_name,
                         device_uid_param_name, annotation_symbol, label_offset_mm,
                         previous_rooms_state, unmatched_report, stats=None, room_sort_values=None,
                         timing=None, max_row_width_mm=0.0):
    """
    room_groups — OrderedDict(room_key -> [device, ...]) для этого этажа
    (желаемое состояние, уже сгруппировано по параметру помещения).
    previous_rooms_state — {room_key: room_record} из state этого же этажа
    в прошлый раз ({} для нового этажа/первого запуска).
    level_dy — на сколько по Y сдвинулся сам этаж относительно прошлого
    раза (0.0, если этаж не двигался/только что появился) — непереехавшие
    помещения переносятся на этот вектор вместе с этажом, а не только по X.
    room_sort_values — {room_key: число} — порядок помещений слева
    направо на схеме, по возрастанию (по умолчанию None — как раньше,
    порядок по _room_sort_key, т.е. по номеру/имени помещения). Если
    передан, используется ПОЛНОСТЬЮ вместо _room_sort_key (не вперемешку
    — ключ, которого нет в словаре, уходит в конец, `float('inf')`).
    Нужно, если у вызывающего кода порядок помещений должен быть другим
    (например СКС — слева направо по плану, см. BuildScsSchematic); СОТ
    и СПС этот аргумент не передают, для них ничего не меняется.
    max_row_width_mm — максимальная ширина ОДНОЙ строки помещений этажа,
    мм (по умолчанию 0 — не ограничивать, как раньше, все помещения в
    одну строку без переноса); если следующее по порядку помещение не
    помещается в текущую строку — переносится на новую строку НИЖЕ (как
    перенос текста по словам, порядок помещений при этом не меняется —
    только на сколько строк он разбит), см. _room_group_width_ft/
    ROW_WRAP_STEP_MM. Нужно, чтобы лист не получался очень длинным по
    ширине при большом числе помещений на этаже — поле "Максимальная
    ширина строки помещений на этаже, мм" в настройках каждой дисциплины
    (СКС/СОТ/СПС), по умолчанию пусто/0 — как раньше.

    Нечётные строки (при переносе) — отзеркалены: подпись помещения
    снизу рамки, марка узла снизу узла, соединительная линия "устройство
    -> шкаф/панель" (рисуется отдельно вызывающим кодом) — от ВЕРХНЕГО
    края узла (см. _place_room_group(flipped=...), _node_top_y). Так
    соседние строки сходятся линиями в один общий зазор между ними
    (чётная сверху — линии вниз, нечётная снизу — линии вверх), а не
    расходятся каждая в свою сторону, пересекая подпись соседней строки.

    Для каждого помещения: если набор устройств (по UniqueId) не
    изменился — либо не трогаем вообще (позиция та же), либо просто
    переносим на новую позицию (ElementTransformUtils), если что-то левее
    сдвинулось, сдвинулся сам этаж, и/или помещение перешло на другую
    строку при переносе по ширине; если набор изменился (или помещения
    раньше не было) — удаляем старые элементы (если были) и рисуем
    заново. Помещения, пропавшие из желаемого набора, удаляются целиком,
    следующие за ними автоматически "подтягиваются" — курсор x не
    резервирует под них место.

    stats (если передан) — словарь-счётчик, наращивает ключи
    "rooms_unchanged"/"rooms_moved"/"rooms_created"/"rooms_redrawn"/"rooms_removed"
    (единица измерения — помещение, не устройство: если содержимое
    помещения изменилось, всё помещение перерисовывается целиком).

    Возвращает (new_rooms_state, level_group_left, level_group_right,
    report_rows, row_wrap_extra_mm) — row_wrap_extra_mm (0.0 без переноса)
    нужен вызывающему коду (sync_levels), чтобы растянуть рамку этажа по
    высоте под все строки помещений, не только под одну.
    """
    level_group_left = None
    level_group_right = None
    new_rooms_state = {}
    report_rows = []

    if room_sort_values is not None:
        sort_key_fn = lambda room_key: room_sort_values.get(room_key, float("inf"))
    else:
        sort_key_fn = _room_sort_key

    ordered_room_keys = sorted(room_groups.keys(), key=sort_key_fn)

    # Первый проход — только сопоставление категорий/устройств и решение,
    # на какую строку попадёт каждое помещение (перенос по ширине, если
    # max_row_width_mm задан) — без единого Revit-вызова, чтобы ряд можно
    # было спланировать целиком до того, как что-либо рисуется/двигается.
    room_valid_devices = {}
    for room_key in ordered_room_keys:
        devices = room_groups[room_key]
        valid_devices = []

        for device in devices:
            category = category_for_device(device)
            symbol = category_symbols.get(category) if category else None
            if symbol is not None:
                valid_devices.append((device, symbol))
            else:
                unmatched_report.append((level_label, room_key, device))

        if not valid_devices:
            continue

        valid_devices.sort(key=lambda pair: _natural_sort_key(get_string_param(pair[0], address_param_name)))
        room_valid_devices[room_key] = valid_devices

    placed_room_keys = [rk for rk in ordered_room_keys if rk in room_valid_devices]

    max_row_width_ft = max_row_width_mm * MM_TO_FT if max_row_width_mm else 0.0
    row_of_room = {}
    row_x_cursor = 0.0
    current_row = 0
    for room_key in placed_room_keys:
        width = _room_group_width_ft(room_key, room_valid_devices[room_key])
        if max_row_width_ft > 0.0 and row_x_cursor > 0.0:
            projected_right = row_x_cursor + GROUP_GAP_MM * MM_TO_FT + width
            if projected_right > max_row_width_ft:
                current_row += 1
                row_x_cursor = 0.0
        if row_x_cursor > 0.0:
            row_x_cursor += GROUP_GAP_MM * MM_TO_FT
        row_of_room[room_key] = current_row
        row_x_cursor += width

    max_row_index = 0
    x_cursor = 0.0
    active_row = 0

    for room_key in placed_room_keys:
        valid_devices = room_valid_devices[room_key]
        row = row_of_room[room_key]
        if row != active_row:
            x_cursor = 0.0
            active_row = row
        max_row_index = max(max_row_index, row)
        row_y = current_level_y - row * ROW_WRAP_STEP_MM * MM_TO_FT
        # Чётные строки — как раньше (подпись/марка сверху, линия от
        # нижнего края узла), нечётные — отзеркалены (см. _place_room_group
        # docstring): так соседние строки сходятся линиями в один общий
        # зазор между ними, а не расходятся каждая в свою сторону.
        flipped = (row % 2 == 1)

        desired_uids = set(device.UniqueId for device, _symbol in valid_devices)
        prev_record = previous_rooms_state.get(room_key)
        prev_uids = set(prev_record["devices"].keys()) if prev_record else set()

        # Смена "стороны" (flipped) требует перерисовки, даже если набор
        # устройств тот же — иначе подпись/марка/направление линии
        # остались бы от прежней строки, для новой стороны неверные (это
        # не просто "подвинуть", у geometрии другая ориентация).
        content_changed = (
            (prev_record is None)
            or (desired_uids != prev_uids)
            or (bool(prev_record.get("flipped", False)) != flipped)
        )

        if not content_changed:
            dx = x_cursor - prev_record["x_left"]
            # Старые (сохранённые до появления переноса по строкам) записи
            # "y" не имеют — тогда считаем, что помещение было в строке 0
            # прежнего положения этажа (current_level_y - level_dy) — так
            # оно и стояло на самом деле до этой версии кода.
            prev_room_y = prev_record.get("y", current_level_y - level_dy)
            dy = row_y - prev_room_y
            room_moved = abs(dx) > _TOLERANCE_FT or abs(dy) > _TOLERANCE_FT
            if room_moved:
                translate_elements(doc, _room_record_element_ids(prev_record), dx, dy)
                _bump(stats, "rooms_moved")
            else:
                _bump(stats, "rooms_unchanged")

            new_devices_state = {}
            for device, symbol in valid_devices:
                uid = device.UniqueId
                old_dev = prev_record["devices"][uid]
                instance = _resolve(doc, old_dev["instance_id"])
                new_x = old_dev["x"] + dx

                # Устройство то же (набор UID не менялся — иначе попали бы в
                # ветку "изменилось" и перерисовались заново), но категория
                # могла сопоставляться с ДРУГИМ схемным семейством с прошлого
                # запуска (настройки поменялись, а сам список устройств
                # помещения — нет) — тогда просто "перенести" узел мало,
                # у него на месте останется СТАРЫЙ тип. Проверяем и меняем
                # тип на месте (FamilyInstance.Symbol), не только позицию.
                if instance is not None and symbol is not None:
                    try:
                        symbol_changed = instance.Symbol.Id != symbol.Id
                    except:
                        symbol_changed = False
                    if symbol_changed:
                        try:
                            if not symbol.IsActive:
                                symbol.Activate()
                                doc.Regenerate()
                            instance.Symbol = symbol
                        except:
                            pass

                address_value = get_string_param(device, address_param_name)
                if instance is not None and address_value:
                    set_param_any(instance, address_param_name, address_value)

                room_value = get_string_param(device, room_param_name)
                if instance is not None and room_value:
                    set_param_any(instance, room_param_name, room_value)

                # Марки без выноски (TagHeadPosition) в некоторых проектах на
                # практике не переезжают надёжно вместе с translate_elements
                # (сдвиг узла выше уже применил vector и к ним тоже — но
                # результат ненадёжен) — поэтому при реальном сдвиге узла
                # старую марку удаляем и ставим заново на новом месте, а не
                # полагаемся на то, что она уже переехала. Марка также
                # добирается задним числом, если её вообще не было (узел
                # размещён до того, как в настройках выбрали марку).
                tag_id = old_dev.get("tag_id")
                if room_moved and tag_id is not None:
                    delete_elements(doc, [tag_id])
                    tag_id = None
                if tag_id is None and instance is not None:
                    new_tag = place_node_annotation(
                        doc, view, instance, annotation_symbol, new_x, row_y, label_offset_mm,
                        below=flipped
                    )
                    if new_tag is not None:
                        tag_id = new_tag.Id.IntegerValue
                        _bump(stats, "tags_added")

                new_devices_state[uid] = {
                    "x": new_x,
                    "instance_id": old_dev["instance_id"],
                    "tag_id": tag_id
                }
                report_rows.append((room_key, address_value or u""))

            room_record = {
                "x_left": x_cursor,
                "x_right": prev_record["x_right"] + dx,
                "y": row_y,
                "flipped": flipped,
                "text_id": prev_record.get("text_id"),
                "line_ids": prev_record.get("line_ids", []),
                "devices": new_devices_state
            }
        else:
            if prev_record is not None:
                delete_elements(doc, _room_record_element_ids(prev_record))
                _bump(stats, "rooms_redrawn")
            else:
                _bump(stats, "rooms_created")

            room_record, room_report_rows = _place_room_group(
                doc, view, x_cursor, room_key, valid_devices, room_param_name,
                address_param_name, device_uid_param_name, annotation_symbol,
                label_offset_mm, row_y, timing=timing, flipped=flipped
            )
            report_rows.extend(room_report_rows)

        new_rooms_state[room_key] = room_record

        level_group_left = room_record["x_left"] if level_group_left is None else min(level_group_left, room_record["x_left"])
        level_group_right = room_record["x_right"] if level_group_right is None else max(level_group_right, room_record["x_right"])

        x_cursor = room_record["x_right"] + GROUP_GAP_MM * MM_TO_FT

    for room_key, prev_record in previous_rooms_state.items():
        if room_key in new_rooms_state:
            continue
        delete_elements(doc, _room_record_element_ids(prev_record))
        _bump(stats, "rooms_removed")

    row_wrap_extra_mm = max_row_index * ROW_WRAP_STEP_MM if max_row_index > 0 else 0.0

    return new_rooms_state, level_group_left, level_group_right, report_rows, row_wrap_extra_mm


# ------------------------------------------------------------
# ВСЕ ЭТАЖИ — инкрементальная синхронизация (верхний уровень)
# ------------------------------------------------------------

def sync_levels(doc, view, level_order, level_room_groups, level_labels, category_symbols,
                 category_for_device, room_param_name, address_param_name, device_uid_param_name,
                 annotation_symbol, label_offset_mm, previous_state, unmatched_report, stats=None,
                 extra_bottom_mm=0.0, extra_left_mm=0.0, room_sort_values=None, timing=None,
                 max_row_width_mm=0.0):
    """
    level_order — ключи этажей (те же, что group_elements_by_level даёт),
    в порядке отрисовки сверху вниз (sorted_level_names).
    level_room_groups — {level_key: OrderedDict(room_key -> [device, ...])}.
    level_labels — {level_key: подпись для схемы} (get_level_label).
    previous_state — {"levels": {level_key: level_record}} из
    sot_layout_state.load_state (или {"levels": {}} для первого запуска).
    extra_bottom_mm — на сколько мм дополнительно опустить нижнюю границу
    рамки КАЖДОГО этажа (по умолчанию 0 — как раньше); нужно, если под
    рамкой этажа рисуется что-то ещё, кроме самой схемы (например СКС —
    несколько линий шины друг под другом, см. BuildScsSchematic). Общий
    на все этажи (не по этажам отдельно) — если изменился по сравнению с
    прошлым запуском, все рамки этажей перерисовываются заново (иначе
    рамка, которую в этот раз просто "подвинули" — без redraw — осталась
    бы со старым (возможно недостаточным) отступом).
    extra_left_mm — аналогично, но влево (по умолчанию 0 — как раньше);
    нужно, если левее рамок помещений рисуется что-то ещё, чем обычная
    ширина рамки не рассчитана (например СКС — несколько стояков панелей
    и дорожки магистралей). Тоже общий на все этажи, тоже форсирует
    полную перерисовку рамок при изменении.
    room_sort_values — {level_key: {room_key: число}} (по умолчанию None
    — как раньше, sync_rooms_in_level сама сортирует по _room_sort_key) —
    порядок помещений слева направо на каждом этаже; передаётся в
    sync_rooms_in_level для соответствующего level_key как есть (см. её
    docstring). Уровня, для которого записи нет, тоже не касается — для
    него сортировка как раньше. СОТ/СПС этот аргумент не передают.
    max_row_width_mm — передаётся в sync_rooms_in_level как есть (см. её
    docstring — перенос помещений по строкам внутри этажа при превышении
    этой ширины, по умолчанию 0 — без переноса). Место под дополнительные
    строки (row_wrap_extra_mm, возврат sync_rooms_in_level) добавляется к
    extra_bottom_mm для КОНКРЕТНОГО этажа — у разных этажей число строк
    может быть разным, поэтому, в отличие от extra_bottom_mm/extra_left_mm,
    это не общий на все этажи параметр, а свой у каждого; общий механизм
    "растянуть рамку вниз" (`_draw_level_frame`) при этом тот же самый.

    stats (если передан) — тот же словарь-счётчик, что и у
    sync_rooms_in_level, дополнительно получает
    "levels_unchanged"/"levels_moved"/"levels_created"/"levels_redrawn"/"levels_removed".

    timing — если передан словарь, копит в нём суммарное время (сек.) по
    видам Revit-операций внутри _place_room_group (см. её докстринг) —
    диагностика, чтобы увидеть, что именно на конкретной модели
    занимает время, вместо гаданий по общему времени вызова.

    Возвращает (new_state, report_rows); new_state — готов для
    sot_layout_state.save_state.
    """
    previous_levels = previous_state.get("levels", {}) if previous_state else {}
    extra_bottom_changed = (previous_state or {}).get("extra_bottom_mm", 0.0) != extra_bottom_mm
    extra_left_changed = (previous_state or {}).get("extra_left_mm", 0.0) != extra_left_mm

    y_cursor = 0.0
    new_levels_state = {}
    report_rows = []

    for level_key in level_order:
        room_groups = level_room_groups[level_key]
        level_label = level_labels[level_key]
        prev_level = previous_levels.get(level_key)
        prev_rooms = prev_level.get("rooms", {}) if prev_level else {}
        level_dy = 0.0 if prev_level is None else (y_cursor - prev_level.get("y", y_cursor))

        level_room_sort_values = (room_sort_values or {}).get(level_key)

        rooms_state, group_left, group_right, level_report_rows, row_wrap_extra_mm = sync_rooms_in_level(
            doc, view, level_label, y_cursor, level_dy, room_groups, category_symbols, category_for_device,
            room_param_name, address_param_name, device_uid_param_name, annotation_symbol,
            label_offset_mm, prev_rooms, unmatched_report, stats, level_room_sort_values,
            timing=timing, max_row_width_mm=max_row_width_mm
        )
        report_rows.extend(level_report_rows)

        if not rooms_state:
            if prev_level is not None:
                delete_elements(doc, _level_frame_element_ids(prev_level))
            continue

        level_extra_bottom_mm = extra_bottom_mm + row_wrap_extra_mm
        row_wrap_changed = (prev_level or {}).get("row_wrap_extra_mm", 0.0) != row_wrap_extra_mm

        y_changed = prev_level is None or abs(prev_level.get("y", 0.0) - y_cursor) > _TOLERANCE_FT
        right_changed = (
            prev_level is None
            or abs(prev_level.get("x_right", 0.0) - group_right) > _TOLERANCE_FT
            or extra_bottom_changed
            or extra_left_changed
            or row_wrap_changed
        )

        if prev_level is not None and not y_changed and not right_changed:
            level_record = {
                "y": y_cursor, "x_right": group_right, "row_wrap_extra_mm": row_wrap_extra_mm,
                "text_id": prev_level.get("text_id"), "line_ids": prev_level.get("line_ids", [])
            }
            _bump(stats, "levels_unchanged")
        elif prev_level is not None and y_changed and not right_changed:
            dy = y_cursor - prev_level["y"]
            translate_elements(doc, _level_frame_element_ids(prev_level), 0.0, dy)
            level_record = {
                "y": y_cursor, "x_right": group_right, "row_wrap_extra_mm": row_wrap_extra_mm,
                "text_id": prev_level.get("text_id"), "line_ids": prev_level.get("line_ids", [])
            }
            _bump(stats, "levels_moved")
        else:
            if prev_level is not None:
                delete_elements(doc, _level_frame_element_ids(prev_level))
                _bump(stats, "levels_redrawn")
            else:
                _bump(stats, "levels_created")
            text_id, line_ids = _draw_level_frame(
                doc, view, level_label, y_cursor, group_left, group_right, level_extra_bottom_mm, extra_left_mm
            )
            level_record = {
                "y": y_cursor, "x_right": group_right, "row_wrap_extra_mm": row_wrap_extra_mm,
                "text_id": text_id, "line_ids": line_ids
            }

        level_record["rooms"] = rooms_state
        new_levels_state[level_key] = level_record

        y_cursor -= (LEVEL_STEP_MM + level_extra_bottom_mm) * MM_TO_FT

    for level_key, prev_level in previous_levels.items():
        if level_key in new_levels_state:
            continue
        delete_elements(doc, _level_frame_element_ids(prev_level))
        for room_record in prev_level.get("rooms", {}).values():
            delete_elements(doc, _room_record_element_ids(room_record))
        _bump(stats, "levels_removed")

    return {
        "v": 1, "levels": new_levels_state,
        "extra_bottom_mm": extra_bottom_mm, "extra_left_mm": extra_left_mm
    }, report_rows


# ------------------------------------------------------------
# ЛИНИИ "УСТРОЙСТВО -> ШКАФ"
# ------------------------------------------------------------

def _iter_state_devices(state):
    """
    (uid, x, row_y, instance_id, flipped) для каждого устройства,
    размещённого на схеме (по итоговому state).

    row_y — Y СОБСТВЕННОЙ строки помещения (room_record["y"]), НЕ этажа
    целиком (level_record["y"]) — при переносе помещений по строкам
    (max_row_width_mm) у разных помещений одного этажа разный Y, а линии
    "устройство -> шкаф/панель" должны собираться в коллектор СВОЕЙ
    строки, а не тянуться через весь этаж до чужой. У помещений без
    собственного "y" в записи (сохранены до появления переноса по
    строкам — тогда все помещения были на Y этажа) — используется Y
    этажа как раньше.

    flipped — room_record["flipped"] (по умолчанию False) — строка
    отзеркалена (см. sync_rooms_in_level/_place_room_group): вызывающему
    коду (sync_cable_connections/scs_schematic.sync_panel_buses) нужно
    знать это, чтобы вести отвод от верхнего края узла и коллектор выше
    строки, а не как обычно — снизу.
    """
    for level_record in state.get("levels", {}).values():
        level_y = level_record.get("y", 0.0)
        for room_record in level_record.get("rooms", {}).values():
            row_y = room_record.get("y", level_y)
            flipped = bool(room_record.get("flipped", False))
            for uid, dev in room_record.get("devices", {}).items():
                yield uid, dev.get("x", 0.0), row_y, dev.get("instance_id"), flipped


def _node_bottom_y(doc, view, instance_id, fallback_y):
    """
    Y нижней границы УГО узла (bounding box схемного семейства в этом
    виде) — вертикальный отвод должен начинаться от границы значка, а не
    из его точки вставки (обычно это центр). Если элемент не резолвится
    или бокс недоступен — fallback_y (точка вставки), чтобы линия всё
    равно нарисовалась, а не пропала.
    """
    el = _resolve(doc, instance_id)
    if el is None:
        return fallback_y

    try:
        bbox = el.get_BoundingBox(view)
        if bbox is None:
            return fallback_y
        return bbox.Min.Y
    except:
        return fallback_y


def _node_top_y(doc, view, instance_id, fallback_y):
    """
    Зеркало _node_bottom_y — Y верхней границы УГО узла (bbox.Max.Y), а
    не нижней. Нужен для строк помещений, перенесённых по ширине и
    отзеркаленных (см. sync_rooms_in_level) — там соединительная линия
    "устройство -> шкаф/панель" должна начинаться от верхнего края
    значка, а не от нижнего (нижний занят маркой, см.
    place_node_annotation(below=True)).
    """
    el = _resolve(doc, instance_id)
    if el is None:
        return fallback_y

    try:
        bbox = el.get_BoundingBox(view)
        if bbox is None:
            return fallback_y
        return bbox.Max.Y
    except:
        return fallback_y


def sync_cable_connections(doc, view, new_state, old_cable_line_ids, cabinet_uid):
    """
    Линии "устройство -> шкаф" — шинная топология вместо звезды от каждого
    узла (та была рабочей, но давала три отдельных отрезка на каждое
    устройство, и на схемах с десятками узлов превращалась в кашу из
    накладывающихся линий):

    - на каждом этаже, где есть узлы, — один общий горизонтальный
      "коллектор", на CABLE_DROP_OFFSET_MM ниже узлов этого этажа (между
      нижней границей рамки помещения и разделительной линией этажа —
      место там уже есть, ничего не перекрывает);
    - от каждого узла этого этажа (включая шкаф, если он на этом же этаже)
      — короткий вертикальный отрезок вниз, до коллектора; начинается не
      из точки вставки узла (обычно это центр УГО), а от нижней границы
      его bounding box в этом виде (см. _node_bottom_y);
    - коллектор дотягивается по X до стояка (CABLE_RISER_OFFSET_MM левее
      рамок помещений);
    - один общий вертикальный стояк на всю схему — от самого верхнего до
      самого нижнего задействованного коллектора, через все этажи разом.

    Итого на этаж — 1 горизонтальная + по одной короткой вертикальной на
    узел, и один стояк на всю схему — вместо трёх отрезков на каждый узел.

    В отличие от помещений/этажей эти линии не редактируются руками и
    полностью выводятся из уже посчитанных позиций узлов, поэтому диффинг
    для них не нужен: на каждом запуске старые (old_cable_line_ids —
    state["cable_line_ids"] из предыдущего запуска) удаляются и рисуются
    заново по актуальным позициям из new_state (уже посчитанному
    sync_levels на этом запуске) — дешевле и надёжнее частичного
    обновления.

    cabinet_uid — UniqueId реального устройства категории "шкаф" (или
    None/не найден на схеме — тогда линии не рисуются вовсе, только
    удаляются старые). Возвращает новый список id линий (для state).
    """
    delete_elements(doc, old_cable_line_ids)

    if not cabinet_uid:
        return []

    devices = list(_iter_state_devices(new_state))
    device_by_uid = dict((uid, (x, y)) for uid, x, y, _iid, _flipped in devices)

    if cabinet_uid not in device_by_uid:
        return []

    doc.Regenerate()

    riser_x = -CABLE_RISER_OFFSET_MM * MM_TO_FT
    drop_offset = CABLE_DROP_OFFSET_MM * MM_TO_FT
    drop_offset_up = CABLE_DROP_OFFSET_UP_MM * MM_TO_FT

    # Группировка по (y, flipped) — y уже собственный y СТРОКИ помещения
    # (см. _iter_state_devices), а не этажа целиком, так что у разных
    # строк одного этажа он разный; flipped хранится отдельно (одинаков
    # для всех устройств одной группы — строка либо целиком отзеркалена,
    # либо нет), чтобы знать, в какую сторону вести коллектор этой группы.
    by_level_y = {}
    flipped_by_y = {}
    for uid, x, y, instance_id, flipped in devices:
        by_level_y.setdefault(y, []).append((x, instance_id))
        flipped_by_y[y] = flipped

    new_ids = []
    collector_ys = []

    for level_y, x_instance_list in by_level_y.items():
        flipped = flipped_by_y[level_y]
        collector_y = level_y + drop_offset_up if flipped else level_y - drop_offset
        collector_ys.append(collector_y)

        xs = [x for x, _iid in x_instance_list]
        x_min = min(xs + [riser_x])
        x_max = max(xs + [riser_x])

        elem = draw_segment(doc, view, x_min, collector_y, x_max, collector_y)
        if elem is not None:
            new_ids.append(elem.Id.IntegerValue)

        for x, instance_id in x_instance_list:
            drop_top_y = _node_top_y(doc, view, instance_id, level_y) if flipped \
                else _node_bottom_y(doc, view, instance_id, level_y)
            elem = draw_segment(doc, view, x, drop_top_y, x, collector_y)
            if elem is not None:
                new_ids.append(elem.Id.IntegerValue)

    if collector_ys:
        elem = draw_segment(doc, view, riser_x, min(collector_ys), riser_x, max(collector_ys))
        if elem is not None:
            new_ids.append(elem.Id.IntegerValue)

    return new_ids
