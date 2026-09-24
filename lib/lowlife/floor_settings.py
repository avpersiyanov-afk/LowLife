# -*- coding: utf-8 -*-
"""
Окно настроек для кнопки «Заполнение этажа» (LOI.panel/FillFloor) + их
хранение между запусками.

Хранится в JSON-файле %APPDATA%\\pyRevit\\LowLifeFloor_settings.json — тот
же подход, что loi_settings.py/scs_settings.py (простой файл вместо
pyrevit.script.get_config()).

Две настройки:
  - target_param_name — имя параметра, в который пишется значение этажа
    (например «Этаж»). Один параметр для всех уровней.
  - level_values — {имя уровня: значение для его элементов} (по одному на
    строке таблицы «Уровень / Значение», см. show_settings_form). Значения
    для уровней, у которых поле оставили пустым, не сохраняются — такие
    уровни при заполнении пропускаются (см. floor_fill.py).

Уровни хранятся ПО ИМЕНИ, а не по ElementId — тот же довод, что в
filter_selection.py: Id не гарантированно совпадает между документами/после
пересоздания уровня, а имя обычно стабильно.
"""

import os
import io
import json

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from pyrevit import forms

from lowlife import settings_transfer

from System.Collections.Generic import List

from System.Windows import (
    Window, WindowStartupLocation, Thickness,
    FontWeights, HorizontalAlignment, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, Orientation, DockPanel, Dock,
    DataGrid, DataGridTextColumn, DataGridLength, DataGridLengthUnitType,
    DataGridHeadersVisibility, DataGridGridLinesVisibility, DataGridSelectionMode
)
from System.Windows.Data import Binding, BindingMode, UpdateSourceTrigger
from System.Windows.Media import Brushes

SETTINGS_FILE_NAME = "LowLifeFloor_settings.json"

PARAM_KEY = "target_param_name"
PARAM_LABEL = u"Параметр «Этаж»"
LEVEL_VALUES_KEY = "level_values"


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
        forms.alert(
            u"Не удалось сохранить настройки в файл:\n{}".format(path)
        )


def load_saved_values():
    """Строковые значения настроек: из JSON-файла, иначе — значения по умолчанию."""
    saved = _read_all()
    level_values = saved.get(LEVEL_VALUES_KEY, {})
    if not isinstance(level_values, dict):
        level_values = {}
    return {
        PARAM_KEY: saved.get(PARAM_KEY, u""),
        LEVEL_VALUES_KEY: {unicode(k): unicode(v) for k, v in level_values.items()},
    }


def save_values(values):
    data = _read_all()
    data.update(values)
    _write_all(data)


def get_level_values(settings):
    """{имя уровня: значение} — без пустых значений."""
    raw = settings.get(LEVEL_VALUES_KEY) or {}
    return {name: val for name, val in raw.items() if unicode(val or u"").strip()}


def require(settings):
    """
    Проверяет обязательные настройки. Останавливает скрипт через
    forms.alert(exitscript=True), если чего-то не хватает.
    """
    missing = []

    if not unicode(settings.get(PARAM_KEY) or u"").strip():
        missing.append(PARAM_LABEL)

    if not get_level_values(settings):
        missing.append(u"Значения по уровням")

    if missing:
        forms.alert(
            u"Не заполнены обязательные настройки:\n\n{}\n\n"
            u"Откройте настройки: Shift+клик по кнопке «Заполнение этажа».".format(
                u"\n".join(missing)
            ),
            exitscript=True
        )


# --- таблица «Уровень / Значение» (WPF DataGrid, см. rename_by_list._show_rename_dialog) --

class _LevelRow(object):
    def __init__(self, level_name, value):
        self.LevelName = level_name
        self.Value = value


def _star(n):
    return DataGridLength(n, DataGridLengthUnitType.Star)


