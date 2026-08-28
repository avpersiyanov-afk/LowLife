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
# (коллектор) на каждом этаже — см. sync_cable_connections.
CABLE_DROP_OFFSET_MM = 15.0

# Вертикальный шаг между "начальной" Y одного этажа и следующего — не
# зависит от содержимого (только от констант выше), поэтому вставка/
# удаление целого этажа — это ровно сдвиг нижестоящих на этот шаг, без
# пересчёта позиций внутри них. См. sync_levels.
LEVEL_STEP_MM = (-BOTTOM_LINE_MM) + LEVEL_SEPARATOR_OFFSET_MM + LEVEL_NEXT_GAP_MM + HEADER_TOP_LINE_MM

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

def place_node_annotation(doc, view, node_instance, annotation_symbol, x, current_level_y, label_offset_mm):
    """
    Ставит марку (IndependentTag) типа annotation_symbol на node_instance —
    марка сама читает "Обозначение"/"Адрес" с помеченного элемента через
    свои поля-метки, ничего сюда передавать/копировать не нужно. Марка —
    горизонтальная (TagOrientation.Horizontal), без выноски, головка по
    центру узла на label_offset_mm выше точки вставки (настройка СОТ
    "Смещение марки узла вверх от точки вставки, мм").
    """
    if annotation_symbol is None or node_instance is None:
        return None

    try:
        if not annotation_symbol.IsActive:
            annotation_symbol.Activate()
            doc.Regenerate()

        point = XYZ(x, current_level_y + label_offset_mm * MM_TO_FT, 0.0)

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


# ------------------------------------------------------------
# ГРУППА ПОМЕЩЕНИЯ (ряд узлов + рамка) — рисование "с нуля"
# ------------------------------------------------------------

