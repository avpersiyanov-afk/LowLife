# -*- coding: utf-8 -*-
"""
Окно настроек кнопки «Точки доступа на двери» (SKUD.panel/PlaceDoorAccessPoints,
Shift+клик) + их хранение между запусками.

Хранится в отдельном JSON-файле %APPDATA%\\pyRevit\\LowLifeSkudDoorPlacement_settings.json
— по образцу companion_placement_settings.py (простой файл вместо
pyrevit.script.get_config(), см. докстринг scs_settings.py).

Окно — мнемосхема двери: два вида на дверь (снаружи и изнутри помещения),
на которых маркерами показаны места устройств точки доступа, и под ними
таблица мест: для каждой стороны × роли (считыватель, замок, доводчик,
геркон, кнопка экстренной разблокировки, домофон, кнопка выхода) —
какие СЕМЕЙСТВА могут стоять на этом месте, привязка (от левого/правого
края двери или над дверью), расстояние, высота и отступ от стены.
Мнемосхема перерисовывается сразу при правке чисел.

Семейства хранятся по ИМЕНИ (не по ElementId) — так настройки
переносятся между проектами без переназначения. Типы семейств здесь не
выбираются вообще: их даёт группа, выбранная для помещения при запуске
кнопки (см. skud_door_placement.py).

Там же (ключ room_groups) запоминается, какая группа была выбрана для
какого помещения в прошлый раз — таблица помещений подставляет её снова.
"""

import os
import io
import json

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('RevitAPI')

from Autodesk.Revit.DB import FilteredElementCollector, Family, CategoryType

from pyrevit import forms

from System.Windows import (
    Window, WindowStartupLocation, Thickness, FontWeights,
    HorizontalAlignment, VerticalAlignment, TextWrapping, GridLength, GridUnitType
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, ComboBox, Orientation, DockPanel, Dock,
    ScrollViewer, ScrollBarVisibility, Canvas, Grid, ColumnDefinition, RowDefinition, Border
)
from System.Windows.Media import Brushes, SolidColorBrush, ColorConverter, DoubleCollection
from System.Windows.Shapes import Rectangle, Ellipse, Line

from lowlife import settings_transfer
from lowlife import skud_door_layout as layout
from lowlife.scs import safe_element_name

SETTINGS_FILE_NAME = "LowLifeSkudDoorPlacement_settings.json"

# Размеры двери, по которым рисуется мнемосхема (реальные размеры при
# расстановке берутся с каждой двери).
PREVIEW_DOOR_WIDTH_MM = 900.0
PREVIEW_DOOR_HEIGHT_MM = 2100.0
PREVIEW_SCALE = 0.1  # px на мм
CANVAS_WIDTH = 400.0
CANVAS_HEIGHT = 300.0
FLOOR_Y = 280.0


def _settings_file_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(appdata, "pyRevit")

    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except:
            pass

    return os.path.join(folder, SETTINGS_FILE_NAME)


def _read_all():
    path = _settings_file_path()

    if not os.path.isfile(path):
        return {}

    try:
        with io.open(path, "r", encoding="utf-8") as f:
            text = f.read()
        if not text.strip():
            return {}
        return json.loads(text)
    except:
        return {}


def _write_all(data):
    path = _settings_file_path()

    try:
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(unicode(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)))
    except:
        forms.alert(u"Не удалось сохранить настройки в файл:\n{}".format(path))


def load_saved_values():
    """{"slots": {key: slot}, "room_groups": {room_key: group_name}} — всегда все места."""
    saved = _read_all()
    raw_slots = saved.get("slots") or {}
    slots = {}
    for key in layout.all_slot_keys():
        side, role = layout.split_slot_key(key)
        slot = layout.default_slot(side, role)
        slot.update(raw_slots.get(key) or {})
        if slot.get("anchor") not in layout.ANCHOR_KEYS:
            slot["anchor"] = "right"
        slot["families"] = [n for n in (slot.get("families") or []) if n]
        slots[key] = slot
    return {
        "slots": slots,
        "room_groups": dict(saved.get("room_groups") or {}),
    }


