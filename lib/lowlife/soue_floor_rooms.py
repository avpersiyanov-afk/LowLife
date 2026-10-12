# -*- coding: utf-8 -*-
"""
Таблица помещений объекта для «СОУЭ - расстановка типовой этаж»: уникальные
имена помещений всех связей (и модели) → категория из справочника расчёта,
уровень шума N, «исключить». Окно редактирования (show_table_window) с
поиском, выгрузкой в Excel и загрузкой обратно (lowlife.xlsx_io).

Хранится в настройках кнопки (soue_floor_settings.ROOM_TABLE_KEY); чистая
логика таблицы — soue_floor_core (RoomRow, merge_room_table,
table_to_sheet/table_from_sheet).
"""

from lowlife import soue_floor_core as core
from lowlife import soue_floor_settings as cfg

TITLE = cfg.BUTTON_NAME


def room_name_counts(doc):
    """{имя помещения: число помещений} по всем связям и модели."""
    from lowlife import soue_floor
    counts = {}
    for source in soue_floor.room_sources(doc):
        for room in source.rooms():
            name = soue_floor.room_name(room)
            if name:
                counts[name] = counts.get(name, 0) + 1
    return counts


def export_rows(rows):
    """Выгрузка строк в .xlsx (путь спрашивается). True — сохранено."""
    from pyrevit import forms
    from lowlife.xlsx_io import write_xlsx
    path = forms.save_file(file_ext='xlsx', default_name=u"СОУЭ — помещения объекта")
    if not path:
        return False
    write_xlsx(path, core.table_to_sheet(rows), sheet_name=u"Помещения",
               col_widths=[40, 8, 48, 12, 10, 3, 52, 8])
    return True


def import_rows():
    """Загрузка строк из .xlsx (путь спрашивается). None — отмена/ничего не прочитано."""
    from pyrevit import forms
    from lowlife.xlsx_io import read_xlsx
    path = forms.pick_file(file_ext='xlsx')
    if not path:
        return None
    rows = core.table_from_sheet(read_xlsx(path))
    if not rows:
        forms.alert(u"В файле не найден столбец «Помещение» или он пуст.", title=TITLE)
        return None
    return rows


