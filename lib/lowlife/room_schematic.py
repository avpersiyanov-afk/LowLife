# -*- coding: utf-8 -*-
"""
Отрисовка «рыбы структурной схемы» кнопки Schematic.panel/BuildRoomSchematic
— рамка на каждый выбранный уровень плюс один бокс с подписью на каждое
выбранное помещение/группу (room_schematic_picker.show) — БЕЗ семейств,
без узлов-устройств, без соединительных линий: только рамки и подписи, как
черновой скелет схемы, который дальше вручную доводится в самом Revit.

Переиспользует низкоуровневые чертёжные примитивы и геометрические
константы sot_schematic.py (тот же масштаб/стиль, что у СОТ/СПС/СКС) —
это чистые функции без побочной логики про устройства, поэтому берутся
как есть, без копирования. НЕ переиспользует sync_levels/sync_rooms_in_level/
_place_room_group/sot_layout_state — они спроектированы вокруг реальных
FamilyInstance-узлов и инкрементального diff по их UniqueId; здесь узлов
нет вообще, а раскладка при каждом запуске просто строится заново (см.
rebuild) — второй, куда более простой движок ради этого не нужен.

Каждый запуск кнопки полностью удаляет прежнее содержимое чертёжного вида
и рисует его заново — в отличие от sot_layout_state, здесь нет устройств
со своими ID, которые было бы жалко терять/двигать по отдельности, поэтому
полный передел проще и надёжнее собственного diff-движка ради текстовых
боксов.
"""

from Autodesk.Revit.DB import (
    FilteredElementCollector, View, ViewDrafting, ViewFamilyType, ViewFamily
)

from lowlife.sot_levels import get_level_label
from lowlife.sot_schematic import (
    MM_TO_FT, GROUP_GAP_MM, BOTTOM_LINE_MM, TOP_LINE_MM, HEADER_TOP_LINE_MM,
    TEXT_Y_MM, TEXT_CHAR_WIDTH_MM, TEXT_FRAME_MARGIN_MM, LEVEL_STEP_MM, ROW_WRAP_STEP_MM,
    create_room_text, center_text_in_frame, draw_vertical_line, draw_horizontal_line,
    _draw_level_frame,
)

SCHEMATIC_VIEW_NAME = u"Структурная схема (черновик)"

# Максимальная ширина одного ряда боксов на этаже, мм — после этой ширины
# следующий бокс переносится на новую строку ниже (см. _place_level_boxes),
# как в sot_schematic.sync_rooms_in_level, но без настройки в v1 — тут нет
# ни устройств, ни marks, растягивать масштаб схемы завязкой на проектные
# настройки пока незачем.
MAX_ROW_WIDTH_MM = 3000.0

# Минимальная ширина бокса (мм) — чтобы совсем короткие подписи (например
# один номер помещения) не давали визуально "схлопнутую" рамку.
MIN_BOX_WIDTH_MM = 30.0


def _box_width_ft(label):
    text_width_ft = len(label or u"") * TEXT_CHAR_WIDTH_MM * MM_TO_FT
    text_required_ft = text_width_ft + TEXT_FRAME_MARGIN_MM * MM_TO_FT
    return max(MIN_BOX_WIDTH_MM * MM_TO_FT, text_required_ft)


def _place_box(doc, view, x_pos, label, current_level_y, width_ft):
    """Рисует один бокс (рамка + центрированная подпись) в позиции x_pos,
    той же высоты/пропорций, что и помещение без устройств у sot_schematic
    (BOTTOM_LINE_MM..HEADER_TOP_LINE_MM). Возвращает (x_left, x_right)."""
    x_left = x_pos
    x_right = x_pos + width_ft
    x_center = (x_left + x_right) / 2.0
    text_y = current_level_y + TEXT_Y_MM * MM_TO_FT

    text_note = create_room_text(doc, view, label, x_center, text_y)
    if text_note is not None:
        center_text_in_frame(doc, text_note, view, x_left, x_right, text_y)

    draw_vertical_line(doc, view, x_left, current_level_y, BOTTOM_LINE_MM, HEADER_TOP_LINE_MM)
    draw_vertical_line(doc, view, x_right, current_level_y, BOTTOM_LINE_MM, HEADER_TOP_LINE_MM)
    draw_horizontal_line(doc, view, x_left, x_right, current_level_y + BOTTOM_LINE_MM * MM_TO_FT)
    draw_horizontal_line(doc, view, x_left, x_right, current_level_y + TOP_LINE_MM * MM_TO_FT)
    draw_horizontal_line(doc, view, x_left, x_right, current_level_y + HEADER_TOP_LINE_MM * MM_TO_FT)

    return x_left, x_right