def _place_room_group(doc, view, x_pos, room_key, valid_devices, room_param_name,
                       address_param_name, device_uid_param_name, annotation_symbol,
                       label_offset_mm, current_level_y, timing=None):
    """
    Рисует помещение с нуля в позиции x_pos — используется и для первой
    постройки схемы, и для перерисовки помещения, чьё содержимое
    изменилось (sync_rooms_in_level). valid_devices — [(device, symbol), ...],
    уже отсортированные вызывающим кодом по адресу устройства (стабильный
    порядок слотов между запусками).

    timing — если передан словарь, копит в нём суммарное время (сек.) по
    видам операций ("text"/"lines"/"symbol_activate"/"instance"/"params"/
    "tag") — диагностика, откуда реально уходит время на конкретной
    модели (см. _bump_time). None по умолчанию — без замеров.

    Возвращает (room_record, report_rows) — room_record идёт в state
    (см. sot_layout_state), report_rows — [(room_key, address), ...].
    """
    offset = LINE_OFFSET_MM * MM_TO_FT
    step = STEP_MM * MM_TO_FT
    text_margin = TEXT_MARGIN_MM * MM_TO_FT
    text_y = TEXT_Y_MM * MM_TO_FT

    nodes_width = 2.0 * offset + (len(valid_devices) - 1) * step
    preliminary_center_x = x_pos + nodes_width / 2.0

    _t0 = time.time()
    text_note = create_room_text(doc, view, room_key, preliminary_center_x, current_level_y + text_y)

    # Ширина по символам, а не по реальному BoundingBox (это требовало бы
    # doc.Regenerate() — убрано целиком, см. center_text_in_frame) — нужна
    # только чтобы решить max(nodes_width, text_required_width): при 2+
    # устройствах в помещении nodes_width почти всегда и так больше, так
    # что грубая оценка ширины текста ни на что не влияет; разве что для
    # одиночных устройств с длинным именем помещения рамка может оказаться
    # чуть уже, чем по факту нужно тексту — сам текст всё равно останется
    # отцентрирован по X (center_text_in_frame ниже, через
    # HorizontalAlignment.Center), просто может на пару мм выйти за рамку
    # по ширине в редких случаях.
    text_width = len(room_key) * 2.5 * MM_TO_FT

    text_required_width = text_width + 2.0 * text_margin
    group_width = max(nodes_width, text_required_width)

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
                doc, view, node_instance, annotation_symbol, x_elem, current_level_y, label_offset_mm
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
    влево: на сколько мм дополнительно отодвинуть самую левую (третью)
    линию рамки левее обычного (по умолчанию 0); нужно, если левее рамок
    помещений рисуется что-то ещё, чем обычная ширина рамки не рассчитана
    (например СКС — несколько стояков панелей и дорожки магистралей, см.
    BuildScsSchematic). Возвращает (text_id, line_ids).
    """
    line_ids = []

    # base_bottom_y/level_lines_top_y — обычная (extra_bottom_mm=0) высота
    # рамки, верх (level_lines_top_y) всегда остаётся здесь же — растягиваем
    # только вниз, на extra_bottom_mm, а не сдвигаем всю рамку целиком
    # (иначе верх рамки оторвался бы от рамок помещений над ним).
    base_bottom_y = current_level_y + BOTTOM_LINE_MM * MM_TO_FT - LEVEL_SEPARATOR_OFFSET_MM * MM_TO_FT
    level_lines_top_y = base_bottom_y + LEVEL_VERTICAL_LINE_LENGTH_MM * MM_TO_FT
    bottom_level_line_y = base_bottom_y - extra_bottom_mm * MM_TO_FT

    # Аналогично extra_bottom_mm: первая и вторая линии (ближе к
    # помещениям) остаются на обычном месте, растягиваем только третью
    # (самую левую) — иначе "оторвались" бы от второй линии/подписи
    # этажа, которая между ними.
    first_level_line_x = group_left - LEVEL_LINE_1_OFFSET_MM * MM_TO_FT
    second_level_line_x = first_level_line_x - LEVEL_LINE_2_OFFSET_MM * MM_TO_FT
    third_level_line_x = second_level_line_x - (LEVEL_LINE_3_OFFSET_MM + extra_left_mm) * MM_TO_FT
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
                         timing=None):
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

    Для каждого помещения: если набор устройств (по UniqueId) не
    изменился — либо не трогаем вообще (позиция та же), либо просто
    переносим на новую позицию (ElementTransformUtils), если что-то левее
    сдвинулось и/или сдвинулся сам этаж; если набор изменился (или
    помещения раньше не было) — удаляем старые элементы (если были) и
    рисуем заново. Помещения, пропавшие из желаемого набора, удаляются
    целиком, следующие за ними автоматически "подтягиваются" — курсор x
    не резервирует под них место.

    stats (если передан) — словарь-счётчик, наращивает ключи
    "rooms_unchanged"/"rooms_moved"/"rooms_created"/"rooms_redrawn"/"rooms_removed"
    (единица измерения — помещение, не устройство: если содержимое
    помещения изменилось, всё помещение перерисовывается целиком).

    Возвращает (new_rooms_state, level_group_left, level_group_right, report_rows).
    """
    x_cursor = 0.0
    level_group_left = None
    level_group_right = None
    new_rooms_state = {}
    report_rows = []

    if room_sort_values is not None:
        sort_key_fn = lambda room_key: room_sort_values.get(room_key, float("inf"))
    else:
        sort_key_fn = _room_sort_key

    for room_key in sorted(room_groups.keys(), key=sort_key_fn):
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

        desired_uids = set(device.UniqueId for device, _symbol in valid_devices)
        prev_record = previous_rooms_state.get(room_key)
        prev_uids = set(prev_record["devices"].keys()) if prev_record else set()

        content_changed = (prev_record is None) or (desired_uids != prev_uids)

        if not content_changed:
            dx = x_cursor - prev_record["x_left"]
            room_moved = abs(dx) > _TOLERANCE_FT or abs(level_dy) > _TOLERANCE_FT
            if room_moved:
                translate_elements(doc, _room_record_element_ids(prev_record), dx, level_dy)
                _bump(stats, "rooms_moved")
            else:
                _bump(stats, "rooms_unchanged")

            new_devices_state = {}
            for device, _symbol in valid_devices:
                uid = device.UniqueId
                old_dev = prev_record["devices"][uid]
                instance = _resolve(doc, old_dev["instance_id"])
                new_x = old_dev["x"] + dx

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
                        doc, view, instance, annotation_symbol, new_x, current_level_y, label_offset_mm
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
                label_offset_mm, current_level_y, timing=timing
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

    return new_rooms_state, level_group_left, level_group_right, report_rows