def save_slots(slots):
    data = _read_all()
    data["slots"] = slots
    _write_all(data)


def save_room_groups(room_groups):
    data = _read_all()
    merged = dict(data.get("room_groups") or {})
    merged.update(room_groups)
    data["room_groups"] = merged
    _write_all(data)


class FamilyOption(object):
    """Семейство для списка выбора (по имени; missing — нет в этом проекте)."""

    def __init__(self, family_name, category_name=u"", missing=False):
        self.family_name = family_name
        if missing:
            self.name = u"{}  (нет в проекте)".format(family_name)
        elif category_name:
            self.name = u"{}  [{}]".format(family_name, category_name)
        else:
            self.name = family_name

    def __str__(self):
        return self.name


def list_model_families(doc):
    """[(имя семейства, имя категории)] всех загруженных модельных семейств."""
    result = []
    seen = set()
    for family in FilteredElementCollector(doc).OfClass(Family):
        name = safe_element_name(family)
        if not name or name in seen:
            continue
        category_name = u""
        try:
            category = family.FamilyCategory
            if category is not None:
                if category.CategoryType != CategoryType.Model:
                    continue
                category_name = category.Name
        except:
            pass
        seen.add(name)
        result.append((name, category_name))
    return sorted(result, key=lambda item: (item[1], item[0].lower()))


def _brush(hex_color):
    return SolidColorBrush(ColorConverter.ConvertFromString(hex_color))


def _role_info(role_key):
    for key, label, short, color in layout.ROLES:
        if key == role_key:
            return label, short, color
    return role_key, role_key, "#555555"


def _draw_door_view(canvas, side, slots):
    """Перерисовывает один вид мнемосхемы (стена, проём, маркеры мест)."""
    canvas.Children.Clear()

    wall = Rectangle()
    wall.Width = CANVAS_WIDTH
    wall.Height = FLOOR_Y
    wall.Fill = _brush("#E4E9EE")
    canvas.Children.Add(wall)

    door_w = PREVIEW_DOOR_WIDTH_MM * PREVIEW_SCALE
    door_h = PREVIEW_DOOR_HEIGHT_MM * PREVIEW_SCALE
    cx = CANVAS_WIDTH / 2.0

    opening = Rectangle()
    opening.Width = door_w
    opening.Height = door_h
    opening.Fill = Brushes.White
    opening.Stroke = _brush("#4A5A6A")
    opening.StrokeThickness = 2
    Canvas.SetLeft(opening, cx - door_w / 2.0)
    Canvas.SetTop(opening, FLOOR_Y - door_h)
    canvas.Children.Add(opening)

    leaf = Rectangle()
    leaf.Width = door_w - 12
    leaf.Height = door_h - 6
    leaf.Stroke = _brush("#9AA8B6")
    leaf.StrokeThickness = 1
    Canvas.SetLeft(leaf, cx - door_w / 2.0 + 6)
    Canvas.SetTop(leaf, FLOOR_Y - door_h + 6)
    canvas.Children.Add(leaf)

    floor = Line()
    floor.X1 = 0
    floor.X2 = CANVAS_WIDTH
    floor.Y1 = FLOOR_Y
    floor.Y2 = FLOOR_Y
    floor.Stroke = _brush("#4A5A6A")
    floor.StrokeThickness = 2
    canvas.Children.Add(floor)

    axis = Line()
    axis.X1 = cx
    axis.X2 = cx
    axis.Y1 = 4
    axis.Y2 = FLOOR_Y
    axis.Stroke = _brush("#B0BAC4")
    axis.StrokeThickness = 1
    dashes = DoubleCollection()
    dashes.Add(4)
    dashes.Add(3)
    axis.StrokeDashArray = dashes
    canvas.Children.Add(axis)

    for role_key, _label, _short, _color in layout.ROLES:
        key = layout.slot_key(side, role_key)
        slot = slots.get(key)
        if not slot:
            continue
        label, short, color = _role_info(role_key)
        u, z, _depth = layout.slot_local_position(slot, PREVIEW_DOOR_WIDTH_MM, PREVIEW_DOOR_HEIGHT_MM)
        x = cx + u * PREVIEW_SCALE
        y = FLOOR_Y - z * PREVIEW_SCALE
        x = max(7.0, min(CANVAS_WIDTH - 7.0, x))
        y = max(7.0, min(FLOOR_Y - 2.0, y))
        is_active = bool(slot.get("families"))

        marker = Ellipse()
        marker.Width = 14
        marker.Height = 14
        marker.Fill = _brush(color) if is_active else Brushes.White
        marker.Stroke = _brush(color)
        marker.StrokeThickness = 2
        marker.ToolTip = u"{} — {}".format(
            label, u", ".join(slot.get("families") or []) or u"семейства не выбраны"
        )
        Canvas.SetLeft(marker, x - 7)
        Canvas.SetTop(marker, y - 7)
        canvas.Children.Add(marker)

        text = TextBlock()
        text.Text = short
        text.FontSize = 10
        text.FontWeight = FontWeights.Bold
        text.Foreground = _brush(color) if is_active else Brushes.Gray
        Canvas.SetLeft(text, x + 8 if x < CANVAS_WIDTH - 40 else x - 30)
        Canvas.SetTop(text, y - 7)
        canvas.Children.Add(text)


