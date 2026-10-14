# -*- coding: utf-8 -*-
"""
Окно кнопки «Параметры в ФОП» (Tools.panel/FopParameters).

Показывает параметры, нужные кнопкам выбранных систем (fop_catalog), —
с примером имени, типом данных, экземпляр/тип и категориями привязки;
пользователь правит имена прямо в таблице. Если в выбранном ФОП есть
похожий параметр (fop_catalog.match_fop), он подставляется вместо примера;
столбец «В ФОП» показывает, есть ли там параметр с текущим именем. Сверху —
системы, файл ФОП (подключённый к Revit, другой или новый), группа в ФОП и
префикс примеров.

show_dialog(app) → dict или None (отмена):
    rows           — все строки (fop_catalog.Row; работать с отмеченными)
    sp_path        — путь к ФОП (подключить, если отличается от текущего)
    create_file    — True, если файл по sp_path нужно сначала создать
    group          — группа в ФОП для новых определений
    write_fop      — создавать в ФОП параметры, которых там нет (иначе только
                     привязка уже существующих)
    write_settings — вписать имена в настройки кнопок систем
    systems        — id выбранных систем
"""

import os

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from pyrevit import forms

from System import Action
from System.Collections.Generic import List
from System.Windows import (
    Window, WindowStartupLocation, Thickness, FontWeights,
    HorizontalAlignment, VerticalAlignment, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, CheckBox, Orientation, DockPanel,
    Dock, DataGrid, DataGridTextColumn, DataGridCheckBoxColumn, DataGridLength,
    DataGridLengthUnitType, DataGridHeadersVisibility, DataGridGridLinesVisibility,
    DataGridSelectionMode, WrapPanel
)
from System.Windows.Data import Binding, BindingMode, UpdateSourceTrigger
from System.Windows.Media import Brushes

from lowlife import fop_catalog, fop_setup, settings_core


TITLE = u"Параметры LowLife в ФОП"


def read_system_settings():
    """{id системы: словарь из её файла настроек} (без подстановки общих значений)."""
    result = {}
    for system_id in fop_catalog.SYSTEM_IDS:
        store = settings_core.JsonStore(fop_catalog.SYSTEM_FILES[system_id], share=False)
        result[system_id] = dict(store.read())
    return result


def write_system_settings(updates):
    """Дописывает {id системы: {ключ: значение}} в файлы настроек систем."""
    written = []
    for system_id, values in updates.items():
        store = settings_core.JsonStore(fop_catalog.SYSTEM_FILES[system_id],
                                        fop_catalog.SYSTEM_TITLES[system_id])
        if store.update(values):
            written.append(fop_catalog.SYSTEM_TITLES[system_id])
    return written


def _star(n):
    return DataGridLength(n, DataGridLengthUnitType.Star)


def _text_col(header, path, width, read_only=True, wrap=False):
    binding = Binding(path)
    if not read_only:
        binding.Mode = BindingMode.TwoWay
        binding.UpdateSourceTrigger = UpdateSourceTrigger.PropertyChanged
    c = DataGridTextColumn()
    c.Header = header
    c.Binding = binding
    c.IsReadOnly = read_only
    c.Width = width
    if wrap:
        from System.Windows import Style, Setter
        style = Style(TextBlock)
        style.Setters.Add(Setter(TextBlock.TextWrappingProperty, TextWrapping.Wrap))
        c.ElementStyle = style
    return c


def _check_col(path):
    b = Binding(path)
    b.Mode = BindingMode.TwoWay
    b.UpdateSourceTrigger = UpdateSourceTrigger.PropertyChanged
    c = DataGridCheckBoxColumn()
    c.Header = u""
    c.Binding = b
    c.Width = DataGridLength.Auto
    return c


def _label(text, bold=False, gray=False, margin=None):
    tb = TextBlock()
    tb.Text = text
    tb.TextWrapping = TextWrapping.Wrap
    if bold:
        tb.FontWeight = FontWeights.Bold
    if gray:
        tb.FontSize = 11
        tb.Foreground = Brushes.Gray
    if margin is not None:
        tb.Margin = margin
    return tb


def _button(text, bold=False):
    b = Button()
    b.Content = text
    b.Padding = Thickness(10, 4, 10, 4)
    b.Margin = Thickness(0, 0, 8, 0)
    if bold:
        b.FontWeight = FontWeights.Bold
    return b