# ------------------------------------------------------------
# ВСЕ ЭТАЖИ — инкрементальная синхронизация (верхний уровень)
# ------------------------------------------------------------

def sync_levels(doc, view, level_order, level_room_groups, level_labels, category_symbols,
                 category_for_device, room_param_name, address_param_name, device_uid_param_name,
                 annotation_symbol, label_offset_mm, previous_state, unmatched_report, stats=None,
                 extra_bottom_mm=0.0, extra_left_mm=0.0, room_sort_values=None, timing=None):
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

        rooms_state, group_left, group_right, level_report_rows = sync_rooms_in_level(
            doc, view, level_label, y_cursor, level_dy, room_groups, category_symbols, category_for_device,
            room_param_name, address_param_name, device_uid_param_name, annotation_symbol,
            label_offset_mm, prev_rooms, unmatched_report, stats, level_room_sort_values,
            timing=timing
        )
        report_rows.extend(level_report_rows)

        if not rooms_state:
            if prev_level is not None:
                delete_elements(doc, _level_frame_element_ids(prev_level))
            continue

        y_changed = prev_level is None or abs(prev_level.get("y", 0.0) - y_cursor) > _TOLERANCE_FT
        right_changed = (
            prev_level is None
            or abs(prev_level.get("x_right", 0.0) - group_right) > _TOLERANCE_FT
            or extra_bottom_changed
            or extra_left_changed
        )

        if prev_level is not None and not y_changed and not right_changed:
            level_record = {
                "y": y_cursor, "x_right": group_right,
                "text_id": prev_level.get("text_id"), "line_ids": prev_level.get("line_ids", [])
            }
            _bump(stats, "levels_unchanged")
        elif prev_level is not None and y_changed and not right_changed:
            dy = y_cursor - prev_level["y"]
            translate_elements(doc, _level_frame_element_ids(prev_level), 0.0, dy)
            level_record = {
                "y": y_cursor, "x_right": group_right,
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
                doc, view, level_label, y_cursor, group_left, group_right, extra_bottom_mm, extra_left_mm
            )
            level_record = {"y": y_cursor, "x_right": group_right, "text_id": text_id, "line_ids": line_ids}

        level_record["rooms"] = rooms_state
        new_levels_state[level_key] = level_record

        y_cursor -= (LEVEL_STEP_MM + extra_bottom_mm) * MM_TO_FT

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
    """(uid, x, level_y, instance_id) для каждого устройства, размещённого на схеме (по итоговому state)."""
    for level_record in state.get("levels", {}).values():
        y = level_record.get("y", 0.0)
        for room_record in level_record.get("rooms", {}).values():
            for uid, dev in room_record.get("devices", {}).items():
                yield uid, dev.get("x", 0.0), y, dev.get("instance_id")


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
    device_by_uid = dict((uid, (x, y)) for uid, x, y, _iid in devices)

    if cabinet_uid not in device_by_uid:
        return []

    doc.Regenerate()

    riser_x = -CABLE_RISER_OFFSET_MM * MM_TO_FT
    drop_offset = CABLE_DROP_OFFSET_MM * MM_TO_FT

    by_level_y = {}
    for uid, x, y, instance_id in devices:
        by_level_y.setdefault(y, []).append((x, instance_id))

    new_ids = []
    collector_ys = []

    for level_y, x_instance_list in by_level_y.items():
        collector_y = level_y - drop_offset
        collector_ys.append(collector_y)

        xs = [x for x, _iid in x_instance_list]
        x_min = min(xs + [riser_x])
        x_max = max(xs + [riser_x])

        elem = draw_segment(doc, view, x_min, collector_y, x_max, collector_y)
        if elem is not None:
            new_ids.append(elem.Id.IntegerValue)

        for x, instance_id in x_instance_list:
            drop_top_y = _node_bottom_y(doc, view, instance_id, level_y)
            elem = draw_segment(doc, view, x, drop_top_y, x, collector_y)
            if elem is not None:
                new_ids.append(elem.Id.IntegerValue)

    if collector_ys:
        elem = draw_segment(doc, view, riser_x, min(collector_ys), riser_x, max(collector_ys))
        if elem is not None:
            new_ids.append(elem.Id.IntegerValue)

    return new_ids
