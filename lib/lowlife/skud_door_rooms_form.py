# -*- coding: utf-8 -*-
"""
Таблица «помещение -> тип точки доступа» для кнопки «Точки доступа на
двери» (SKUD.panel/PlaceDoorAccessPoints).

Строка на каждое помещение активного вида: «Имя(номер)» (номер — из
параметра, заданного в настройках кнопки), уровень, двери и выпадающий
список типов точек доступа (из настроек кнопки, Shift+клик). Сверху —
поиск по имени/номеру и «Назначить тип всем показанным» (удобно
отфильтровать, например, «серверная», и назначить разом). Помещения без
дверей показаны серыми, тип им выбрать нельзя.

Колонка «Двери» — кнопка «оснащается / всего»: по клику открывается
список дверей помещения («Марка · Семейство : Тип → Коридор(1.01)») с
галочками. Галочки заранее проставлены фильтром по помещению за дверью
(настройки кнопки); снятая/поставленная вручную галочка запоминается для
этой двери и имеет приоритет над фильтром («Сбросить к фильтру» убирает
ручную правку дверей помещения).

Внизу — «Показать на плане»: окно закрывается с action="preview", и
кнопка обводит на активном виде двери выбранных помещений (зелёный —
будет оснащена, красный — исключена), ничего не расставляя.

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
    StackPanel, TextBlock, TextBox, Button, ComboBox, CheckBox, Orientation, DockPanel, Dock,
    ScrollViewer, ScrollBarVisibility, Grid, ColumnDefinition
)
from System.Windows.Media import Brushes

NO_TYPE = u"— не расставлять —"

_COLUMNS = [(u"Имя", None), (u"Уровень", 140), (u"Двери (оснащается / всего)", 150),
            (u"Тип точки доступа", 260)]


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


def _button(text, bold=False):
    btn = Button()
    btn.Content = text
    btn.Padding = Thickness(10, 4, 10, 4)
    btn.Margin = Thickness(0, 0, 8, 0)
    if bold:
        btn.FontWeight = FontWeights.Bold
    return btn


def _show_doors_dialog(room_title, doors, number_param, auto_of, state):
    """
    Список дверей помещения с галочками. auto_of(entry) — решение фильтра,
    state — {door_key: bool|None} ручных правок (меняется на месте, только
    по «ОК»). Возвращает True, если нажали «ОК».
    """
    result = {"ok": False}

    win = Window()
    win.Title = u"Двери помещения: {}".format(room_title)
    win.Width = 720
    win.Height = 420
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    hint = TextBlock()
    hint.Text = (
        u"Отмечены двери, которые будут оснащены. Изначально галочки ставит фильтр "
        u"по помещению за дверью (настройки кнопки); изменённая вручную галочка "
        u"запоминается для этой двери. Серым — решение фильтра."
    )
    hint.TextWrapping = TextWrapping.Wrap
    hint.FontSize = 11
    hint.Foreground = Brushes.Gray
    hint.Margin = Thickness(12, 10, 12, 8)
    DockPanel.SetDock(hint, Dock.Top)
    outer.Children.Add(hint)

    rows = []
    body = StackPanel()
    body.Margin = Thickness(12, 0, 12, 8)
    for entry in doors:
        auto = auto_of(entry)
        manual = state.get(entry.unique_key)
        row = StackPanel()
        row.Orientation = Orientation.Horizontal
        row.Margin = Thickness(0, 2, 0, 2)
        box = CheckBox()
        box.Content = entry.label(number_param)
        box.IsChecked = auto if manual is None else bool(manual)
        row.Children.Add(box)
        note = TextBlock()
        note.Text = u"   фильтр: {}".format(u"да" if auto else u"нет")
        note.Foreground = Brushes.Gray
        note.FontSize = 11
        note.VerticalAlignment = VerticalAlignment.Center
        row.Children.Add(note)
        body.Children.Add(row)
        rows.append((entry, box, auto))

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(12, 8, 4, 12)
    DockPanel.SetDock(buttons, Dock.Bottom)

    reset_btn = _button(u"Сбросить к фильтру")
    cancel_btn = _button(u"Отмена")
    ok_btn = _button(u"ОК", bold=True)

    def on_reset(sender, args):
        for _entry, box, auto in rows:
            box.IsChecked = auto

    def on_ok(sender, args):
        for entry, box, auto in rows:
            checked = bool(box.IsChecked)
            state[entry.unique_key] = None if checked == auto else checked
        result["ok"] = True
        win.Close()

    def on_cancel(sender, args):
        win.Close()

    reset_btn.Click += on_reset
    ok_btn.Click += on_ok
    cancel_btn.Click += on_cancel
    buttons.Children.Add(reset_btn)
    buttons.Children.Add(cancel_btn)
    buttons.Children.Add(ok_btn)
    outer.Children.Add(buttons)

    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scroll.Content = body
    outer.Children.Add(scroll)

    win.Content = outer
    win.ShowDialog()
    return result["ok"]


def show_rooms_table(rooms, type_names, saved_choice, room_number_param, auto_of, overrides):
    """
    rooms — список RoomEntry (skud_door_placement), type_names — имена
    типов точек доступа, saved_choice — {room.key: type_name} с прошлого
    раза, room_number_param — параметр номера для «Имя(номер)»,
    auto_of(door_entry) — решение фильтра дверей, overrides — сохранённые
    ручные правки {door_key: bool}.

    Возвращает None (окно закрыто без действия) либо dict:
        action    — "place" («Расставить») или "preview" («Показать на плане»);
        choice    — {room.key: type_name} (только помещения с выбранным типом);
        overrides — {door_key: bool|None} ручные правки дверей всех
                    помещений таблицы (None — правки нет, решает фильтр).
    """
    result = {"value": None}
    choices = [NO_TYPE] + list(type_names)
    rows = []  # (room, row_grid, combo, search_text)
    state = {}
    for room in rooms:
        for entry in room.doors:
            value = overrides.get(entry.unique_key)
            state[entry.unique_key] = None if value is None else bool(value)

    def included(entry):
        manual = state.get(entry.unique_key)
        return auto_of(entry) if manual is None else manual

    def doors_text(room):
        return u"{} / {}".format(sum(1 for e in room.doors if included(e)), len(room.doors))

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
        u"расставляется на оснащаемые двери помещения по мнемосхеме. Какие двери "
        u"оснащаются — решает фильтр по помещению за дверью (настройки кнопки), "
        u"поправить можно по клику на «Двери». «Показать на плане» — обвести "
        u"двери выбранных помещений на активном виде, ничего не расставляя. "
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
        cell.TextWrapping = TextWrapping.Wrap
        _place(head, cell, index)
    header.Children.Add(head)

    body = StackPanel()
    body.Margin = Thickness(16, 0, 16, 8)

    for room in rooms:
        row = _make_grid()
        door_count = len(room.doors)
        display = room.display_name(room_number_param)
        for index, text in enumerate([display, room.level_name]):
            cell = TextBlock()
            cell.Text = text or u""
            cell.TextWrapping = TextWrapping.Wrap
            if not door_count:
                cell.Foreground = Brushes.Gray
            _place(row, cell, index)

        doors_btn = Button()
        doors_btn.Content = doors_text(room)
        doors_btn.Padding = Thickness(6, 1, 6, 1)
        doors_btn.HorizontalAlignment = HorizontalAlignment.Left
        doors_btn.IsEnabled = door_count > 0
        doors_btn.ToolTip = u"Список дверей помещения — какие оснащать"

        def on_doors(sender, args, room=room, display=display, doors_btn=doors_btn):
            if _show_doors_dialog(display, room.doors, room_number_param, auto_of, state):
                doors_btn.Content = doors_text(room)

        doors_btn.Click += on_doors
        _place(row, doors_btn, 2)

        combo = ComboBox()
        for name in choices:
            combo.Items.Add(name)
        saved = saved_choice.get(room.key)
        combo.SelectedIndex = choices.index(saved) if saved in choices else 0
        combo.IsEnabled = door_count > 0
        _place(row, combo, 3)

        body.Children.Add(row)
        rows.append((room, row, combo, display.lower()))

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
    buttons.Margin = Thickness(16, 8, 8, 12)
    DockPanel.SetDock(buttons, Dock.Bottom)

    preview_btn = _button(u"Показать на плане")
    preview_btn.ToolTip = (
        u"Обвести на активном виде двери помещений с выбранным типом: зелёный — "
        u"будет оснащена, красный — исключена. Ничего не расставляется; выбор "
        u"сохраняется, подсветка убирается при следующем запуске кнопки."
    )
    cancel_btn = _button(u"Отмена")
    ok_btn = _button(u"Расставить", bold=True)

    def finish(action):
        choice = {}
        for room, _row, combo, _text in rows:
            index = combo.SelectedIndex
            if index > 0 and combo.IsEnabled:
                choice[room.key] = choices[index]
        result["value"] = {"action": action, "choice": choice, "overrides": dict(state)}
        win.Close()

    def on_preview(sender, args):
        finish("preview")

    def on_ok(sender, args):
        finish("place")

    def on_cancel(sender, args):
        win.Close()

    preview_btn.Click += on_preview
    ok_btn.Click += on_ok
    cancel_btn.Click += on_cancel
    buttons.Children.Add(preview_btn)
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

    return result["value"]