def _file_dialog(fn, **kwargs):
    """forms.pick_file/save_file; у старых pyRevit нет аргумента title."""
    try:
        return fn(**kwargs)
    except TypeError:
        kwargs.pop("title", None)
        return fn(**kwargs)


def show_dialog(app):
    saved = read_system_settings()
    shared = settings_core.read_shared()

    state = {
        "result": None,
        "prefix": fop_catalog.DEFAULT_PREFIX,
        "sp_path": fop_setup.connected_path(app),
        "create_file": False,
        "rows": [],
        "fop_defs": fop_setup.read_definitions(app, fop_setup.connected_path(app)),
    }

    win = Window()
    win.Title = TITLE
    win.Width = 1180
    win.Height = 760
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    header = StackPanel()
    header.Margin = Thickness(16, 12, 16, 8)
    DockPanel.SetDock(header, Dock.Top)

    title = _label(TITLE, bold=True)
    title.FontSize = 16
    header.Children.Add(title)
    header.Children.Add(_label(
        u"Список параметров, нужных кнопкам LowLife выбранных систем. Имена в столбце "
        u"«Имя параметра» — пример: поменяйте их под соглашение проекта (двойной клик "
        u"по ячейке). Отмеченные параметры будут созданы в файле ФОП (если их там ещё "
        u"нет) и привязаны к указанным категориям проекта; уже существующие "
        u"привязки дополняются, а не заменяются.",
        gray=True, margin=Thickness(0, 4, 0, 0)))

    # --- системы ---
    header.Children.Add(_label(u"① Системы", bold=True, margin=Thickness(0, 12, 0, 2)))
    systems_panel = WrapPanel()
    system_boxes = {}
    for system_id in fop_catalog.SYSTEM_IDS:
        cb = CheckBox()
        cb.Content = fop_catalog.SYSTEM_TITLES[system_id]
        cb.IsChecked = True
        cb.Margin = Thickness(0, 2, 16, 2)
        systems_panel.Children.Add(cb)
        system_boxes[system_id] = cb
    header.Children.Add(systems_panel)

    # --- файл ФОП ---
    header.Children.Add(_label(u"② Файл общих параметров (ФОП)", bold=True,
                               margin=Thickness(0, 12, 0, 2)))
    fop_row = DockPanel()
    fop_buttons = StackPanel()
    fop_buttons.Orientation = Orientation.Horizontal
    DockPanel.SetDock(fop_buttons, Dock.Right)
    pick_btn = _button(u"Выбрать файл…")
    new_btn = _button(u"Создать новый…")
    new_btn.Margin = Thickness(0)
    fop_buttons.Children.Add(pick_btn)
    fop_buttons.Children.Add(new_btn)
    fop_row.Children.Add(fop_buttons)
    fop_text = TextBlock()
    fop_text.VerticalAlignment = VerticalAlignment.Center
    fop_text.TextWrapping = TextWrapping.Wrap
    fop_text.Margin = Thickness(0, 0, 12, 0)
    fop_row.Children.Add(fop_text)
    header.Children.Add(fop_row)

    def refresh_fop_text():
        path = state["sp_path"]
        if not path:
            fop_text.Text = u"К Revit не подключён файл ФОП — выберите существующий или создайте новый."
            fop_text.Foreground = Brushes.Firebrick
        elif state["create_file"]:
            fop_text.Text = u"{}  (будет создан)".format(path)
            fop_text.Foreground = Brushes.Black
        else:
            fop_text.Text = path
            fop_text.Foreground = Brushes.Black

    refresh_fop_text()

    def on_pick(sender, args):
        path = _file_dialog(forms.pick_file, file_ext="txt",
                            title=u"Файл общих параметров (ФОП)")
        if path:
            state["sp_path"] = path
            state["create_file"] = False
            state["fop_defs"] = fop_setup.read_definitions(app, path)
            refresh_fop_text()
            refresh_fop()

    def on_new(sender, args):
        path = _file_dialog(forms.save_file, file_ext="txt", default_name=u"LowLife_ФОП",
                            title=u"Новый файл общих параметров")
        if path:
            exists = os.path.isfile(path)
            state["sp_path"] = path
            state["create_file"] = not exists
            state["fop_defs"] = fop_setup.read_definitions(app, path) if exists else []
            refresh_fop_text()
            refresh_fop()

    pick_btn.Click += on_pick
    new_btn.Click += on_new

    # --- группа, префикс, настройки ---
    header.Children.Add(_label(u"③ Группа и имена", bold=True, margin=Thickness(0, 12, 0, 2)))
    opts = WrapPanel()

    def add_field(caption, text, width):
        opts.Children.Add(_label(caption, margin=Thickness(0, 4, 6, 0)))
        box = TextBox()
        box.Text = text
        box.Width = width
        box.Padding = Thickness(3)
        box.Margin = Thickness(0, 0, 20, 0)
        opts.Children.Add(box)
        return box

    group_box = add_field(u"Группа в ФОП для новых параметров:", fop_catalog.DEFAULT_GROUP, 180)
    prefix_box = add_field(u"Префикс имён-примеров:", fop_catalog.DEFAULT_PREFIX, 100)
    write_fop_box = CheckBox()
    write_fop_box.Content = u"Записывать в ФОП недостающие параметры"
    write_fop_box.IsChecked = False
    write_fop_box.Margin = Thickness(0, 4, 20, 0)
    opts.Children.Add(write_fop_box)
    write_box = CheckBox()
    write_box.Content = u"Вписать имена в настройки кнопок выбранных систем"
    write_box.IsChecked = True
    write_box.Margin = Thickness(0, 4, 0, 0)
    opts.Children.Add(write_box)
    header.Children.Add(opts)
    header.Children.Add(_label(
        u"Имена, уже введённые в настройках кнопок, подставлены как есть. Если в ФОП "
        u"есть похожий параметр (например «Длина проводника» с префиксом проекта), он "
        u"подставлен вместо примера — столбец «В ФОП». Параметр, который уже есть в ФОП "
        u"(в любой группе), берётся оттуда. Параметры, которых нет ни в ФОП, ни в "
        u"проекте, создаются в ФОП только при включённом «Записывать в ФОП», иначе "
        u"пропускаются. Префикс меняет только примеры, которые вы не правили.",
        gray=True, margin=Thickness(0, 4, 0, 6)))

    # --- таблица ---
    grid = DataGrid()
    grid.Margin = Thickness(16, 0, 16, 0)
    grid.AutoGenerateColumns = False
    grid.CanUserAddRows = False
    grid.CanUserDeleteRows = False
    grid.CanUserResizeRows = False
    grid.CanUserSortColumns = False
    grid.HeadersVisibility = DataGridHeadersVisibility.Column
    grid.GridLinesVisibility = DataGridGridLinesVisibility.Horizontal
    grid.SelectionMode = DataGridSelectionMode.Single
    grid.Columns.Add(_check_col("Checked"))
    grid.Columns.Add(_text_col(u"Назначение", "Label", _star(2.2), wrap=True))
    name_col = _text_col(u"Имя параметра", "Name", _star(1.6), read_only=False)
    name_col.FontWeight = FontWeights.Bold
    grid.Columns.Add(name_col)
    grid.Columns.Add(_text_col(u"В ФОП", "FopStatus", _star(1.4), wrap=True))
    grid.Columns.Add(_text_col(u"Пример", "Example", _star(1.2)))
    grid.Columns.Add(_text_col(u"Тип данных", "DataType", DataGridLength.Auto))
    grid.Columns.Add(_text_col(u"Экз./тип", "Kind", DataGridLength.Auto))
    grid.Columns.Add(_text_col(u"Категории", "Categories", _star(2.2), wrap=True))
    grid.Columns.Add(_text_col(u"Системы", "Systems", _star(1.0), wrap=True))
    grid.Columns.Add(_text_col(u"Примечание", "Note", _star(1.8), wrap=True))

    def commit():
        try:
            grid.CommitEdit()
            grid.CommitEdit()
        except Exception:
            pass

    def write_fop():
        return bool(write_fop_box.IsChecked)

    def selected_systems():
        return [s for s in fop_catalog.SYSTEM_IDS if system_boxes[s].IsChecked]

    def rebuild(*_args):
        commit()
        old = dict((r.key, r) for r in state["rows"])
        rows = fop_catalog.build_rows(selected_systems(), saved, shared, state["prefix"])
        for r in rows:
            prev = old.get(r.key)
            if prev is not None:
                r.Name = prev.Name
                r.auto_name = prev.auto_name
                r.source = prev.source
                r.Checked = prev.Checked
        state["rows"] = rows
        fop_catalog.match_fop(rows, state["fop_defs"])
        fop_catalog.update_status(rows, state["fop_defs"], write_fop())
        data = List[object]()
        for r in rows:
            data.Add(r)
        grid.ItemsSource = data

    def refresh_grid():
        try:
            grid.Items.Refresh()
        except Exception:
            pass

    def refresh_fop():
        commit()
        fop_catalog.match_fop(state["rows"], state["fop_defs"])
        fop_catalog.update_status(state["rows"], state["fop_defs"], write_fop())
        refresh_grid()

    def after_edit():
        fop_catalog.update_status(state["rows"], state["fop_defs"], write_fop())
        refresh_grid()

    # Обновить «В ФОП» после правки имени — уже после выхода ячейки из
    # редактирования (во время него Items.Refresh запрещён).
    grid.CellEditEnding += lambda s, a: grid.Dispatcher.BeginInvoke(Action(after_edit))

    for cb in system_boxes.values():
        cb.Checked += rebuild
        cb.Unchecked += rebuild

    def on_prefix_changed(sender, args):
        commit()
        new_prefix = prefix_box.Text or u""
        fop_catalog.change_prefix(state["rows"], state["prefix"], new_prefix)
        state["prefix"] = new_prefix
        fop_catalog.update_status(state["rows"], state["fop_defs"], write_fop())
        refresh_grid()

    prefix_box.TextChanged += on_prefix_changed
    write_fop_box.Checked += lambda s, a: after_edit()
    write_fop_box.Unchecked += lambda s, a: after_edit()

    rebuild()

    # --- кнопки ---
    buttons = DockPanel()
    buttons.Margin = Thickness(16, 8, 16, 12)
    DockPanel.SetDock(buttons, Dock.Bottom)

    left = StackPanel()
    left.Orientation = Orientation.Horizontal
    DockPanel.SetDock(left, Dock.Left)
    all_btn = _button(u"Отметить все")
    none_btn = _button(u"Снять все")
    left.Children.Add(all_btn)
    left.Children.Add(none_btn)

    right = StackPanel()
    right.Orientation = Orientation.Horizontal
    right.HorizontalAlignment = HorizontalAlignment.Right
    cancel_btn = _button(u"Отмена")
    ok_btn = _button(u"Добавить в ФОП и привязать", bold=True)
    ok_btn.Margin = Thickness(0)
    right.Children.Add(cancel_btn)
    right.Children.Add(ok_btn)

    buttons.Children.Add(left)
    buttons.Children.Add(right)

    def set_all(value):
        commit()
        for r in state["rows"]:
            r.Checked = value
        grid.Items.Refresh()

    all_btn.Click += lambda s, a: set_all(True)
    none_btn.Click += lambda s, a: set_all(False)

    def on_ok(sender, args):
        commit()
        rows = state["rows"]
        problems = []
        if write_fop() and not state["sp_path"]:
            problems.append(u"Не выбран файл ФОП, куда записывать параметры.")
        group = (group_box.Text or u"").strip()
        if write_fop() and not group:
            problems.append(u"Не задана группа в ФОП.")
        if not any(r.Checked for r in rows):
            problems.append(u"Не отмечено ни одного параметра.")
        problems.extend(fop_catalog.validate(rows))
        if problems:
            forms.alert(u"\n".join(problems), title=TITLE)
            return
        state["result"] = {
            "rows": rows,
            "sp_path": state["sp_path"],
            "create_file": state["create_file"],
            "group": group,
            "write_fop": write_fop(),
            "write_settings": bool(write_box.IsChecked),
            "systems": selected_systems(),
        }
        win.Close()

    ok_btn.Click += on_ok
    cancel_btn.Click += lambda s, a: win.Close()

    outer.Children.Add(header)
    outer.Children.Add(buttons)
    outer.Children.Add(grid)
    win.Content = outer
    win.ShowDialog()

    return state["result"]
