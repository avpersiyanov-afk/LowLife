# -*- coding: utf-8 -*-
"""
Окно настроек кнопки «Проверка LOI» (LOI.panel/CheckLOI) + их хранение
между запусками.

Хранится в JSON-файле %APPDATA%\\pyRevit\\LowLifeLOICheck_settings.json —
тот же подход, что floor_settings.py/loi_settings.py (простой файл вместо
pyrevit.script.get_config()).

Настройки:
  - category_names — проверяемые категории, по имени (как в
    filter_selection.py: Id категорий не гарантированно совпадают между
    документами, имя стабильно);
  - labels_text — список параметров «как в требованиях LOI», по одному на
    строке (шаг ① — вписывается сначала);
  - param_map — {строка списка: имя параметра модели} (шаг ② — для каждой
    строки вписывается нужный параметр; пусто — берётся сама строка, см.
    loi_check_core.build_rows);
  - floor_param_name — параметр для столбца «Этаж»; пусто — тот же, что
    у кнопки «Заполнение этажа», а если и там пусто — уровень элемента.
"""

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from pyrevit import forms

from lowlife import settings_core, settings_transfer, loi_check_core as core

from System.Collections.Generic import List

from System.Windows import (
    Window, WindowStartupLocation, Thickness,
    FontWeights, HorizontalAlignment, VerticalAlignment, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, Orientation, DockPanel, Dock,
    ScrollViewer, ScrollBarVisibility,
    DataGrid, DataGridTextColumn, DataGridLength, DataGridLengthUnitType,
    DataGridHeadersVisibility, DataGridGridLinesVisibility, DataGridSelectionMode
)
from System.Windows.Data import Binding, BindingMode, UpdateSourceTrigger
from System.Windows.Media import Brushes

SETTINGS_FILE_NAME = "LowLifeLOICheck_settings.json"
BUTTON_NAME = u"Проверка LOI"

CATEGORIES_KEY = "category_names"
LABELS_KEY = "labels_text"
PARAM_MAP_KEY = "param_map"
FLOOR_KEY = "floor_param_name"


_STORE = settings_core.JsonStore(SETTINGS_FILE_NAME)
_settings_file_path = _STORE.path
_read_all = _STORE.read
_write_all = _STORE.write


def load_saved_values():
    """Значения настроек: из JSON-файла, иначе — значения по умолчанию."""
    saved = _read_all()
    names = saved.get(CATEGORIES_KEY, [])
    param_map = saved.get(PARAM_MAP_KEY, {})
    return {
        CATEGORIES_KEY: [unicode(n) for n in names] if isinstance(names, list) else [],
        LABELS_KEY: unicode(saved.get(LABELS_KEY, u"") or u""),
        PARAM_MAP_KEY: ({unicode(k): unicode(v) for k, v in param_map.items()}
                        if isinstance(param_map, dict) else {}),
        FLOOR_KEY: unicode(saved.get(FLOOR_KEY, u"") or u""),
    }


def save_values(values):
    data = _read_all()
    data.update(values)
    _write_all(data)


def get_rows(settings):
    """[(строка списка, имя параметра)] — см. loi_check_core.build_rows."""
    labels = core.parse_labels(settings.get(LABELS_KEY))
    return core.build_rows(labels, settings.get(PARAM_MAP_KEY))


def get_floor_param(settings):
    """Параметр столбца «Этаж»: свой, иначе из «Заполнения этажа», иначе u""."""
    own = unicode(settings.get(FLOOR_KEY) or u"").strip()
    if own:
        return own
    try:
        from lowlife import floor_settings
        return unicode(floor_settings.load_saved_values().get(floor_settings.PARAM_KEY) or u"").strip()
    except Exception:
        return u""


def require(settings):
    """Останавливает скрипт через forms.alert(exitscript=True), если не
    выбраны категории или пуст список параметров."""
    missing = []
    if not settings.get(CATEGORIES_KEY):
        missing.append(u"Категории для проверки")
    if not get_rows(settings):
        missing.append(u"Список параметров")
    if missing:
        forms.alert(
            u"Не заполнены обязательные настройки:\n\n{}\n\n"
            u"Откройте настройки: Shift+клик по кнопке «{}».".format(
                u"\n".join(missing), BUTTON_NAME),
            exitscript=True
        )