def show_table_window(rows, heading, intro):
    """
    Окно таблицы: строка = имя помещения, кол-во, категория (список
    справочника), шум N (заполняется по категории, можно ввести вручную),
    «исключить». Поиск по имени, «Выгрузить в Excel…», «Загрузить из
    Excel…». Возвращает [RoomRow] (все показанные строки и загруженные из
    Excel, которых нет в окне) или None при отмене.
    """
    import clr
    clr.AddReference('PresentationFramework')
    clr.AddReference('PresentationCore')

    from System.Windows import (
        Window, WindowStartupLocation, Thickness, FontWeights, HorizontalAlignment,
        TextWrapping, GridLength, Visibility, VerticalAlignment
    )
    from System.Windows.Controls import (
        StackPanel, TextBlock, TextBox, Button, ComboBox, CheckBox, Orientation,
        ScrollViewer, ScrollBarVisibility, Grid, ColumnDefinition, DockPanel, Dock
    )
    from System.Windows.Media import Brushes

    from pyrevit import forms

    categories = [name for name, _ in core.NOISE_CATEGORIES]
    widths = [300, 50, 330, 70, 70]

    win = Window()
    win.Title = u"{}: помещения объекта".format(TITLE)
    win.Width = 900
    win.Height = 700
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    dock = DockPanel()
    dock.Margin = Thickness(14)
    win.Content = dock

    top = StackPanel()
    DockPanel.SetDock(top, Dock.Top)
    dock.Children.Add(top)

    def text(parent, value, bold=False, gray=False, size=None):
        block = TextBlock()
        block.Text = value
        block.TextWrapping = TextWrapping.Wrap
        if bold:
            block.FontWeight = FontWeights.Bold
        if gray:
            block.Foreground = Brushes.Gray
            block.FontSize = 11
        if size:
            block.FontSize = size
        parent.Children.Add(block)
        return block

    text(top, heading, bold=True, size=15)
    text(top, intro, gray=True).Margin = Thickness(0, 2, 0, 8)

    tools = StackPanel()
    tools.Orientation = Orientation.Horizontal
    tools.Margin = Thickness(0, 0, 0, 8)
    top.Children.Add(tools)
    text(tools, u"Поиск:").Margin = Thickness(0, 3, 6, 0)
    search = TextBox()
    search.Width = 220
    tools.Children.Add(search)
    only_missing = CheckBox()
    only_missing.Content = u"только без уровня шума"
    only_missing.Margin = Thickness(12, 3, 0, 0)
    tools.Children.Add(only_missing)
    export_btn = Button()
    export_btn.Content = u"Выгрузить в Excel…"
    export_btn.Padding = Thickness(8, 2, 8, 2)
    export_btn.Margin = Thickness(16, 0, 0, 0)
    tools.Children.Add(export_btn)
    import_btn = Button()
    import_btn.Content = u"Загрузить из Excel…"
    import_btn.Padding = Thickness(8, 2, 8, 2)
    import_btn.Margin = Thickness(8, 0, 0, 0)
    tools.Children.Add(import_btn)

    def make_grid():
        grid = Grid()
        for width in widths:
            column = ColumnDefinition()
            column.Width = GridLength(width)
            grid.ColumnDefinitions.Add(column)
        return grid

    def place(grid, element, column):
        Grid.SetColumn(element, column)
        element.Margin = Thickness(2, 1, 6, 1)
        element.VerticalAlignment = VerticalAlignment.Center
        grid.Children.Add(element)

    header = make_grid()
    for index, title in enumerate([u"Помещение", u"Кол-во", u"Категория", u"Шум N, дБА",
                                   u"Исключить"]):
        block = TextBlock()
        block.Text = title
        block.FontWeight = FontWeights.Bold
        place(header, block, index)
    top.Children.Add(header)

    bottom = StackPanel()
    bottom.Orientation = Orientation.Horizontal
    bottom.HorizontalAlignment = HorizontalAlignment.Right
    bottom.Margin = Thickness(0, 10, 0, 0)
    DockPanel.SetDock(bottom, Dock.Bottom)
    dock.Children.Add(bottom)
    status = TextBlock()
    status.Margin = Thickness(0, 3, 16, 0)
    status.Foreground = Brushes.Gray
    bottom.Children.Add(status)
    cancel_btn = Button()
    cancel_btn.Content = u"Отмена"
    cancel_btn.Padding = Thickness(10, 4, 10, 4)
    cancel_btn.Margin = Thickness(0, 0, 8, 0)
    bottom.Children.Add(cancel_btn)
    ok_btn = Button()
    ok_btn.Content = u"Сохранить"
    ok_btn.Padding = Thickness(10, 4, 10, 4)
    ok_btn.FontWeight = FontWeights.Bold
    bottom.Children.Add(ok_btn)

    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    body = StackPanel()
    scroll.Content = body
    dock.Children.Add(scroll)

    controls = []  # [(RoomRow, grid, category combo, noise box, exclude box)]
    extra = {}     # строки из Excel, которых нет в окне

    def noise_text(value):
        if value is None:
            return u""
        return (u"{:.0f}" if float(value) == int(float(value)) else u"{}").format(float(value))

    def apply_row(item, category, noise, exclude):
        _, _, combo, box, check = item
        combo.SelectedItem = category if category in categories else None
        if category and category not in categories:
            combo.Text = category
        box.Text = noise_text(noise if noise is not None else core.category_noise(category))
        check.IsChecked = bool(exclude)

    for row in rows:
        grid = make_grid()
        name = TextBlock()
        name.Text = row.name
        name.TextWrapping = TextWrapping.Wrap
        place(grid, name, 0)
        count = TextBlock()
        count.Text = u"{}".format(row.count) if row.count else u"—"
        place(grid, count, 1)
        combo = ComboBox()
        combo.IsEditable = True
        for category in categories:
            combo.Items.Add(category)
        place(grid, combo, 2)
        box = TextBox()
        place(grid, box, 3)
        check = CheckBox()
        place(grid, check, 4)
        item = (row, grid, combo, box, check)
        apply_row(item, row.category, row.noise, row.exclude)

        def on_category(sender, args, box=box):
            noise = core.category_noise(sender.SelectedItem)
            if noise is not None:
                box.Text = noise_text(noise)

        combo.SelectionChanged += on_category
        body.Children.Add(grid)
        controls.append(item)

    def read_row(item):
        """Строка из полей окна (или None + текст ошибки)."""
        row, _, combo, box, check = item
        category = combo.SelectedItem or (combo.Text or u"").strip()
        category = core.match_category(category) or category
        noise_value = (box.Text or u"").strip()
        noise = None
        if noise_value:
            noise = core.parse_number(noise_value)
            if noise is None:
                return None, u"{}: шум — нужно число".format(row.name)
        if noise is not None and noise == core.category_noise(category):
            noise = None  # совпадает с категорией — пусть следует за ней
        return core.RoomRow(row.name, row.count, category, noise, bool(check.IsChecked)), None

    def refresh(*args):
        words = core.normalize(search.Text).split()
        missing_only = bool(only_missing.IsChecked)
        shown = 0
        without = 0
        for item in controls:
            row, grid = item[0], item[1]
            current, _ = read_row(item)
            lacks = current is not None and not current.exclude and current.effective_noise() is None
            if lacks:
                without += 1
            visible = all(word in core.normalize(row.name) for word in words)
            if missing_only and not lacks:
                visible = False
            grid.Visibility = Visibility.Visible if visible else Visibility.Collapsed
            shown += 1 if visible else 0
        status.Text = u"Показано {} из {}; без уровня шума: {}".format(shown, len(controls), without)

    search.TextChanged += refresh
    only_missing.Checked += refresh
    only_missing.Unchecked += refresh

    def current_rows():
        result = []
        errors = []
        for item in controls:
            row, error = read_row(item)
            if error:
                errors.append(error)
            else:
                result.append(row)
        return result, errors

    def on_export(sender, args):
        current, errors = current_rows()
        if errors:
            forms.alert(u"Исправьте:\n\n" + u"\n".join(errors[:20]), title=TITLE)
            return
        export_rows(current + list(extra.values()))

    def on_import(sender, args):
        loaded = import_rows()
        if not loaded:
            return
        by_key = dict((item[0].key, item) for item in controls)
        applied = 0
        for row in loaded:
            item = by_key.get(row.key)
            if item is None:
                extra[row.key] = row
                continue
            apply_row(item, row.category, row.noise, row.exclude)
            applied += 1
        refresh()
        forms.alert(u"Загружено строк: {} (в этом окне: {}).".format(len(loaded), applied), title=TITLE)

    export_btn.Click += on_export
    import_btn.Click += on_import

    result = {"rows": None}

    def on_ok(sender, args):
        current, errors = current_rows()
        if errors:
            forms.alert(u"Исправьте:\n\n" + u"\n".join(errors[:20]), title=TITLE)
            return
        result["rows"] = current + list(extra.values())
        win.Close()

    def on_cancel(sender, args):
        win.Close()

    ok_btn.Click += on_ok
    cancel_btn.Click += on_cancel

    refresh()
    win.ShowDialog()
    return result["rows"]


