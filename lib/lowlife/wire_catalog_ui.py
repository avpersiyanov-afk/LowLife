# -*- coding: utf-8 -*-
"""
UI справочника кабелей (кнопки панели «Кабели»): выбор справочника, если
в модели их несколько, и окно правки — таблица всех строк ключевой
спецификации, в которой можно менять значения, добавлять строки и
копировать выбранную строку как основу для нового кабеля.

Таблица построена на System.Data.DataTable: столбцы справочника
произвольные (имена параметров проекта), а DataGrid привязывается к
DataTable без Python-классов со свойствами. Имена столбцов DataTable —
служебные c0, c1, ... (имена параметров с точками/скобками ломают путь
привязки), заголовок в DataGrid — настоящее имя поля.

Правки применяются одной транзакцией по кнопке «Сохранить» через
wire_catalog.apply_entries; окно закрывается, итог показывает кнопка.
"""

import clr
clr.AddReference('System.Data')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System import String, Int32, DBNull
from System.Data import DataTable

from System.Windows import (
    Window, WindowStartupLocation, Thickness, FontWeights, TextWrapping,
    HorizontalAlignment,
)
from System.Windows.Controls import (
    StackPanel, TextBlock, Button, Orientation, DockPanel, Dock, DataGrid,
    DataGridTextColumn, DataGridHeadersVisibility, DataGridSelectionMode,
    DataGridSelectionUnit, DataGridLength, DataGridLengthUnitType,
)
from System.Windows.Data import Binding, BindingMode, UpdateSourceTrigger

from pyrevit import forms

from lowlife import wire_catalog

ID_COL = u"_id"


def choose_catalog(doc, title):
    """
    Справочник кабелей модели (wire_catalog.KeySchedule). Несколько — даём
    выбрать; ни одного — сообщение и выход из скрипта.
    """
    catalogs = wire_catalog.find_wire_catalogs(doc)
    if not catalogs:
        # пустой справочник (строк ещё нет) find_wire_catalogs отбрасывает —
        # для правки/загрузки он годится
        catalogs = [ks for ks in wire_catalog.list_key_schedules(doc) if ks.is_circuit]
    if not catalogs:
        forms.alert(
            u"Справочник кабелей не найден: в модели нет ключевой спецификации "
            u"категории «Электрические цепи».",
            title=title, exitscript=True)
    if len(catalogs) == 1:
        return catalogs[0]

    by_label = {}
    for ks in catalogs:
        by_label[u"{} ({} строк)".format(ks.name, len(ks.rows))] = ks
    picked = forms.SelectFromList.show(
        sorted(by_label.keys()), title=u"Какой справочник кабелей", button_name=u"Выбрать")
    if not picked:
        import sys
        sys.exit()
    return by_label[picked]


def _cell(value):
    if value is None or value is DBNull.Value:
        return u""
    return unicode(value)


