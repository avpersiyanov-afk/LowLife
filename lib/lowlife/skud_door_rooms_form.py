# -*- coding: utf-8 -*-
"""
Таблица «помещение -> тип точки доступа» для кнопки «Точки доступа на
двери» (SKUD.panel/PlaceDoorAccessPoints).

Строка на каждое помещение активного вида: номер, имя, уровень, источник
(текущая модель или имя связи), число дверей и выпадающий список типов
точек доступа (из настроек кнопки, Shift+клик). Сверху — поиск по
номеру/имени и «Назначить тип всем показанным»
(удобно отфильтровать, например, «серверная», и назначить разом).
Помещения без дверей показаны серыми, тип им выбрать нельзя.

Показ — своё окно WPF (а не forms.SelectFromList): нужна именно таблица с
выбором значения в каждой строке.
"""

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from System.Windows import (
    Window, WindowStartupLocation, Thickness, FontWeights, HorizontalAlignment,
    VerticalAlignment, TextWrapping, GridLength, GridUnitType, Visibility
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, ComboBox, Orientation, DockPanel, Dock,
    ScrollViewer, ScrollBarVisibility, Grid, ColumnDefinition
)
from System.Windows.Media import Brushes

NO_TYPE = u"— не расставлять —"

_COLUMNS = [(u"Номер", 80), (u"Имя", None), (u"Уровень", 120), (u"Источник", 170),
            (u"Дверей", 60), (u"Тип точки доступа", 260)]


def _make_grid():
    grid = Grid()
    for _title, width in _COLUMNS:
        column = ColumnDefinition()
        column.Width = GridLength(1, GridUnitType.Star) if width is None else GridLength(width)
        grid.ColumnDefinitions.Add(column)
    return grid


def _place(grid, element, column):
    Grid.SetColumn(element, column)
    element.Margin = Thickness(2, 2, 6, 2)
    element.VerticalAlignment = VerticalAlignment.Center
    grid.Children.Add(element)


def show_rooms_table(rooms, type_names, saved_choice):
    """
    rooms — список RoomEntry (skud_door_placement), type_names — имена
    типов точек доступа, saved_choice — {room.key: type_name} с прошлого
    раза. Возвращает {room.key: type_name} (только помещения с выбранным
    типом) либо None, если окно закрыли без «Расставить».
    """
    result = {"choice": None}
    choices = [NO_TYPE] + list(type_names)
    rows = []  # (room, row_grid, combo, search_text)

    win = Window()
    win.Title = u"Точки доступа на двери — выбор типов по помещениям"
    win.Width = 1000
    win.Height = 700
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    header = StackPanel()
    header.Margin = Thickness(16, 12, 16, 6)
    DockPanel.SetDock(header, Dock.Top)

    title = TextBlock()
    title.Text = u"Помещения активного вида"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    header.Children.Add(title)

    hint = TextBlock()
    hint.Text = (
        u"Для каждого помещения выберите тип точки доступа — его состав "
        u"расставляется на каждую дверь помещения по мнемосхеме. Типы и их "
        u"состав настраиваются по Shift+клику на кнопке. "
        u"«Внутри» — сторона двери, обращённая в это помещение."
    )
    hint.FontSize = 11
    hint.Foreground = Brushes.Gray
    hint.TextWrapping = TextWrapping.Wrap
    hint.Margin = Thickness(0, 2, 0, 8)
    header.Children.Add(hint)

    tools = StackPanel()
    tools.Orientation = Orientation.Horizontal
    tools.Margin = Thickness(0, 0, 0, 8)

    search_label = TextBlock()
    search_label.Text = u"Поиск:"
    search_label.VerticalAlignment = VerticalAlignment.Center
    search_label.Margin = Thickness(0, 0, 6, 0)
    tools.Children.Add(search_label)

    search_box = TextBox()
    search_box.Width = 220
    search_box.Padding = Thickness(4, 2, 4, 2)
    tools.Children.Add(search_box)

    bulk_label = TextBlock()
    bulk_label.Text = u"Всем показанным:"
    bulk_label.VerticalAlignment = VerticalAlignment.Center
    bulk_label.Margin = Thickness(24, 0, 6, 0)
    tools.Children.Add(bulk_label)

    bulk_combo = ComboBox()
    bulk_combo.Width = 240
    for name in choices:
        bulk_combo.Items.Add(name)
    bulk_combo.SelectedIndex = 0
    tools.Children.Add(bulk_combo)

    bulk_btn = Button()
    bulk_btn.Content = u"Назначить"
    bulk_btn.Padding = Thickness(8, 2, 8, 2)
    bulk_btn.Margin = Thickness(6, 0, 0, 0)
    tools.Children.Add(bulk_btn)

    header.Children.Add(tools)

    head = _make_grid()
    for index, (column_title, _width) in enumerate(_COLUMNS):
        cell = TextBlock()
        cell.Text = column_title
        cell.FontWeight = FontWeights.Bold
        _place(head, cell, index)
    header.Children.Add(head)

    body = StackPanel()
    body.Margin = Thickness(16, 0, 16, 8)

    for room in rooms:
        row = _make_grid()
        door_count = len(room.doors)
        values = [room.number, room.name, room.level_name,
                  room.source.label or u"текущая модель", u"{}".format(door_count)]
        for index, text in enumerate(values):
            cell = TextBlock()
            cell.Text = text or u""
            cell.TextWrapping = TextWrapping.Wrap
            if not door_count:
                cell.Foreground = Brushes.Gray
            _place(row, cell, index)

        combo = ComboBox()
        for name in choices:
            combo.Items.Add(name)
        saved = saved_choice.get(room.key)
        combo.SelectedIndex = choices.index(saved) if saved in choices else 0
        combo.IsEnabled = door_count > 0
        _place(row, combo, 5)

        body.Children.Add(row)
        rows.append((room, row, combo, u"{} {}".format(room.number, room.name).lower()))

    if not rooms:
        empty = TextBlock()
        empty.Text = u"На активном виде нет помещений."
        empty.Foreground = Brushes.Gray
        body.Children.Add(empty)

    def on_search(sender, args):
        needle = (search_box.Text or u"").strip().lower()
        for _room, row, _combo, text in rows:
            row.Visibility = Visibility.Visible if (not needle or needle in text) else Visibility.Collapsed

    def on_bulk(sender, args):
        index = bulk_combo.SelectedIndex
        if index < 0:
            return
        for _room, row, combo, _text in rows:
            if row.Visibility == Visibility.Visible and combo.IsEnabled:
                combo.SelectedIndex = index

    search_box.TextChanged += on_search
    bulk_btn.Click += on_bulk

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
    ok_btn.Content = u"Расставить"
    ok_btn.Padding = Thickness(10, 4, 10, 4)
    ok_btn.FontWeight = FontWeights.Bold

    def on_ok(sender, args):
        choice = {}
        for room, _row, combo, _text in rows:
            index = combo.SelectedIndex
            if index > 0 and combo.IsEnabled:
                choice[room.key] = choices[index]
        result["choice"] = choice
        win.Close()

    def on_cancel(sender, args):
        win.Close()

    ok_btn.Click += on_ok
    cancel_btn.Click += on_cancel
    buttons.Children.Add(cancel_btn)
    buttons.Children.Add(ok_btn)

    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scroll.Content = body

    outer.Children.Add(header)
    outer.Children.Add(buttons)
    outer.Children.Add(scroll)

    win.Content = outer
    win.ShowDialog()

    return result["choice"]
