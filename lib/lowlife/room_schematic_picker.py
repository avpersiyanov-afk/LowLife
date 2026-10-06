# -*- coding: utf-8 -*-
"""
Окно кнопки Schematic.panel/BuildRoomSchematic («Рыба структурной схемы»).

Одно окно на весь сценарий (раньше были цепочки SelectFromList: четыре
параметра, затем по 3-4 диалога на каждый этаж — пользователь жаловался,
что это слишком сложно):

  - слева — список этажей (порядок и подписи — sot_levels, как у
    СОТ/СПС/СКС), у каждого — сколько боксов на нём уже будет;
  - справа — таблица помещений выбранного этажа: «Номер», «Имя» и
    редактируемый столбец «На схеме» — как помещение показать на схеме.
    Пусто — помещения на схеме нет. Одинаковая подпись у нескольких
    помещений этажа — они сливаются в один бокс (так делаются группы);
  - под таблицей — массовые действия над выделенными строками (задать
    подпись, подставить имя помещения, убрать со схемы) и копирование
    подписей с другого этажа по именам помещений;
  - типовые этажи: при открытии этажа без подписей, у которого тот же
    набор помещений, что у уже заполненного этажа, подписи подставляются
    сразу (room_schematic_core.find_typical_source/copy_labels_by_name), о
    чём говорит строка над таблицей.

Подписи запоминаются между запусками (по UniqueId помещения, на каждый
файл модели свои) в %APPDATA%\\pyRevit\\LowLifeRoomSchematic_settings.json,
вместе с именем вида — повторный запуск открывает окно уже заполненным.

Помещения — из room_finder.get_records(doc) (хост + все связи).
Логика без WPF/Revit — room_schematic_core.py.
"""

from collections import OrderedDict

import clr
clr.AddReference('System')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System.Collections.Generic import List
from System.Windows import (
    Window, WindowStartupLocation, Thickness, FontWeights, GridLength,
    GridUnitType, VerticalAlignment, TextWrapping,
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, ComboBox, ListBox, ListBoxItem,
    Orientation, DockPanel, Dock, WrapPanel, Grid, ColumnDefinition,
    DataGrid, DataGridTextColumn, DataGridLength, DataGridLengthUnitType,
    DataGridHeadersVisibility, DataGridGridLinesVisibility,
    DataGridSelectionMode, DataGridEditingUnit,
)
from System.Windows.Data import Binding, BindingMode, UpdateSourceTrigger
from System.Windows.Input import Key

from pyrevit import forms

from lowlife import room_schematic_core as core
from lowlife.room_finder import natural_key
from lowlife.room_schematic import SCHEMATIC_VIEW_NAME
from lowlife.settings_core import JsonStore
from lowlife.sot_levels import sorted_level_names, get_level_label

TITLE = u"Рыба структурной схемы"

_store = JsonStore("LowLifeRoomSchematic_settings.json", label=u"рыбы структурной схемы")


# --- запоминание подписей между запусками --------------------------------------

def _doc_key(doc):
    try:
        path = doc.PathName
    except Exception:
        path = None
    if path:
        return path
    try:
        return doc.Title
    except Exception:
        return u""


def _room_key(record):
    try:
        return record.room.UniqueId
    except Exception:
        return None


def _load_saved(doc):
    entry = _store.read().get(_doc_key(doc))
    return entry if isinstance(entry, dict) else {}


def _save(doc, view_name, rows_by_level):
    labels = {}
    for rows in rows_by_level.values():
        for row in rows:
            label = (row.label or u"").strip()
            if label and row.key:
                labels[row.key] = label
    _store.update({_doc_key(doc): {"view_name": view_name, "labels": labels}})


# --- строки таблицы ---------------------------------------------------------------

class _RoomRow(object):
    """Строка таблицы; атрибуты name/number/label/room_id — то, что ждёт
    room_schematic_core, они же — пути привязки столбцов DataGrid."""

    def __init__(self, record, label):
        self.number = record.number or u""
        self.name = record.name or u""
        self.label = label or u""
        self.room_id = record.room_id
        self.key = _room_key(record)


