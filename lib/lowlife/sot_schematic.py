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

Портировано из рабочего Dynamo-скрипта построения структурной схемы СОТ:
геометрия (шаги, отступы, длины линий) сохранена без изменений — это
чисто чертёжные константы, не связанные с настройками проекта.
"""

import math
import re

from Autodesk.Revit.DB import (
    XYZ, Line, TextNote, TextNoteType, TextNoteOptions,
    HorizontalTextAlignment, FilteredElementCollector, View,
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
NODE_LABEL_OFFSET_MM = 3.0

_ROOM_NUMBER_RE = re.compile(r"\((\d+)\)\s*$")
_ANY_NUMBER_RE = re.compile(r"\d+")


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
# ИМЯ ВИДА / ТИП ТЕКСТА
# ------------------------------------------------------------

def get_unique_view_name(doc, base_name):
    existing_names = set()

    try:
        for view in FilteredElementCollector(doc).OfClass(View).ToElements():
            try:
                existing_names.add(view.Name)
            except:
                pass
    except:
        pass

    if base_name not in existing_names:
        return base_name

    counter = 1
    while True:
        candidate = u"{}_{}".format(base_name, counter)
        if candidate not in existing_names:
            return candidate
        counter += 1


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
    if text_note is None:
        return False

    try:
        frame_center_x = (frame_left + frame_right) / 2.0
        move_text_to(doc, text_note, frame_center_x, target_y)
        doc.Regenerate()

        bbox = text_note.get_BoundingBox(view)
        if bbox is None:
            return False

        text_center_x = (bbox.Min.X + bbox.Max.X) / 2.0
        text_center_y = (bbox.Min.Y + bbox.Max.Y) / 2.0
        delta_x = frame_center_x - text_center_x
        delta_y = target_y - text_center_y

        if abs(delta_x) > 0.000001 or abs(delta_y) > 0.000001:
            ElementTransformUtils.MoveElement(doc, text_note.Id, XYZ(delta_x, delta_y, 0.0))

        return True
    except:
        return False


def center_level_text(doc, text_note, view, left_x, right_x, bottom_y, top_y):
    if text_note is None:
        return False

    try:
        center_x = (left_x + right_x) / 2.0
        center_y = (bottom_y + top_y) / 2.0
        move_text_to(doc, text_note, center_x, center_y)
        doc.Regenerate()

        bbox = text_note.get_BoundingBox(view)
        if bbox is None:
            return False

        actual_center_x = (bbox.Min.X + bbox.Max.X) / 2.0
        actual_center_y = (bbox.Min.Y + bbox.Max.Y) / 2.0
        delta_x = center_x - actual_center_x
        delta_y = center_y - actual_center_y

        if abs(delta_x) > 0.000001 or abs(delta_y) > 0.000001:
            ElementTransformUtils.MoveElement(doc, text_note.Id, XYZ(delta_x, delta_y, 0.0))

        return True
    except:
        return False


# ------------------------------------------------------------
# ЛИНИИ
# ------------------------------------------------------------

def draw_vertical_line(doc, view, x, y_offset=0.0):
    if view is None:
        return False
    try:
        y_min = y_offset + BOTTOM_LINE_MM * MM_TO_FT
        y_max = y_offset + HEADER_TOP_LINE_MM * MM_TO_FT
        start = XYZ(x, y_min, 0.0)
        end = XYZ(x, y_max, 0.0)
        if start.DistanceTo(end) < 0.001:
            return False
        doc.Create.NewDetailCurve(view, Line.CreateBound(start, end))
        return True
    except:
        return False


def draw_level_vertical_line(doc, view, x, bottom_y):
    if view is None:
        return False
    try:
        start = XYZ(x, bottom_y, 0.0)
        end = XYZ(x, bottom_y + LEVEL_VERTICAL_LINE_LENGTH_MM * MM_TO_FT, 0.0)
        if start.DistanceTo(end) < 0.001:
            return False
        doc.Create.NewDetailCurve(view, Line.CreateBound(start, end))
        return True
    except:
        return False


def draw_horizontal_line(doc, view, x_start, x_end, y):
    if view is None:
        return False
    try:
        start = XYZ(x_start, y, 0.0)
        end = XYZ(x_end, y, 0.0)
        if start.DistanceTo(end) < 0.001:
            return False
        doc.Create.NewDetailCurve(view, Line.CreateBound(start, end))
        return True
    except:
        return False


# ------------------------------------------------------------
# МАРКА УЗЛА (аннотация "Обозначение, Адрес" над схемным семейством)
# ------------------------------------------------------------

def place_node_annotation(doc, view, node_instance, annotation_symbol, x, current_level_y):
    """
    Ставит марку (IndependentTag) типа annotation_symbol на node_instance —
    марка сама читает "Обозначение"/"Адрес" с помеченного элемента через
    свои поля-метки, ничего сюда передавать/копировать не нужно. Марка —
    горизонтальная (TagOrientation.Horizontal), без выноски, головка по
    центру узла на NODE_LABEL_OFFSET_MM выше точки вставки.
    """
    if annotation_symbol is None or node_instance is None:
        return None

    try:
        if not annotation_symbol.IsActive:
            annotation_symbol.Activate()
            doc.Regenerate()

        point = XYZ(x, current_level_y + NODE_LABEL_OFFSET_MM * MM_TO_FT, 0.0)

        return IndependentTag.Create(
            doc, annotation_symbol.Id, view.Id, Reference(node_instance),
            False, TagOrientation.Horizontal, point
        )
    except:
        return None


# ------------------------------------------------------------
# ГРУППА ПОМЕЩЕНИЯ (ряд узлов + рамка) ВНУТРИ УРОВНЯ
# ------------------------------------------------------------

def _place_room_group(doc, view, x_pos, room_key, valid_devices, category_symbols,
                       room_param_name, address_param_name, annotation_symbol,
                       current_level_y, report_rows):
    """
    Возвращает (group_left_x, group_right_x, devices_placed) — валидные
    устройства уже отфильтрованы по наличию схемного символа у вызывающего
    кода (build_level_block), поэтому здесь всегда есть что размещать.

    Над каждым узлом ставится марка annotation_symbol (см.
    place_node_annotation), если она задана в настройках.
    """
    offset = LINE_OFFSET_MM * MM_TO_FT
    step = STEP_MM * MM_TO_FT
    text_margin = TEXT_MARGIN_MM * MM_TO_FT
    text_y = TEXT_Y_MM * MM_TO_FT

    nodes_width = 2.0 * offset + (len(valid_devices) - 1) * step
    preliminary_center_x = x_pos + nodes_width / 2.0

    text_note = create_room_text(doc, view, room_key, preliminary_center_x, current_level_y + text_y)
    text_width = get_text_width(doc, text_note, view)
    if text_width <= 0.0:
        text_width = len(room_key) * 2.5 * MM_TO_FT

    text_required_width = text_width + 2.0 * text_margin
    group_width = max(nodes_width, text_required_width)

    group_left_x = x_pos
    group_right_x = x_pos + group_width
    group_center_x = (group_left_x + group_right_x) / 2.0

    if text_note is not None:
        center_text_in_frame(doc, text_note, view, group_left_x, group_right_x, current_level_y + text_y)

    draw_vertical_line(doc, view, group_left_x, current_level_y)
    draw_vertical_line(doc, view, group_right_x, current_level_y)
    draw_horizontal_line(doc, view, group_left_x, group_right_x, current_level_y + BOTTOM_LINE_MM * MM_TO_FT)
    draw_horizontal_line(doc, view, group_left_x, group_right_x, current_level_y + TOP_LINE_MM * MM_TO_FT)
    draw_horizontal_line(doc, view, group_left_x, group_right_x, current_level_y + HEADER_TOP_LINE_MM * MM_TO_FT)

    nodes_center_width = (len(valid_devices) - 1) * step
    nodes_start_x = group_center_x - nodes_center_width / 2.0
    x_elem = nodes_start_x

    devices_placed = 0

    for device, symbol in valid_devices:
        if not symbol.IsActive:
            symbol.Activate()
            doc.Regenerate()

        placement_point = XYZ(x_elem, current_level_y, 0.0)
        node_instance = doc.Create.NewFamilyInstance(placement_point, symbol, view)

        if node_instance is not None:
            devices_placed += 1

            address_value = get_string_param(device, address_param_name)
            if address_value:
                set_param_any(node_instance, address_param_name, address_value)

            room_value = get_string_param(device, room_param_name)
            if room_value:
                set_param_any(node_instance, room_param_name, room_value)

            report_rows.append((room_key, address_value or u""))

            place_node_annotation(doc, view, node_instance, annotation_symbol, x_elem, current_level_y)

        x_elem += step

    return group_left_x, group_right_x, devices_placed


# ------------------------------------------------------------
# ОДИН УРОВЕНЬ ЦЕЛИКОМ
# ------------------------------------------------------------

def build_level_block(doc, view, level_key, room_groups, category_symbols,
                       category_for_device, current_level_y, room_param_name,
                       address_param_name, annotation_symbol, unmatched_report):
    """
    room_groups — OrderedDict(room_key -> [device, ...]).
    category_for_device(device) -> имя категории или None.
    category_symbols — {имя категории: FamilySymbol}.

    Возвращает новый current_level_y (для следующего, более низкого,
    уровня) и report_rows — список (room_key, address) размещённых
    устройств этого уровня.
    """
    x_pos = 0.0
    level_group_left = None
    level_group_right = None
    placed_room_groups = 0
    report_rows = []

    for room_key in sorted(room_groups.keys(), key=_room_sort_key):
        devices = room_groups[room_key]
        valid_devices = []

        for device in devices:
            category = category_for_device(device)
            symbol = category_symbols.get(category) if category else None
            if symbol is not None:
                valid_devices.append((device, symbol))
            else:
                unmatched_report.append((level_key, room_key, device))

        if not valid_devices:
            continue

        group_left_x, group_right_x, _placed = _place_room_group(
            doc, view, x_pos, room_key, valid_devices, category_symbols,
            room_param_name, address_param_name, annotation_symbol, current_level_y, report_rows
        )

        level_group_left = group_left_x if level_group_left is None else min(level_group_left, group_left_x)
        level_group_right = group_right_x if level_group_right is None else max(level_group_right, group_right_x)
        placed_room_groups += 1

        x_pos = group_right_x + GROUP_GAP_MM * MM_TO_FT

    if placed_room_groups == 0 or level_group_left is None or level_group_right is None:
        return current_level_y, report_rows

    bottom_level_line_y = current_level_y + BOTTOM_LINE_MM * MM_TO_FT - LEVEL_SEPARATOR_OFFSET_MM * MM_TO_FT

    first_level_line_x = level_group_left - LEVEL_LINE_1_OFFSET_MM * MM_TO_FT
    second_level_line_x = first_level_line_x - LEVEL_LINE_2_OFFSET_MM * MM_TO_FT
    third_level_line_x = second_level_line_x - LEVEL_LINE_3_OFFSET_MM * MM_TO_FT
    right_level_line_x = level_group_right + RIGHT_VERTICAL_LINE_OFFSET_MM * MM_TO_FT

    draw_level_vertical_line(doc, view, first_level_line_x, bottom_level_line_y)
    draw_level_vertical_line(doc, view, second_level_line_x, bottom_level_line_y)
    draw_level_vertical_line(doc, view, third_level_line_x, bottom_level_line_y)
    draw_level_vertical_line(doc, view, right_level_line_x, bottom_level_line_y)

    draw_horizontal_line(doc, view, third_level_line_x, right_level_line_x, bottom_level_line_y)

    continuous_top_line_y = current_level_y + (HEADER_TOP_LINE_MM + CONTINUOUS_TOP_LINE_OFFSET_MM) * MM_TO_FT
    draw_horizontal_line(doc, view, third_level_line_x, right_level_line_x, continuous_top_line_y)

    level_lines_top_y = bottom_level_line_y + LEVEL_VERTICAL_LINE_LENGTH_MM * MM_TO_FT
    level_text_x = (second_level_line_x + third_level_line_x) / 2.0
    level_text_y = (level_lines_top_y + bottom_level_line_y) / 2.0

    level_text_note = create_level_text(doc, view, level_key, level_text_x, level_text_y)
    if level_text_note is not None:
        center_level_text(
            doc, level_text_note, view,
            second_level_line_x, third_level_line_x,
            bottom_level_line_y, level_lines_top_y
        )

    next_level_y = bottom_level_line_y - LEVEL_NEXT_GAP_MM * MM_TO_FT - HEADER_TOP_LINE_MM * MM_TO_FT

    return next_level_y, report_rows