# --- окно ----------------------------------------------------------------------

class _ParamRow(object):
    def __init__(self, label, param):
        self.Label = label
        self.Param = param


def _star(n):
    return DataGridLength(n, DataGridLengthUnitType.Star)


def _section(text, top=16):
    tb = TextBlock()
    tb.Text = text
    tb.FontWeight = FontWeights.Bold
    tb.Margin = Thickness(0, top, 0, 2)
    return tb


def _hint(text):
    tb = TextBlock()
    tb.Text = text
    tb.FontSize = 11
    tb.Foreground = Brushes.Gray
    tb.TextWrapping = TextWrapping.Wrap
    tb.Margin = Thickness(0, 2, 0, 4)
    return tb


def _categories_label_text(names):
    if not names:
        return u"Категории не выбраны."
    preview = u"; ".join(sorted(names)[:6])
    if len(names) > 6:
        preview += u"; …"
    return u"Выбрано: {}. {}".format(len(names), preview)


def show_settings_form(doc, values):
    """Модальное окно настроек. Возвращает словарь значений или None (отмена)."""
    from lowlife import loi_check

    result = {"values": None}
    state = {
        "categories": list(values.get(CATEGORIES_KEY) or []),
        # все когда-либо вписанные соответствия — строку можно удалить из
        # списка и вернуть, не теряя вписанный для неё параметр
        "map": dict(values.get(PARAM_MAP_KEY) or {}),
    }

    win = Window()
    win.Title = u"Настройки: " + BUTTON_NAME
    win.Width = 720
    win.Height = 820
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    root = StackPanel()
    root.Margin = Thickness(16)

    title = TextBlock()
    title.Text = u"Что проверять и какие столбцы выводить в спецификацию"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    root.Children.Add(title)
    root.Children.Add(_hint(u"Значения сохраняются и подставляются при следующих запусках."))

    # --- ① категории ---------------------------------------------------------
    root.Children.Add(_section(u"① Категории семейств", 8))

    cat_row = StackPanel()
    cat_row.Orientation = Orientation.Horizontal
    cat_row.Margin = Thickness(0, 4, 0, 0)

    cat_btn = Button()
    cat_btn.Content = u"Выбрать категории…"
    cat_btn.Padding = Thickness(8, 2, 8, 2)
    cat_row.Children.Add(cat_btn)

    cat_label = TextBlock()
    cat_label.Text = _categories_label_text(state["categories"])
    cat_label.VerticalAlignment = VerticalAlignment.Center
    cat_label.Margin = Thickness(8, 0, 0, 0)
    cat_label.TextWrapping = TextWrapping.Wrap
    cat_row.Children.Add(cat_label)
    root.Children.Add(cat_row)

    root.Children.Add(_hint(
        u"Проверяются все экземпляры отмеченных категорий в текущем файле. "
        u"По каждой категории строится своя спецификация."))

    def on_pick_categories(sender, args):
        options = loi_check.list_categories(doc)
        if not options:
            forms.alert(u"В документе нет модельных элементов.")
            return
        checked = set(n.lower() for n in state["categories"])
        items = [forms.TemplateListItem(o, checked=(o.raw_name.lower() in checked))
                 for o in options]
        chosen = forms.SelectFromList.show(
            items,
            title=u"Категории для проверки LOI (в скобках — число элементов)",
            button_name=u"Сохранить",
            multiselect=True
        )
        if chosen is None:
            return
        state["categories"] = [o.raw_name for o in chosen]
        cat_label.Text = _categories_label_text(state["categories"])

    cat_btn.Click += on_pick_categories

    # --- ② список параметров ---------------------------------------------------
    root.Children.Add(_section(u"② Список параметров (по одному на строке) *"))
    root.Children.Add(_hint(
        u"Впишите параметры так, как они названы в требованиях LOI, — по "
        u"одному на строке. Строка станет заголовком столбца спецификации."))

    labels_box = TextBox()
    labels_box.Text = values.get(LABELS_KEY, u"")
    labels_box.AcceptsReturn = True
    labels_box.TextWrapping = TextWrapping.Wrap
    labels_box.Height = 130
    labels_box.Padding = Thickness(4)
    labels_box.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    root.Children.Add(labels_box)

    # --- ③ параметр для каждой строки ----------------------------------------
    root.Children.Add(_section(u"③ Параметр модели для каждой строки"))
    root.Children.Add(_hint(
        u"Таблица повторяет список выше. Для каждой строки впишите имя "
        u"параметра в модели (экземпляра или типа), из которого брать значение. "
        u"Пусто — параметр с тем же именем, что и строка."))

    data = List[object]()

    grid = DataGrid()
    grid.Height = 220
    grid.AutoGenerateColumns = False
    grid.CanUserAddRows = False
    grid.CanUserDeleteRows = False
    grid.CanUserResizeRows = False
    grid.CanUserSortColumns = False
    grid.HeadersVisibility = DataGridHeadersVisibility.Column
    grid.GridLinesVisibility = DataGridGridLinesVisibility.Horizontal
    grid.SelectionMode = DataGridSelectionMode.Single
    grid.ItemsSource = data

    label_col = DataGridTextColumn()
    label_col.Header = u"Строка списка"
    label_col.Binding = Binding("Label")
    label_col.IsReadOnly = True
    label_col.Width = _star(1)
    grid.Columns.Add(label_col)

    param_binding = Binding("Param")
    param_binding.Mode = BindingMode.TwoWay
    param_binding.UpdateSourceTrigger = UpdateSourceTrigger.PropertyChanged
    param_col = DataGridTextColumn()
    param_col.Header = u"Параметр в модели"
    param_col.Binding = param_binding
    param_col.Width = _star(1)
    grid.Columns.Add(param_col)

    root.Children.Add(grid)

    def collect_grid():
        try:
            grid.CommitEdit()
        except Exception:
            pass
        for row in data:
            state["map"][row.Label] = unicode(row.Param or u"").strip()

    def refresh_grid():
        collect_grid()
        data.Clear()
        for label in core.parse_labels(labels_box.Text):
            data.Add(_ParamRow(label, state["map"].get(label, u"")))
        grid.ItemsSource = None
        grid.ItemsSource = data

    def on_labels_changed(sender, args):
        refresh_grid()

    refresh_grid()
    labels_box.TextChanged += on_labels_changed

    # --- ④ этаж -------------------------------------------------------------
    root.Children.Add(_section(u"④ Параметр для столбца «Этаж»"))
    floor_box = TextBox()
    floor_box.Text = values.get(FLOOR_KEY, u"")
    floor_box.Padding = Thickness(4)
    root.Children.Add(floor_box)
    root.Children.Add(_hint(
        u"Пусто — параметр из настроек кнопки «Заполнение этажа», а если "
        u"не задан и он — уровень элемента."))

    # --- кнопки ----------------------------------------------------------------
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
        collect_grid()
        labels = core.parse_labels(labels_box.Text)
        result["values"] = {
            CATEGORIES_KEY: list(state["categories"]),
            LABELS_KEY: u"\n".join(labels),
            PARAM_MAP_KEY: core.clean_param_map(labels, state["map"]),
            FLOOR_KEY: floor_box.Text.strip(),
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
        buttons, _read_all, _write_all, u"проверки LOI", _on_settings_imported
    )

    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scroll.Content = root

    outer.Children.Add(buttons)
    outer.Children.Add(scroll)

    win.Content = outer
    win.ShowDialog()

    return result["values"]


def get_settings_interactive(doc):
    """Окно настроек (Shift+клик); сохраняет и возвращает значения, None — отмена."""
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
    """Сохранённые настройки без показа окна."""
    return load_saved_values()
