# -*- coding: utf-8 -*-
"""
Окно настроек кнопки «Точки доступа на двери» (SKUD.panel/PlaceDoorAccessPoints,
Shift+клик) + их хранение между запусками.

Хранится в отдельном JSON-файле %APPDATA%\\pyRevit\\LowLifeSkudDoorPlacement_settings.json
— по образцу companion_placement_settings.py (простой файл вместо
pyrevit.script.get_config(), см. докстринг scs_settings.py).

Окно состоит из двух частей, которые работают вместе:

1. Мнемосхема двери — два вида на дверь (снаружи и изнутри помещения) и
   таблица мест (сторона × роль: считыватель, замок, доводчик, геркон,
   кнопка экстренной разблокировки, домофон, кнопка выхода). Для каждого
   места: какие СЕМЕЙСТВА могут на нём стоять, привязка (от левого/
   правого края двери или над дверью), расстояние, высота, отступ от
   стены, у замка и геркона — количество (2 — двустворчатая дверь, второй
   элемент зеркально относительно оси двери).

2. Типы точек доступа — именованные составы («ТД-1 вход по карте», ...).
   Выбранный вверху тип показывается прямо в таблице мест: колонка
   «Типоразмер» — какой типоразмер (из разрешённых на месте семейств)
   стоит на этом месте в этом типе; пусто — место в типе не используется.
   Мнемосхема рисует состав выбранного типа (закрашенный маркер — место
   занято в типе). Эти типы потом выбираются для помещений при запуске
   кнопки.

Семейства и типоразмеры хранятся по ИМЕНИ (не по ElementId) — так
настройки переносятся между проектами без переназначения.

Там же (ключ room_types) запоминается, какой тип точки доступа был
выбран для какого помещения в прошлый раз, и (room_number_param) —
параметр помещения с номером для таблицы помещений: там помещение
показывается как «Имя(номер)». Имя параметра — соглашение проекта, поэтому
вводится в окне, а не зашито; пусто — штатный «Номер» помещения.

Фильтр дверей: door_keywords_text — слова для имени помещения ЗА дверью
(оснащаются только двери, ведущие в коридор/МОП/паркинг/...; пусто — все
двери), include_outside — оснащать ли двери наружу (за дверью нет
помещения). door_overrides — ручная правка из таблицы помещений
({door_key: true/false}), имеет приоритет над фильтром. preview_markers —
id линий подсветки «Показать на плане» по документу, удаляются при
следующем запуске кнопки.
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
    StackPanel, TextBlock, TextBox, Button, ComboBox, CheckBox, Orientation, DockPanel, Dock,
    ScrollViewer, ScrollBarVisibility, Canvas, Grid, ColumnDefinition, Border
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


def _clean_access_types(raw):
    result = []
    seen = set()
    for item in raw or []:
        name = (item.get("name") or u"").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        composition = {}
        for key, entry in (item.get("composition") or {}).items():
            if entry and entry.get("family") and entry.get("type"):
                composition[key] = {"family": entry["family"], "type": entry["type"]}
        result.append({"name": name, "composition": composition})
    return result


def load_saved_values():
    """{"slots": {key: slot}, "access_types": [...], "room_types": {room_key: name},
    "room_number_param": имя параметра номера помещения}."""
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
        "access_types": _clean_access_types(saved.get("access_types")),
        "room_types": dict(saved.get("room_types") or {}),
        "room_number_param": saved.get("room_number_param") or u"",
        "door_keywords_text": (saved["door_keywords_text"] if "door_keywords_text" in saved
                               else layout.DEFAULT_DOOR_KEYWORDS),
        "include_outside": bool(saved.get("include_outside", True)),
        "door_overrides": dict(saved.get("door_overrides") or {}),
        "preview_markers": dict(saved.get("preview_markers") or {}),
    }


def save_layout(slots, access_types, room_number_param, door_keywords_text, include_outside):
    data = _read_all()
    data["room_number_param"] = room_number_param
    data["door_keywords_text"] = door_keywords_text
    data["include_outside"] = bool(include_outside)
    data["slots"] = slots
    data["access_types"] = access_types
    data.pop("room_groups", None)  # от первой версии кнопки (выбор модельных групп)
    _write_all(data)


def save_door_overrides(overrides):
    """overrides — {door_key: true/false/None}; None — убрать ручную правку."""
    data = _read_all()
    merged = dict(data.get("door_overrides") or {})
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = bool(value)
    data["door_overrides"] = merged
    _write_all(data)


def save_preview_markers(doc_key, marker_ids):
    data = _read_all()
    markers = dict(data.get("preview_markers") or {})
    if marker_ids:
        markers[doc_key] = list(marker_ids)
    else:
        markers.pop(doc_key, None)
    data["preview_markers"] = markers
    _write_all(data)


def save_room_types(room_types):
    data = _read_all()
    merged = dict(data.get("room_types") or {})
    merged.update(room_types)
    data["room_types"] = merged
    _write_all(data)


# ------------------------------------------------------------
# Семейства и типоразмеры проекта
# ------------------------------------------------------------

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


class SymbolOption(object):
    """Типоразмер для списка выбора: «Семейство : Тип»."""

    def __init__(self, family_name, type_name):
        self.family_name = family_name
        self.type_name = type_name
        self.name = u"{} : {}".format(family_name, type_name)

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


def list_family_type_names(doc, family_names):
    """[(имя семейства, имя типоразмера)] всех типоразмеров перечисленных семейств."""
    wanted = set(layout.normalize_family_name(n) for n in family_names)
    result = []
    for family in FilteredElementCollector(doc).OfClass(Family):
        family_name = safe_element_name(family)
        if layout.normalize_family_name(family_name) not in wanted:
            continue
        for symbol_id in family.GetFamilySymbolIds():
            symbol = doc.GetElement(symbol_id)
            type_name = safe_element_name(symbol) if symbol is not None else None
            if type_name:
                result.append((family_name, type_name))
    return sorted(result, key=lambda item: (item[0].lower(), item[1].lower()))


# ------------------------------------------------------------
# Мнемосхема
# ------------------------------------------------------------

def _brush(hex_color):
    return SolidColorBrush(ColorConverter.ConvertFromString(hex_color))


def _role_info(role_key):
    for key, label, short, color in layout.ROLES:
        if key == role_key:
            return label, short, color
    return role_key, role_key, "#555555"


def _add_marker(canvas, x, y, short, color, state, tooltip):
    """state: "used" — занято в выбранном типе, "allowed" — есть семейства, "off" — нет."""
    x = max(7.0, min(CANVAS_WIDTH - 7.0, x))
    y = max(7.0, min(FLOOR_Y - 2.0, y))

    marker = Ellipse()
    marker.Width = 14
    marker.Height = 14
    marker.StrokeThickness = 2
    if state == "used":
        marker.Fill = _brush(color)
        marker.Stroke = _brush(color)
    elif state == "allowed":
        marker.Fill = Brushes.White
        marker.Stroke = _brush(color)
    else:
        marker.Fill = Brushes.White
        marker.Stroke = Brushes.LightGray
    marker.ToolTip = tooltip
    Canvas.SetLeft(marker, x - 7)
    Canvas.SetTop(marker, y - 7)
    canvas.Children.Add(marker)

    text = TextBlock()
    text.Text = short
    text.FontSize = 10
    text.FontWeight = FontWeights.Bold
    text.Foreground = _brush(color) if state != "off" else Brushes.LightGray
    Canvas.SetLeft(text, x + 8 if x < CANVAS_WIDTH - 40 else x - 30)
    Canvas.SetTop(text, y - 7)
    canvas.Children.Add(text)


def _draw_door_view(canvas, side, slots, composition):
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
        entry = composition.get(key)
        if entry:
            state = "used"
            tooltip = u"{} — {} : {}".format(label, entry["family"], entry["type"])
        elif slot.get("families"):
            state = "allowed"
            tooltip = u"{} — в выбранном типе не используется ({})".format(
                label, u", ".join(slot["families"]))
        else:
            state = "off"
            tooltip = u"{} — семейства не выбраны".format(label)
        positions = layout.slot_local_positions(key, slot, PREVIEW_DOOR_WIDTH_MM, PREVIEW_DOOR_HEIGHT_MM)
        for u, z, _depth in positions:
            _add_marker(canvas, cx + u * PREVIEW_SCALE, FLOOR_Y - z * PREVIEW_SCALE,
                        short, color, state, tooltip)


def _families_text(names):
    return u", ".join(names) if names else u"— не выбрано"


def _type_text(entry):
    if not entry:
        return u"— не используется"
    return u"{} : {}".format(entry["family"], entry["type"])


# ------------------------------------------------------------
# Окно
# ------------------------------------------------------------

def show_settings_form(doc, values):
    """Модальное окно. Возвращает {"slots", "access_types"}, None (Отмена)
    или settings_transfer.RELOAD (после загрузки настроек из файла)."""
    result = {"values": None}
    slots = dict((key, dict(slot)) for key, slot in values["slots"].items())
    access_types = [{"name": t["name"], "composition": dict(t["composition"])}
                    for t in values["access_types"]]
    state = {"current": access_types[0]["name"] if access_types else None}
    canvases = {}
    type_cells = []  # (key, TextBlock) — колонка «Типоразмер»
    type_buttons = []

    def current_type():
        return layout.find_access_type(access_types, state["current"])

    def current_composition():
        access_type = current_type()
        return access_type["composition"] if access_type else {}

    win = Window()
    win.Title = u"Настройки: Точки доступа на двери"
    win.Width = 1400
    win.Height = 900
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    # --- шапка: типы точек доступа + мнемосхема (не прокручивается) ---

    header = StackPanel()
    header.Margin = Thickness(16, 12, 16, 4)
    DockPanel.SetDock(header, Dock.Top)

    title = TextBlock()
    title.Text = u"Мнемосхема двери и типы точек доступа"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    header.Children.Add(title)

    hint = TextBlock()
    hint.Text = (
        u"1) В таблице мест укажите, какие СЕМЕЙСТВА могут стоять на каждом месте и "
        u"где оно относительно двери. «Левый/правый край» — как видит дверь человек, "
        u"стоящий с этой стороны; расстояние — от края проёма в сторону стены. "
        u"Высота — от низа двери (для «над дверью» — от верха). «От стены» — отступ "
        u"от поверхности стены к наблюдателю. Кол-во 2 у замка/геркона — "
        u"двустворчатая дверь: второй ставится зеркально относительно оси двери.\n"
        u"2) Создайте типы точек доступа и для выбранного типа задайте в колонке "
        u"«Типоразмер» состав: какой типоразмер стоит на каком месте. Эти типы "
        u"выбираются для помещений при запуске кнопки."
    )
    hint.FontSize = 11
    hint.Foreground = Brushes.Gray
    hint.TextWrapping = TextWrapping.Wrap
    hint.Margin = Thickness(0, 2, 0, 8)
    header.Children.Add(hint)

    types_row = StackPanel()
    types_row.Orientation = Orientation.Horizontal
    types_row.Margin = Thickness(0, 0, 0, 8)

    types_label = TextBlock()
    types_label.Text = u"Тип точки доступа:"
    types_label.FontWeight = FontWeights.Bold
    types_label.VerticalAlignment = VerticalAlignment.Center
    types_label.Margin = Thickness(0, 0, 8, 0)
    types_row.Children.Add(types_label)

    types_combo = ComboBox()
    types_combo.Width = 280
    types_row.Children.Add(types_combo)

    def make_small_button(text):
        btn = Button()
        btn.Content = text
        btn.Padding = Thickness(8, 2, 8, 2)
        btn.Margin = Thickness(6, 0, 0, 0)
        types_row.Children.Add(btn)
        return btn

    new_btn = make_small_button(u"Новый…")
    copy_btn = make_small_button(u"Копировать…")
    rename_btn = make_small_button(u"Переименовать…")
    delete_btn = make_small_button(u"Удалить")
    header.Children.Add(types_row)

    number_row = StackPanel()
    number_row.Orientation = Orientation.Horizontal
    number_row.Margin = Thickness(0, 0, 0, 8)
    number_label = TextBlock()
    number_label.Text = u"Параметр номера помещения (для таблицы помещений, «Имя(номер)»):"
    number_label.VerticalAlignment = VerticalAlignment.Center
    number_label.Margin = Thickness(0, 0, 8, 0)
    number_row.Children.Add(number_label)
    number_box = TextBox()
    number_box.Width = 280
    number_box.Padding = Thickness(4, 2, 4, 2)
    number_box.Text = values.get("room_number_param") or u""
    number_box.ToolTip = u"Пусто — штатный параметр «Номер» помещения."
    number_row.Children.Add(number_box)
    header.Children.Add(number_row)

    filter_row = StackPanel()
    filter_row.Orientation = Orientation.Horizontal
    filter_row.Margin = Thickness(0, 0, 0, 8)
    filter_label = TextBlock()
    filter_label.Text = u"Оснащать двери, ведущие в помещения с именем, содержащим:"
    filter_label.VerticalAlignment = VerticalAlignment.Center
    filter_label.Margin = Thickness(0, 0, 8, 0)
    filter_row.Children.Add(filter_label)
    filter_box = TextBox()
    filter_box.Width = 420
    filter_box.Padding = Thickness(4, 2, 4, 2)
    filter_box.Text = values.get("door_keywords_text") or u""
    filter_box.ToolTip = (
        u"Через запятую, без учёта регистра, достаточно основы слова. Проверяется "
        u"имя помещения ЗА дверью (с другой стороны от выбранного помещения). "
        u"Пусто — оснащаются все двери помещения. Отдельные двери можно "
        u"включить/исключить вручную в таблице помещений."
    )
    filter_row.Children.Add(filter_box)
    outside_box = CheckBox()
    outside_box.Content = u"и двери наружу (за дверью нет помещения)"
    outside_box.IsChecked = bool(values.get("include_outside", True))
    outside_box.VerticalAlignment = VerticalAlignment.Center
    outside_box.Margin = Thickness(12, 0, 0, 0)
    filter_row.Children.Add(outside_box)
    header.Children.Add(filter_row)

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
    legend_note.Text = (
        u"Закрашен — место занято в выбранном типе,\n"
        u"контур — семейства есть, в типе не используется,\n"
        u"серый — семейства не выбраны."
    )
    legend_note.FontSize = 10
    legend_note.Foreground = Brushes.Gray
    legend_note.Margin = Thickness(0, 6, 0, 0)
    legend.Children.Add(legend_note)
    views_row.Children.Add(legend)
    header.Children.Add(views_row)

    def redraw():
        composition = current_composition()
        for side, canvas in canvases.items():
            _draw_door_view(canvas, side, slots, composition)

    def refresh_type_column():
        composition = current_composition()
        has_type = current_type() is not None
        for key, cell in type_cells:
            cell.Text = _type_text(composition.get(key)) if has_type else u"— сначала создайте тип"
        for btn in type_buttons:
            btn.IsEnabled = has_type
        rename_btn.IsEnabled = has_type
        copy_btn.IsEnabled = has_type
        delete_btn.IsEnabled = has_type
        redraw()

    def refresh_types_combo():
        types_combo.Items.Clear()
        for access_type in access_types:
            types_combo.Items.Add(access_type["name"])
        names = [t["name"] for t in access_types]
        types_combo.SelectedIndex = names.index(state["current"]) if state["current"] in names else -1
        refresh_type_column()

    def on_type_selected(sender, args):
        index = types_combo.SelectedIndex
        if 0 <= index < len(access_types):
            state["current"] = access_types[index]["name"]
        refresh_type_column()

    def ask_name(prompt, default=u""):
        name = forms.ask_for_string(default=default, prompt=prompt, title=u"Тип точки доступа")
        if name is None:
            return None
        name = name.strip()
        if not name:
            return None
        if layout.find_access_type(access_types, name) is not None:
            forms.alert(u"Тип «{}» уже есть.".format(name))
            return None
        return name

    def on_new(sender, args):
        name = ask_name(u"Имя нового типа точки доступа (например «ТД-1 вход по карте»):")
        if name is None:
            return
        access_types.append({"name": name, "composition": {}})
        state["current"] = name
        refresh_types_combo()

    def on_copy(sender, args):
        source = current_type()
        if source is None:
            return
        name = ask_name(u"Имя копии типа «{}»:".format(source["name"]), source["name"] + u" (копия)")
        if name is None:
            return
        access_types.append({"name": name, "composition": dict(source["composition"])})
        state["current"] = name
        refresh_types_combo()

    def on_rename(sender, args):
        access_type = current_type()
        if access_type is None:
            return
        name = ask_name(u"Новое имя типа «{}»:".format(access_type["name"]), access_type["name"])
        if name is None:
            return
        access_type["name"] = name
        state["current"] = name
        refresh_types_combo()

    def on_delete(sender, args):
        access_type = current_type()
        if access_type is None:
            return
        if not forms.alert(u"Удалить тип «{}»?".format(access_type["name"]), yes=True, no=True):
            return
        access_types.remove(access_type)
        state["current"] = access_types[0]["name"] if access_types else None
        refresh_types_combo()

    types_combo.SelectionChanged += on_type_selected
    new_btn.Click += on_new
    copy_btn.Click += on_copy
    rename_btn.Click += on_rename
    delete_btn.Click += on_delete

    # --- таблица мест (прокручивается) ---

    table = StackPanel()
    table.Margin = Thickness(16, 4, 16, 8)

    column_widths = [190, None, 80, 140, 60, 70, 70, 50, 250, 80]
    column_titles = [u"Место", u"Семейства (могут стоять)", u"", u"Привязка", u"Расст., мм",
                     u"Высота, мм", u"От стены, мм", u"Кол-во", u"Типоразмер в выбранном типе", u""]

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

    def make_buttons(pick_tooltip, clear_tooltip):
        cell = StackPanel()
        cell.Orientation = Orientation.Horizontal
        pick_btn = Button()
        pick_btn.Content = u"Выбрать…"
        pick_btn.ToolTip = pick_tooltip
        pick_btn.Padding = Thickness(4, 1, 4, 1)
        clear_btn = Button()
        clear_btn.Content = u"×"
        clear_btn.ToolTip = clear_tooltip
        clear_btn.Padding = Thickness(5, 1, 5, 1)
        clear_btn.Margin = Thickness(3, 0, 0, 0)
        cell.Children.Add(pick_btn)
        cell.Children.Add(clear_btn)
        return cell, pick_btn, clear_btn

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
            cell.TextWrapping = TextWrapping.Wrap
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

            fam_buttons, fam_pick, fam_clear = make_buttons(
                u"Выбрать семейства для этого места", u"Очистить список семейств")
            place(row, fam_buttons, 2)

            def on_pick_families(sender, args, key=key, label=label, side_label=side_label,
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

            def on_clear_families(sender, args, key=key, families_cell=families_cell):
                slots[key]["families"] = []
                families_cell.Text = _families_text([])
                redraw()

            fam_pick.Click += on_pick_families
            fam_clear.Click += on_clear_families

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

            if role_key in layout.COUNTABLE_ROLES:
                count_box = ComboBox()
                for n in range(1, layout.MAX_COUNT + 1):
                    count_box.Items.Add(u"{}".format(n))
                count_box.SelectedIndex = layout.slot_count(key, slot) - 1

                def on_count(sender, args, key=key, count_box=count_box):
                    if count_box.SelectedIndex >= 0:
                        slots[key]["count"] = u"{}".format(count_box.SelectedIndex + 1)
                        redraw()

                count_box.SelectionChanged += on_count
                place(row, count_box, 7)

            type_cell = TextBlock()
            type_cell.TextWrapping = TextWrapping.Wrap
            place(row, type_cell, 8)
            type_cells.append((key, type_cell))

            type_btns, type_pick, type_clear = make_buttons(
                u"Выбрать типоразмер для этого места в выбранном типе точки доступа",
                u"Не использовать это место в выбранном типе")
            place(row, type_btns, 9)
            type_buttons.extend([type_pick, type_clear])

            def on_pick_type(sender, args, key=key, label=label, side_label=side_label,
                             type_cell=type_cell):
                access_type = current_type()
                if access_type is None:
                    return
                families = slots[key]["families"]
                if not families:
                    forms.alert(u"Сначала выберите для этого места семейства (колонка «Семейства»).")
                    return
                options = [SymbolOption(f, t) for f, t in list_family_type_names(doc, families)]
                if not options:
                    forms.alert(u"У выбранных семейств этого места в проекте нет типоразмеров.")
                    return
                chosen = forms.SelectFromList.show(
                    options,
                    title=u"«{}»: {} — {}".format(access_type["name"], label, side_label.lower()),
                    button_name=u"Выбрать",
                    multiselect=False
                )
                if not chosen:
                    return
                access_type["composition"][key] = {"family": chosen.family_name, "type": chosen.type_name}
                type_cell.Text = _type_text(access_type["composition"][key])
                redraw()

            def on_clear_type(sender, args, key=key, type_cell=type_cell):
                access_type = current_type()
                if access_type is None:
                    return
                access_type["composition"].pop(key, None)
                type_cell.Text = _type_text(None)
                redraw()

            type_pick.Click += on_pick_type
            type_clear.Click += on_clear_type

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
        result["values"] = {"slots": slots, "access_types": access_types,
                            "room_number_param": (number_box.Text or u"").strip(),
                            "door_keywords_text": filter_box.Text or u"",
                            "include_outside": bool(outside_box.IsChecked)}
        win.Close()

    def on_cancel(sender, args):
        win.Close()

    ok_btn.Click += on_ok
    cancel_btn.Click += on_cancel

    buttons.Children.Add(cancel_btn)
    buttons.Children.Add(ok_btn)

    def _on_settings_imported():
        result["values"] = settings_transfer.RELOAD
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

    refresh_types_combo()

    win.Content = outer
    win.ShowDialog()

    return result["values"]


def get_settings_interactive(doc):
    """Окно (Shift+клик). Возвращает сохранённые значения или None (Отмена)."""
    while True:
        saved = load_saved_values()
        edited = show_settings_form(doc, saved)

        if edited == settings_transfer.RELOAD:
            continue

        if edited is None:
            return None

        save_layout(edited["slots"], edited["access_types"], edited["room_number_param"],
                    edited["door_keywords_text"], edited["include_outside"])
        return edited


def get_settings_silent():
    """Сохранённые места, типы точек доступа и выбор по помещениям — без окна."""
    return load_saved_values()


def require_access_types(values):
    """Типы точек доступа с непустым составом; если ни одного — стоп с подсказкой."""
    usable = []
    for access_type in values["access_types"]:
        items, _stale = layout.composition_items(access_type, values["slots"])
        if items:
            usable.append(access_type)
    if not usable:
        forms.alert(
            u"Не настроено ни одного типа точки доступа с составом.\n\n"
            u"Откройте настройки: Shift+клик по кнопке «Точки доступа на двери», "
            u"выберите семейства для мест мнемосхемы, создайте тип точки доступа "
            u"(«Новый…») и задайте ему типоразмеры в колонке «Типоразмер».",
            exitscript=True
        )
    return usable