def show_edit_window(doc, ks):
    """
    Показывает таблицу справочника. Возвращает entries для
    wire_catalog.apply_entries (только изменённые и новые строки) или
    None, если пользователь закрыл окно без сохранения.
    """
    fields = ks.field_names()
    writable = wire_catalog.writable_fields(ks)
    columns = [wire_catalog.KEY_COLUMN] + fields

    table = DataTable()
    table.Columns.Add(ID_COL, Int32)
    for i in range(len(columns)):
        table.Columns.Add(u"c{}".format(i), String)

    originals = {}
    rows_by_id = {}
    for row in ks.rows:
        values = wire_catalog.row_values(row, fields)
        rid = row.Id.IntegerValue
        originals[rid] = values
        rows_by_id[rid] = row
        dr = table.NewRow()
        dr[ID_COL] = rid
        for i, v in enumerate(values):
            dr[u"c{}".format(i)] = v
        table.Rows.Add(dr)

    result = {"entries": None}

    win = Window()
    win.Title = u"Справочник кабелей — {}".format(ks.name)
    win.Width = 1000
    win.Height = 620
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    header = StackPanel()
    header.Margin = Thickness(16, 12, 16, 8)
    DockPanel.SetDock(header, Dock.Top)
    title = TextBlock()
    title.Text = u"{} — {} строк".format(ks.name, len(ks.rows))
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    header.Children.Add(title)
    info = TextBlock()
    info.Text = (
        u"Меняйте значения прямо в ячейках. Новая строка — пустая строка внизу "
        u"таблицы или кнопка «Копировать строку» (копия выбранной как основа). "
        u"Ключевые имена должны быть уникальными. Серые столбцы вычисляемые или "
        u"только для чтения. Удалять строки здесь нельзя — на них могут ссылаться цепи."
    )
    info.FontSize = 11
    info.TextWrapping = TextWrapping.Wrap
    info.Margin = Thickness(0, 4, 0, 0)
    header.Children.Add(info)
    outer.Children.Add(header)

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(16, 8, 16, 12)
    DockPanel.SetDock(buttons, Dock.Bottom)

    grid = DataGrid()
    grid.Margin = Thickness(16, 0, 16, 0)
    grid.AutoGenerateColumns = False
    grid.CanUserAddRows = True
    grid.CanUserDeleteRows = False
    grid.HeadersVisibility = DataGridHeadersVisibility.Column
    grid.SelectionMode = DataGridSelectionMode.Single
    grid.SelectionUnit = DataGridSelectionUnit.FullRow
    grid.ItemsSource = table.DefaultView

    for i, name in enumerate(columns):
        col = DataGridTextColumn()
        col.Header = name
        binding = Binding(u"c{}".format(i))
        binding.Mode = BindingMode.TwoWay
        binding.UpdateSourceTrigger = UpdateSourceTrigger.LostFocus
        col.Binding = binding
        col.Width = DataGridLength(2 if i == 0 else 1, DataGridLengthUnitType.Star)
        if i > 0 and not writable.get(name):
            col.IsReadOnly = True
            col.Header = u"{} (только чтение)".format(name)
        grid.Columns.Add(col)

    def on_copy(sender, args):
        grid.CommitEdit()
        view = grid.SelectedItem
        try:
            src = view.Row
        except Exception:
            forms.alert(u"Выберите строку, которую копировать.")
            return
        dr = table.NewRow()
        for i in range(len(columns)):
            dr[u"c{}".format(i)] = _cell(src[u"c{}".format(i)])
        dr[u"c0"] = u"{} (копия)".format(_cell(src[u"c0"]))
        table.Rows.Add(dr)
        try:
            grid.ScrollIntoView(grid.Items[grid.Items.Count - 2])
        except Exception:
            pass

    def on_save(sender, args):
        grid.CommitEdit()
        grid.CommitEdit()
        entries = []
        for dr in table.Rows:
            values = [_cell(dr[u"c{}".format(i)]) for i in range(len(columns))]
            rid = dr[ID_COL]
            if rid is None or rid is DBNull.Value:
                if not any(v.strip() for v in values):
                    continue
                entries.append((None, dict(zip(columns, values))))
                continue
            rid = int(rid)
            if values == originals.get(rid):
                continue
            changed = dict(
                (columns[i], values[i]) for i in range(len(columns))
                if values[i] != originals[rid][i]
            )
            entries.append((rows_by_id[rid], changed))
        result["entries"] = entries
        win.Close()

    def on_cancel(sender, args):
        win.Close()

    for text, handler in ((u"Копировать строку", on_copy),
                          (u"Сохранить", on_save),
                          (u"Отмена", on_cancel)):
        b = Button()
        b.Content = text
        b.Padding = Thickness(12, 4, 12, 4)
        b.Margin = Thickness(8, 0, 0, 0)
        b.Click += handler
        buttons.Children.Add(b)

    outer.Children.Add(buttons)
    outer.Children.Add(grid)
    win.Content = outer
    win.ShowDialog()
    return result["entries"]


def report_stats(stats, title):
    """Итог apply_entries — окном."""
    parts = [
        u"Добавлено строк: {}".format(stats["added"]),
        u"Изменено строк: {} (значений: {})".format(stats["updated"], stats["changed"]),
    ]
    if stats.get("unchanged"):
        parts.append(u"Без изменений: {}".format(stats["unchanged"]))
    errors = stats.get("errors") or []
    if errors:
        parts.append(u"")
        parts.append(u"Проблемы ({}):".format(len(errors)))
        parts.extend(errors[:20])
        if len(errors) > 20:
            parts.append(u"… и ещё {}".format(len(errors) - 20))
    forms.alert(u"\n".join(parts), title=title)