def _families_text(names):
    return u", ".join(names) if names else u"— не выбрано (место не используется)"


def show_settings_form(doc, values):
    """Модальное окно мнемосхемы. Возвращает slots, None (Отмена) или
    settings_transfer.RELOAD (после загрузки настроек из файла)."""
    result = {"slots": None}
    slots = dict((key, dict(slot)) for key, slot in values["slots"].items())
    canvases = {}

    win = Window()
    win.Title = u"Настройки: Точки доступа на двери"
    win.Width = 1120
    win.Height = 860
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    # --- шапка + мнемосхема (не прокручивается) ---

    header = StackPanel()
    header.Margin = Thickness(16, 12, 16, 4)
    DockPanel.SetDock(header, Dock.Top)

    title = TextBlock()
    title.Text = u"Мнемосхема двери"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    header.Children.Add(title)

    hint = TextBlock()
    hint.Text = (
        u"Для каждого места укажите, какие СЕМЕЙСТВА могут на нём стоять, и где "
        u"оно находится относительно двери. Тип семейства берётся из группы, "
        u"выбранной для помещения при запуске кнопки: каждый элемент группы "
        u"встаёт на первое свободное место, где указано его семейство "
        u"(сначала снаружи, потом внутри). «Левый/правый край» — как видит "
        u"дверь человек, стоящий с этой стороны; расстояние — от края проёма "
        u"в сторону стены. Высота — от низа двери (для «над дверью» — от "
        u"верха двери). «От стены» — отступ от поверхности стены к "
        u"наблюдателю. Места без семейств не используются (маркер пустой)."
    )
    hint.FontSize = 11
    hint.Foreground = Brushes.Gray
    hint.TextWrapping = TextWrapping.Wrap
    hint.Margin = Thickness(0, 2, 0, 8)
    header.Children.Add(hint)

    views_row = StackPanel()
    views_row.Orientation = Orientation.Horizontal
    for side, side_label in layout.SIDES:
        box = StackPanel()
        box.Margin = Thickness(0, 0, 24, 0)
        caption = TextBlock()
        caption.Text = u"{} — вид на дверь".format(side_label)
        caption.FontWeight = FontWeights.Bold
        caption.Margin = Thickness(0, 0, 0, 4)
        box.Children.Add(caption)

        canvas = Canvas()
        canvas.Width = CANVAS_WIDTH
        canvas.Height = CANVAS_HEIGHT
        canvas.ClipToBounds = True
        frame = Border()
        frame.BorderBrush = _brush("#B0BAC4")
        frame.BorderThickness = Thickness(1)
        frame.Child = canvas
        box.Children.Add(frame)
        canvases[side] = canvas
        views_row.Children.Add(box)

    legend = StackPanel()
    legend.VerticalAlignment = VerticalAlignment.Bottom
    for _key, label, short, color in layout.ROLES:
        item = TextBlock()
        item.Text = u"{} — {}".format(short, label)
        item.Foreground = _brush(color)
        item.FontSize = 11
        legend.Children.Add(item)
    legend_note = TextBlock()
    legend_note.Text = u"Закрашен — место используется,\nпустой — семейства не выбраны."
    legend_note.FontSize = 10
    legend_note.Foreground = Brushes.Gray
    legend_note.Margin = Thickness(0, 6, 0, 0)
    legend.Children.Add(legend_note)
    views_row.Children.Add(legend)
    header.Children.Add(views_row)

    def redraw():
        for side, canvas in canvases.items():
            _draw_door_view(canvas, side, slots)

    # --- таблица мест (прокручивается) ---

    table = StackPanel()
    table.Margin = Thickness(16, 4, 16, 8)

    column_widths = [210, None, 90, 150, 70, 70, 70]
    column_titles = [u"Место", u"Семейства", u"", u"Привязка", u"Расст., мм", u"Высота, мм", u"От стены, мм"]

    def make_grid():
        grid = Grid()
        for width in column_widths:
            column = ColumnDefinition()
            if width is None:
                column.Width = GridLength(1, GridUnitType.Star)
            else:
                column.Width = GridLength(width)
            grid.ColumnDefinitions.Add(column)
        return grid

    def place(grid, element, column):
        Grid.SetColumn(element, column)
        element.Margin = Thickness(2, 2, 6, 2)
        element.VerticalAlignment = VerticalAlignment.Center
        grid.Children.Add(element)

    family_cache = {}

    def model_families():
        if "items" not in family_cache:
            family_cache["items"] = list_model_families(doc)
        return family_cache["items"]

    for side, side_label in layout.SIDES:
        section = TextBlock()
        section.Text = side_label
        section.FontSize = 14
        section.FontWeight = FontWeights.Bold
        section.Margin = Thickness(0, 10, 0, 4)
        table.Children.Add(section)

        head = make_grid()
        for index, text in enumerate(column_titles):
            cell = TextBlock()
            cell.Text = text
            cell.FontWeight = FontWeights.Bold
            cell.FontSize = 11
            place(head, cell, index)
        table.Children.Add(head)

        for role_key, _label, _short, _color in layout.ROLES:
            key = layout.slot_key(side, role_key)
            slot = slots[key]
            label, short, color = _role_info(role_key)
            row = make_grid()

            name_cell = TextBlock()
            name_cell.Text = u"{} ({})".format(label, short)
            name_cell.Foreground = _brush(color)
            name_cell.TextWrapping = TextWrapping.Wrap
            place(row, name_cell, 0)

            families_cell = TextBlock()
            families_cell.Text = _families_text(slot["families"])
            families_cell.TextWrapping = TextWrapping.Wrap
            place(row, families_cell, 1)

            buttons_cell = StackPanel()
            buttons_cell.Orientation = Orientation.Horizontal
            pick_btn = Button()
            pick_btn.Content = u"Выбрать…"
            pick_btn.Padding = Thickness(6, 1, 6, 1)
            clear_btn = Button()
            clear_btn.Content = u"×"
            clear_btn.ToolTip = u"Очистить список семейств"
            clear_btn.Padding = Thickness(6, 1, 6, 1)
            clear_btn.Margin = Thickness(4, 0, 0, 0)
            buttons_cell.Children.Add(pick_btn)
            buttons_cell.Children.Add(clear_btn)
            place(row, buttons_cell, 2)

            def on_pick(sender, args, key=key, label=label, side_label=side_label,
                        families_cell=families_cell):
                current = slots[key]["families"]
                current_lower = set(layout.normalize_family_name(n) for n in current)
                available = model_families()
                available_lower = set(layout.normalize_family_name(n) for n, _c in available)
                options = [FamilyOption(n, c) for n, c in available]
                options += [FamilyOption(n, missing=True) for n in current
                            if layout.normalize_family_name(n) not in available_lower]
                items = [forms.TemplateListItem(o, checked=(
                    layout.normalize_family_name(o.family_name) in current_lower))
                    for o in options]
                chosen = forms.SelectFromList.show(
                    items,
                    title=u"Семейства: {} — {}".format(label, side_label.lower()),
                    button_name=u"Выбрать",
                    multiselect=True
                )
                if chosen is None:
                    return
                slots[key]["families"] = [o.family_name for o in chosen]
                families_cell.Text = _families_text(slots[key]["families"])
                redraw()

            def on_clear(sender, args, key=key, families_cell=families_cell):
                slots[key]["families"] = []
                families_cell.Text = _families_text([])
                redraw()

            pick_btn.Click += on_pick
            clear_btn.Click += on_clear

            anchor_box = ComboBox()
            for _anchor_key, anchor_label in layout.ANCHORS:
                anchor_box.Items.Add(anchor_label)
            anchor_box.SelectedIndex = layout.ANCHOR_KEYS.index(slot["anchor"])

            def on_anchor(sender, args, key=key, anchor_box=anchor_box):
                index = anchor_box.SelectedIndex
                if 0 <= index < len(layout.ANCHOR_KEYS):
                    slots[key]["anchor"] = layout.ANCHOR_KEYS[index]
                    redraw()

            anchor_box.SelectionChanged += on_anchor
            place(row, anchor_box, 3)

            for column, field in ((4, "offset_mm"), (5, "height_mm"), (6, "depth_mm")):
                box = TextBox()
                box.Text = u"{}".format(slot.get(field, u"0"))
                box.Padding = Thickness(3, 1, 3, 1)

                def on_changed(sender, args, key=key, field=field, box=box):
                    slots[key][field] = box.Text
                    redraw()

                box.TextChanged += on_changed
                place(row, box, column)

            table.Children.Add(row)

    # --- нижний ряд кнопок ---

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(16, 8, 16, 12)
    DockPanel.SetDock(buttons, Dock.Bottom)

    cancel_btn = Button()
    cancel_btn.Content = u"Отмена"
    cancel_btn.Padding = Thickness(10, 4, 10, 4)
    cancel_btn.Margin = Thickness(0, 0, 8, 0)

    ok_btn = Button()
    ok_btn.Content = u"Сохранить"
    ok_btn.Padding = Thickness(10, 4, 10, 4)
    ok_btn.FontWeight = FontWeights.Bold

    def on_ok(sender, args):
        result["slots"] = slots
        win.Close()

    def on_cancel(sender, args):
        win.Close()

    ok_btn.Click += on_ok
    cancel_btn.Click += on_cancel

    buttons.Children.Add(cancel_btn)
    buttons.Children.Add(ok_btn)

    def _on_settings_imported():
        result["slots"] = settings_transfer.RELOAD
        win.Close()

    settings_transfer.add_transfer_buttons(
        buttons, _read_all, _write_all, u"точек доступа на двери", _on_settings_imported
    )

    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scroll.Content = table

    outer.Children.Add(header)
    outer.Children.Add(buttons)
    outer.Children.Add(scroll)

    redraw()

    win.Content = outer
    win.ShowDialog()

    return result["slots"]


def get_settings_interactive(doc):
    """Окно мнемосхемы (Shift+клик). Возвращает сохранённые места или None (Отмена)."""
    while True:
        saved = load_saved_values()
        edited = show_settings_form(doc, saved)

        if edited == settings_transfer.RELOAD:
            continue

        if edited is None:
            return None

        save_slots(edited)
        return edited


def get_settings_silent():
    """Сохранённые места и выбор групп по помещениям — без окна."""
    return load_saved_values()


def require_active_slots(values):
    """Места с семействами; если ни одного — стоп с подсказкой про Shift+клик."""
    active = layout.active_slots(values["slots"])
    if not active:
        forms.alert(
            u"На мнемосхеме двери не выбрано ни одного семейства.\n\n"
            u"Откройте настройки: Shift+клик по кнопке «Точки доступа на двери» "
            u"и для нужных мест (считыватель, замок, ...) выберите семейства.",
            exitscript=True
        )
    return active