def show_settings_form(doc, values):
    """
    Модальное окно редактирования настроек. Возвращает словарь значений
    (PARAM_KEY/LEVEL_VALUES_KEY) или None, если пользователь отменил.
    """
    from lowlife import geometry

    levels = geometry.get_document_levels(doc)
    saved_level_values = values.get(LEVEL_VALUES_KEY) or {}

    result = {"values": None}

    win = Window()
    win.Title = u"Настройки: Заполнение этажа"
    win.Width = 640
    win.Height = 640
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    header = StackPanel()
    header.Margin = Thickness(16, 12, 16, 8)
    DockPanel.SetDock(header, Dock.Top)

    title = TextBlock()
    title.Text = u"Параметр «Этаж» и значения по уровням"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    header.Children.Add(title)

    hint = TextBlock()
    hint.Text = u"Значения сохраняются и подставляются при следующих запусках."
    hint.FontSize = 11
    hint.Foreground = Brushes.Gray
    hint.Margin = Thickness(0, 4, 0, 0)
    header.Children.Add(hint)

    param_section = TextBlock()
    param_section.Text = u"① Параметр «Этаж»"
    param_section.FontWeight = FontWeights.Bold
    param_section.Margin = Thickness(0, 14, 0, 2)
    header.Children.Add(param_section)

    param_label = TextBlock()
    param_label.Text = u"Имя параметра элемента, в который записывается этаж *"
    param_label.TextWrapping = TextWrapping.Wrap
    param_label.Margin = Thickness(0, 2, 0, 2)
    header.Children.Add(param_label)

    param_box = TextBox()
    param_box.Text = values.get(PARAM_KEY, u"")
    param_box.Padding = Thickness(4)
    header.Children.Add(param_box)

    levels_section = TextBlock()
    levels_section.Text = u"② Значения по уровням"
    levels_section.FontWeight = FontWeights.Bold
    levels_section.Margin = Thickness(0, 14, 0, 2)
    header.Children.Add(levels_section)

    levels_hint = TextBlock()
    levels_hint.Text = (
        u"Для каждого уровня впишите, что записывать в параметр «Этаж» "
        u"элементам, физически расположенным на этом уровне (см. "
        u"lowlife.geometry.get_element_level — по Element.LevelId). Пустое "
        u"значение — уровень пропускается при заполнении."
    )
    levels_hint.FontSize = 11
    levels_hint.Foreground = Brushes.Gray
    levels_hint.TextWrapping = TextWrapping.Wrap
    levels_hint.Margin = Thickness(0, 0, 0, 6)
    header.Children.Add(levels_hint)

    if not levels:
        no_levels = TextBlock()
        no_levels.Text = u"В документе не найдено ни одного уровня."
        no_levels.Foreground = Brushes.Firebrick
        no_levels.TextWrapping = TextWrapping.Wrap
        header.Children.Add(no_levels)

    data = List[object]()
    for lv in levels:
        name = geometry.level_name(lv)
        data.Add(_LevelRow(name, saved_level_values.get(name, u"")))

    grid = DataGrid()
    grid.Margin = Thickness(16, 0, 16, 0)
    grid.AutoGenerateColumns = False
    grid.CanUserAddRows = False
    grid.CanUserDeleteRows = False
    grid.CanUserResizeRows = False
    grid.HeadersVisibility = DataGridHeadersVisibility.Column
    grid.GridLinesVisibility = DataGridGridLinesVisibility.Horizontal
    grid.SelectionMode = DataGridSelectionMode.Single
    grid.IsReadOnly = False
    grid.ItemsSource = data

    level_col = DataGridTextColumn()
    level_col.Header = u"Уровень"
    level_col.Binding = Binding("LevelName")
    level_col.IsReadOnly = True
    level_col.Width = _star(1)
    grid.Columns.Add(level_col)

    value_binding = Binding("Value")
    value_binding.Mode = BindingMode.TwoWay
    value_binding.UpdateSourceTrigger = UpdateSourceTrigger.PropertyChanged
    value_col = DataGridTextColumn()
    value_col.Header = u"Значение для элементов этого уровня"
    value_col.Binding = value_binding
    value_col.Width = _star(1)
    grid.Columns.Add(value_col)

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
        try:
            grid.CommitEdit()
        except:
            pass

        level_values = {}
        for row in data:
            val = unicode(row.Value or u"").strip()
            if val:
                level_values[row.LevelName] = val

        result["values"] = {
            PARAM_KEY: param_box.Text,
            LEVEL_VALUES_KEY: level_values,
        }
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
        buttons, _read_all, _write_all, u"заполнения этажа", _on_settings_imported
    )

    outer.Children.Add(header)
    outer.Children.Add(buttons)
    outer.Children.Add(grid)

    win.Content = outer
    win.ShowDialog()

    return result["values"]


def get_settings_interactive(doc):
    """
    Показывает окно настроек, сохраняет введённые значения и возвращает
    их. Возвращает None, если пользователь нажал «Отмена». Открывается
    по Shift+клику на кнопке «Заполнение этажа».
    """
    while True:
        saved = load_saved_values()
        edited = show_settings_form(doc, saved)

        if edited == settings_transfer.RELOAD:
            continue

        if edited is None:
            return None

        save_values(edited)
        return edited


def get_settings_silent():
    """Настройки без показа окна — уже сохранённые значения (или значения
    по умолчанию, если ещё не настроено). Используется кнопкой «Заполнение этажа»."""
    return load_saved_values()