def _rows_by_level(records, saved_labels):
    """(level_order, OrderedDict(level_name -> [_RoomRow, ...])) — строки
    этажа отсортированы по номеру помещения."""
    level_groups = OrderedDict()
    for index, record in enumerate(records):
        name = record.level_name or u"Без уровня"
        if name not in level_groups:
            try:
                level = record.room.Level
            except Exception:
                level = None
            level_groups[name] = {"elements": [], "level": level, "order": index}
        level_groups[name]["elements"].append(record)

    level_order = sorted_level_names(level_groups)
    rows_by_level = OrderedDict()
    for level_name in level_order:
        level_records = sorted(
            level_groups[level_name]["elements"],
            key=lambda r: (natural_key(r.number), natural_key(r.name)),
        )
        rows_by_level[level_name] = [
            _RoomRow(r, saved_labels.get(_room_key(r))) for r in level_records
        ]
    return level_order, rows_by_level


# --- окно ---------------------------------------------------------------------------

def _star(n):
    return DataGridLength(n, DataGridLengthUnitType.Star)


def _button(text, bold=False):
    btn = Button()
    btn.Content = text
    btn.Padding = Thickness(10, 3, 10, 3)
    btn.Margin = Thickness(0, 0, 6, 4)
    if bold:
        btn.FontWeight = FontWeights.Bold
    return btn


def _label(text):
    tb = TextBlock()
    tb.Text = text
    tb.VerticalAlignment = VerticalAlignment.Center
    tb.Margin = Thickness(0, 0, 6, 4)
    return tb


def _floor_caption(level_name, rows):
    boxes = len(core.boxes_for_floor(rows))
    text = u"{}  ·  пом.: {}".format(get_level_label(level_name), len(rows))
    if boxes:
        text += u"  ·  боксов: {}".format(boxes)
    return text