def _place_level_boxes(doc, view, current_level_y, level_boxes):
    """
    Раскладывает боксы одного этажа слева направо, с переносом на новую
    строку при превышении MAX_ROW_WIDTH_MM (тот же приём, что первый проход
    sync_rooms_in_level: сперва считаем ширины и распределяем по строкам,
    потом рисуем). Возвращает (group_left, group_right, row_wrap_extra_mm)
    — последнее нужно вызывающему коду, чтобы растянуть рамку этажа под
    все строки (см. _draw_level_frame extra_bottom_mm).
    """
    max_row_width_ft = MAX_ROW_WIDTH_MM * MM_TO_FT
    widths = [_box_width_ft(box["label"]) for box in level_boxes]

    row_of_box = []
    row_x_cursor = 0.0
    current_row = 0
    for width in widths:
        if row_x_cursor > 0.0:
            projected_right = row_x_cursor + GROUP_GAP_MM * MM_TO_FT + width
            if projected_right > max_row_width_ft:
                current_row += 1
                row_x_cursor = 0.0
        if row_x_cursor > 0.0:
            row_x_cursor += GROUP_GAP_MM * MM_TO_FT
        row_of_box.append(current_row)
        row_x_cursor += width

    max_row_index = max(row_of_box) if row_of_box else 0

    group_left = None
    group_right = None
    x_cursor = 0.0
    active_row = 0

    for box, width, row in zip(level_boxes, widths, row_of_box):
        if row != active_row:
            x_cursor = 0.0
            active_row = row
        row_y = current_level_y - row * ROW_WRAP_STEP_MM * MM_TO_FT
        x_left, x_right = _place_box(doc, view, x_cursor, box["label"], row_y, width)
        group_left = x_left if group_left is None else min(group_left, x_left)
        group_right = x_right if group_right is None else max(group_right, x_right)
        x_cursor = x_right + GROUP_GAP_MM * MM_TO_FT

    row_wrap_extra_mm = max_row_index * ROW_WRAP_STEP_MM if max_row_index > 0 else 0.0
    return group_left, group_right, row_wrap_extra_mm


def _find_view_by_name(doc, name):
    """(view, name_conflict) — вид с точным именем name, либо (None, True),
    если он есть, но не ViewDrafting, либо (None, False), если такого вида
    вообще нет (первый запуск — нужно создать)."""
    try:
        views = FilteredElementCollector(doc).OfClass(View).ToElements()
    except Exception:
        return None, False

    for view in views:
        try:
            view_name = view.Name
        except Exception:
            continue
        if view_name == name:
            if isinstance(view, ViewDrafting):
                return view, False
            return None, True

    return None, False


def check_view(doc):
    """
    (view, drafting_type_id, error) — вызывать ДО открытия транзакции
    (только читает модель, как и BuildSotSchematic перед своим
    is_new_view/drafting_type_id):
      - вид с именем SCHEMATIC_VIEW_NAME уже есть и это ViewDrafting ->
        (view, None, None);
      - вид с таким именем есть, но не чертёжный -> (None, None, текст
        ошибки) — переименовать/удалить должен пользователь;
      - вида нет -> (None, drafting_type_id, None), либо (None, None,
        текст ошибки), если в проекте вовсе нет ViewFamilyType для
        чертёжных видов (не должно случаться в обычном проекте, но
        встречается в шаблонах с урезанным набором типов видов).
    """
    view, name_conflict = _find_view_by_name(doc, SCHEMATIC_VIEW_NAME)
    if name_conflict:
        return None, None, (
            u"Вид «{}» уже существует, но не является чертёжным. "
            u"Переименуйте его или удалите.".format(SCHEMATIC_VIEW_NAME)
        )
    if view is not None:
        return view, None, None

    drafting_type_id = None
    for vft in FilteredElementCollector(doc).OfClass(ViewFamilyType).ToElements():
        try:
            if vft.ViewFamily == ViewFamily.Drafting:
                drafting_type_id = vft.Id
                break
        except Exception:
            continue

    if drafting_type_id is None:
        return None, None, u"В проекте не найден ViewFamilyType для чертёжных видов (Drafting)."

    return None, drafting_type_id, None


def create_view(doc, drafting_type_id):
    """Создаёт и именует новый чертёжный вид схемы. Вызывать внутри транзакции."""
    view = ViewDrafting.Create(doc, drafting_type_id)
    view.Name = SCHEMATIC_VIEW_NAME
    view.Scale = 1
    return view


def _clear_view(doc, view):
    """Удаляет всё содержимое вида (кроме самого вида) — см. модульный
    докстринг: перерисовка "с нуля" при каждом запуске, без diff-состояния."""
    try:
        ids = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType().ToElementIds()
    except Exception:
        return
    if ids.Count == 0:
        return
    try:
        doc.Delete(ids)
    except Exception:
        for eid in ids:
            try:
                doc.Delete(eid)
            except Exception:
                pass


def rebuild(doc, view, boxes):
    """
    boxes — OrderedDict(level_name -> [box, ...]), как возвращает
    room_schematic_picker.show (box = {"kind", "label", "room_ids"}).
    Полностью перерисовывает view. Возвращает (num_levels, num_boxes).
    Вызывать внутри транзакции.
    """
    _clear_view(doc, view)

    y_cursor = 0.0
    num_levels = 0
    num_boxes = 0

    for level_name, level_boxes in boxes.items():
        if not level_boxes:
            continue

        level_label = get_level_label(level_name)
        group_left, group_right, row_wrap_extra_mm = _place_level_boxes(
            doc, view, y_cursor, level_boxes
        )
        _draw_level_frame(doc, view, level_label, y_cursor, group_left, group_right, row_wrap_extra_mm)

        num_levels += 1
        num_boxes += len(level_boxes)
        y_cursor -= (LEVEL_STEP_MM + row_wrap_extra_mm) * MM_TO_FT

    return num_levels, num_boxes