def edit_all_rooms(doc):
    """Окно для всех имён помещений объекта (из Shift+клика). Сохраняет по «Сохранить»."""
    rows = core.merge_room_table(cfg.load_room_table(), room_name_counts(doc))
    edited = show_table_window(
        rows, u"Помещения объекта: уровень шума и исключения",
        u"Все уникальные имена помещений связей. Категория — из справочника расчёта СОУЭ "
        u"(шум подставляется сам, можно ввести свой). Отмеченные «Исключить» не оснащаются. "
        u"Новые имена заполнены по подсказке — проверьте. Можно выгрузить в Excel, "
        u"заполнить там и загрузить обратно.")
    if edited is not None:
        cfg.save_room_table(edited)
    return edited


def ask_missing_noise(rows):
    """
    Окно для помещений без уровня шума (при запуске). Сохраняет по
    «Сохранить»; возвращает строки или None при отмене.
    """
    edited = show_table_window(
        rows, u"Новые помещения и помещения без уровня шума",
        u"Этих имён ещё нет в таблице помещений объекта или у них не задан шум. Категория у "
        u"новых имён подобрана по имени — проверьте; выберите категорию, введите шум вручную "
        u"или отметьте «Исключить». Оставшиеся без шума будут пропущены (с сообщением в отчёте).")
    if edited is not None:
        cfg.save_room_table(edited)
    return edited