def show(doc, records):
    """
    Показывает окно. Возвращает (view_name, OrderedDict(level_name ->
    [box, ...])) для room_schematic.rebuild, либо None, если окно закрыто
    без построения.
    """
    if not records:
        return None

    saved = _load_saved(doc)
    saved_labels = saved.get("labels") or {}
    level_order, rows_by_level = _rows_by_level(records, saved_labels)
    if not level_order:
        return None

    state = {"level": None, "auto_filled": set(), "result": None}

    win = Window()
    win.Title = TITLE
    win.Width = 1050
    win.Height = 720
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    # --- шапка ---
    header = TextBlock()
    header.Text = (
        u"Выберите этаж слева и в столбце «На схеме» напишите, как показать "
        u"помещение на схеме. Пусто — помещения на схеме не будет. Одинаковая "
        u"подпись у нескольких помещений этажа — один общий бокс (группа). "
        u"Можно выделить несколько строк (Shift/Ctrl) и задать им подпись "
        u"разом. Этаж с тем же набором помещений, что у уже заполненного "
        u"(типовой), заполнится сам."
    )
    header.TextWrapping = TextWrapping.Wrap
    header.Margin = Thickness(12, 10, 12, 8)
    DockPanel.SetDock(header, Dock.Top)

    # --- низ: имя вида + кнопки ---
    bottom = DockPanel()
    bottom.Margin = Thickness(12, 8, 12, 12)
    DockPanel.SetDock(bottom, Dock.Bottom)

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    DockPanel.SetDock(buttons, Dock.Right)
    cancel_btn = _button(u"Отмена")
    build_btn = _button(u"Построить схему", bold=True)
    buttons.Children.Add(cancel_btn)
    buttons.Children.Add(build_btn)

    view_row = StackPanel()
    view_row.Orientation = Orientation.Horizontal
    view_row.Children.Add(_label(u"Имя чертёжного вида:"))
    view_box = TextBox()
    view_box.Width = 360
    view_box.Margin = Thickness(0, 0, 6, 4)
    view_box.Text = saved.get("view_name") or SCHEMATIC_VIEW_NAME
    view_row.Children.Add(view_box)

    bottom.Children.Add(buttons)
    bottom.Children.Add(view_row)

    # --- середина: этажи | таблица ---
    body = Grid()
    body.Margin = Thickness(12, 0, 12, 0)
    left_col = ColumnDefinition()
    left_col.Width = GridLength(280)
    right_col = ColumnDefinition()
    right_col.Width = GridLength(1, GridUnitType.Star)
    body.ColumnDefinitions.Add(left_col)
    body.ColumnDefinitions.Add(right_col)

    floors = ListBox()
    floors.Margin = Thickness(0, 0, 10, 0)
    floor_items = []
    for level_name in level_order:
        item = ListBoxItem()
        item.Content = _floor_caption(level_name, rows_by_level[level_name])
        floors.Items.Add(item)
        floor_items.append(item)
    Grid.SetColumn(floors, 0)
    body.Children.Add(floors)

    right = DockPanel()
    right.LastChildFill = True
    Grid.SetColumn(right, 1)
    body.Children.Add(right)

    banner = TextBlock()
    banner.TextWrapping = TextWrapping.Wrap
    banner.FontWeight = FontWeights.Bold
    banner.Margin = Thickness(0, 0, 0, 6)
    DockPanel.SetDock(banner, Dock.Top)
    right.Children.Add(banner)

    tools = WrapPanel()
    tools.Margin = Thickness(0, 6, 0, 0)
    DockPanel.SetDock(tools, Dock.Bottom)
    tools.Children.Add(_label(u"Выделенным:"))
    label_box = TextBox()
    label_box.Width = 180
    label_box.Margin = Thickness(0, 0, 6, 4)
    tools.Children.Add(label_box)
    set_btn = _button(u"Задать подпись")
    name_btn = _button(u"Подпись = имя помещения")
    clear_btn = _button(u"Убрать со схемы")
    tools.Children.Add(set_btn)
    tools.Children.Add(name_btn)
    tools.Children.Add(clear_btn)
    tools.Children.Add(_label(u"   Как на этаже:"))
    copy_combo = ComboBox()
    copy_combo.Width = 200
    copy_combo.Margin = Thickness(0, 0, 6, 4)
    for level_name in level_order:
        copy_combo.Items.Add(get_level_label(level_name))
    tools.Children.Add(copy_combo)
    copy_btn = _button(u"Скопировать")
    tools.Children.Add(copy_btn)
    right.Children.Add(tools)

    grid = DataGrid()
    grid.AutoGenerateColumns = False
    grid.CanUserAddRows = False
    grid.CanUserDeleteRows = False
    grid.CanUserResizeRows = False
    grid.HeadersVisibility = DataGridHeadersVisibility.Column
    grid.GridLinesVisibility = DataGridGridLinesVisibility.Horizontal
    grid.SelectionMode = DataGridSelectionMode.Extended

    number_col = DataGridTextColumn()
    number_col.Header = u"Номер"
    number_col.Binding = Binding("number")
    number_col.IsReadOnly = True
    number_col.Width = DataGridLength(90)
    grid.Columns.Add(number_col)

    name_col = DataGridTextColumn()
    name_col.Header = u"Имя"
    name_col.Binding = Binding("name")
    name_col.IsReadOnly = True
    name_col.Width = _star(1)
    grid.Columns.Add(name_col)

    label_binding = Binding("label")
    label_binding.Mode = BindingMode.TwoWay
    label_binding.UpdateSourceTrigger = UpdateSourceTrigger.PropertyChanged
    label_col = DataGridTextColumn()
    label_col.Header = u"На схеме"
    label_col.Binding = label_binding
    label_col.Width = _star(1)
    grid.Columns.Add(label_col)

    right.Children.Add(grid)

    # --- поведение ---

    def commit():
        try:
            grid.CommitEdit(DataGridEditingUnit.Row, True)
        except Exception:
            pass

    def current_rows():
        return rows_by_level.get(state["level"]) or []

    def refresh():
        """Перерисовать таблицу и подпись этажа после правок из кода
        (строки — обычные python-объекты без INotifyPropertyChanged)."""
        commit()
        try:
            grid.Items.Refresh()
        except Exception:
            pass
        level_name = state["level"]
        if level_name is not None:
            index = level_order.index(level_name)
            floor_items[index].Content = _floor_caption(level_name, current_rows())

    def selected_rows():
        rows = [row for row in grid.SelectedItems]
        if not rows:
            forms.alert(u"Выделите строки в таблице (Shift/Ctrl — несколько).", title=TITLE)
        return rows

    def open_level(level_name):
        commit()
        if state["level"] is not None:
            refresh()
        state["level"] = level_name
        rows = rows_by_level[level_name]
        banner.Text = u""

        if (not core.has_labels(rows)) and level_name not in state["auto_filled"]:
            source = core.find_typical_source(level_order, rows_by_level, level_name)
            if source is not None:
                core.copy_labels_by_name(rows_by_level[source], rows)
                state["auto_filled"].add(level_name)
                banner.Text = (
                    u"Типовой этаж: подписи взяты с «{}» (тот же набор помещений). "
                    u"Проверьте и при необходимости поправьте."
                ).format(get_level_label(source))

        data = List[object]()
        for row in rows:
            data.Add(row)
        grid.ItemsSource = data
        refresh()

    def on_floor_changed(sender, args):
        index = floors.SelectedIndex
        if 0 <= index < len(level_order):
            open_level(level_order[index])

    def on_set(sender, args):
        text = (label_box.Text or u"").strip()
        if not text:
            forms.alert(u"Впишите подпись в поле слева от кнопки.", title=TITLE)
            return
        commit()
        for row in selected_rows():
            row.label = text
        refresh()

    def on_name(sender, args):
        commit()
        for row in selected_rows():
            row.label = row.name
        refresh()

    def on_clear(sender, args):
        commit()
        for row in selected_rows():
            row.label = u""
        refresh()

    def on_label_key(sender, args):
        if args.Key == Key.Enter:
            on_set(sender, args)

    def on_copy(sender, args):
        index = copy_combo.SelectedIndex
        if not (0 <= index < len(level_order)):
            forms.alert(u"Выберите этаж-образец в списке.", title=TITLE)
            return
        source = level_order[index]
        if source == state["level"]:
            return
        commit()
        copied = core.copy_labels_by_name(rows_by_level[source], current_rows())
        banner.Text = u"С «{}» перенесено подписей (по именам помещений): {}.".format(
            get_level_label(source), copied)
        refresh()

    def on_cancel(sender, args):
        win.Close()

    def on_build(sender, args):
        commit()
        refresh()
        boxes = core.build_boxes(level_order, rows_by_level)
        if not boxes:
            forms.alert(u"Ни у одного помещения нет подписи «На схеме» — строить нечего.", title=TITLE)
            return
        state["result"] = (view_name_text(), boxes)
        win.Close()

    def view_name_text():
        return (view_box.Text or u"").strip() or SCHEMATIC_VIEW_NAME

    def on_closing(sender, args):
        # Подписи сохраняются и при «Отмене»/крестике — чтобы не потерять
        # заполненное, если окно закрыли, не построив схему.
        commit()
        _save(doc, view_name_text(), rows_by_level)

    floors.SelectionChanged += on_floor_changed
    set_btn.Click += on_set
    name_btn.Click += on_name
    clear_btn.Click += on_clear
    label_box.KeyDown += on_label_key
    copy_btn.Click += on_copy
    cancel_btn.Click += on_cancel
    build_btn.Click += on_build
    win.Closing += on_closing

    outer.Children.Add(header)
    outer.Children.Add(bottom)
    outer.Children.Add(body)
    win.Content = outer

    floors.SelectedIndex = 0
    win.ShowDialog()

    return state["result"]
