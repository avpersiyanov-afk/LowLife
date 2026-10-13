# -*- coding: utf-8 -*-
"""
Окно кнопки «Виды по уровням» (Tools.panel/LevelViews): маска имени вида,
список шаблонов видов планов (галочка «создать» + своё «Значение» у
каждого) и предпросмотр имён на первом уровне. Логика имён —
level_views_core, создание видов — level_views.
"""

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from pyrevit import forms

from lowlife import level_views, level_views_core as core

from System.Windows import (
    Window, WindowStartupLocation, Thickness, FontWeights,
    HorizontalAlignment, VerticalAlignment, TextWrapping, GridLength,
    GridUnitType
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, Orientation, CheckBox, DockPanel,
    Dock, Grid, ColumnDefinition, RowDefinition, ScrollViewer,
    ScrollBarVisibility
)
from System.Windows.Media import Brushes

TITLE = u"Виды по уровням"
_PREVIEW_MAX = 8


def _hint(parent, text, top=2):
    tb = TextBlock()
    tb.Text = text
    tb.FontSize = 11
    tb.Foreground = Brushes.Gray
    tb.TextWrapping = TextWrapping.Wrap
    tb.Margin = Thickness(0, top, 0, 0)
    parent.Children.Add(tb)
    return tb


def _place(grid, element, row, col):
    Grid.SetRow(element, row)
    Grid.SetColumn(element, col)
    grid.Children.Add(element)


def _button(parent, text, handler, bold=False):
    b = Button()
    b.Content = text
    b.Padding = Thickness(10, 4, 10, 4)
    b.Margin = Thickness(8, 0, 0, 0)
    if bold:
        b.FontWeight = FontWeights.Bold
    b.Click += handler
    parent.Children.Add(b)
    return b


class _Row(object):
    def __init__(self, template, check, value_box):
        self.template = template
        self.name = level_views.safe_name(template)
        self.check = check
        self.value_box = value_box

    def checked(self):
        return bool(self.check.IsChecked)

    def value(self):
        return unicode(self.value_box.Text or u"").strip()


def show(doc, templates, levels, settings, level_template):
    """
    Окно. Возвращает (маска, [(шаблон, значение)], {шаблон: значение})
    или None при отмене.
    """
    saved_values = settings[core.VALUES_KEY]
    checked = set(settings[core.CHECKED_KEY])
    first_values = level_views.level_values(levels[0], level_template) if levels else {}
    result = {"value": None}

    win = Window()
    win.Title = TITLE
    win.Width = 760
    win.Height = 720
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.Margin = Thickness(16, 12, 16, 12)

    # --- шапка: маска -------------------------------------------------------------
    header = StackPanel()
    DockPanel.SetDock(header, Dock.Top)
    title = TextBlock()
    title.Text = TITLE
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    header.Children.Add(title)
    _hint(header, u"Для каждого отмеченного шаблона вида создаётся план на каждом уровне "
                  u"модели (уровней: {}) с этим шаблоном. Вид с таким же именем на том же "
                  u"уровне не создаётся заново — ему назначается шаблон.".format(len(levels)))

    mask_label = TextBlock()
    mask_label.Text = u"Маска имени вида"
    mask_label.FontWeight = FontWeights.Bold
    mask_label.Margin = Thickness(0, 12, 0, 2)
    header.Children.Add(mask_label)
    mask_box = TextBox()
    mask_box.Padding = Thickness(4)
    mask_box.Text = settings[core.MASK_KEY]
    header.Children.Add(mask_box)
    _hint(header, u"Подстановки: {Уровень} — имя уровня; {Значение} — значение шаблона из "
                  u"списка ниже; {Шаблон} — имя шаблона; {Отметка} — «+3.300»; {Этаж}, "
                  u"{Корпус}, {Комментарий} — части имени уровня по шаблону из настроек "
                  u"«Секущего диапазона». Например «{Уровень}_{Значение}» или "
                  u"«{Этаж} этаж. {Значение}».")
    outer.Children.Add(header)

    # --- низ: предпросмотр и кнопки -----------------------------------------------
    bottom = StackPanel()
    DockPanel.SetDock(bottom, Dock.Bottom)
    preview_title = TextBlock()
    preview_title.FontWeight = FontWeights.Bold
    preview_title.Margin = Thickness(0, 10, 0, 2)
    bottom.Children.Add(preview_title)
    preview = TextBlock()
    preview.TextWrapping = TextWrapping.Wrap
    bottom.Children.Add(preview)

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(0, 12, 0, 0)
    bottom.Children.Add(buttons)
    outer.Children.Add(bottom)

    # --- середина: шаблоны ---------------------------------------------------------
    middle = DockPanel()
    middle.Margin = Thickness(0, 12, 0, 0)

    list_head = DockPanel()
    DockPanel.SetDock(list_head, Dock.Top)
    list_title = TextBlock()
    list_title.Text = u"Шаблоны видов и их значения"
    list_title.FontWeight = FontWeights.Bold
    list_title.VerticalAlignment = VerticalAlignment.Center
    list_head.Children.Add(list_title)
    select_buttons = StackPanel()
    select_buttons.Orientation = Orientation.Horizontal
    select_buttons.HorizontalAlignment = HorizontalAlignment.Right
    list_head.Children.Add(select_buttons)
    middle.Children.Add(list_head)

    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scroll.Margin = Thickness(0, 6, 0, 0)
    grid = Grid()
    scroll.Content = grid
    middle.Children.Add(scroll)
    outer.Children.Add(middle)

    for width in (GridLength(1, GridUnitType.Star), GridLength(150),
                  GridLength(1, GridUnitType.Star)):
        col = ColumnDefinition()
        col.Width = width
        grid.ColumnDefinitions.Add(col)

    grid.RowDefinitions.Add(RowDefinition())
    for col, text in enumerate((u"Шаблон вида", u"Вид", u"Значение")):
        head = TextBlock()
        head.Text = text
        head.Foreground = Brushes.Gray
        head.Margin = Thickness(0, 0, 8, 4)
        _place(grid, head, 0, col)

    rows = []
    for i, template in enumerate(templates):
        grid.RowDefinitions.Add(RowDefinition())
        name = level_views.safe_name(template)
        check = CheckBox()
        check.Content = name
        check.IsChecked = name in checked
        check.VerticalAlignment = VerticalAlignment.Center
        check.Margin = Thickness(0, 3, 8, 3)
        _place(grid, check, i + 1, 0)
        kind = TextBlock()
        kind.Text = level_views.KIND_LABELS.get(template.ViewType, u"")
        kind.Foreground = Brushes.Gray
        kind.VerticalAlignment = VerticalAlignment.Center
        kind.Margin = Thickness(0, 3, 8, 3)
        _place(grid, kind, i + 1, 1)
        value_box = TextBox()
        value_box.Padding = Thickness(3)
        value_box.Margin = Thickness(0, 3, 0, 3)
        value_box.Text = saved_values.get(name, name)
        _place(grid, value_box, i + 1, 2)
        rows.append(_Row(template, check, value_box))

    def chosen():
        return [r for r in rows if r.checked()]

    def update_preview(*_args):
        mask = mask_box.Text
        picked = chosen()
        error = core.validate_mask(mask)
        if error:
            preview_title.Text = u"Маска: " + error
            preview_title.Foreground = Brushes.Firebrick
            preview.Text = u""
            return
        preview_title.Foreground = Brushes.Black
        if not picked:
            preview_title.Text = u"Отметьте шаблоны, для которых создавать виды."
            preview.Text = u""
            return
        preview_title.Text = u"Будет видов: {} ({} шабл. × {} ур.). Имена на уровне «{}»:".format(
            len(picked) * len(levels), len(picked), len(levels),
            first_values.get(core.TOKEN_LEVEL, u""))
        lines = [u"• " + core.build_view_name(mask, first_values, r.name, r.value())
                 for r in picked[:_PREVIEW_MAX]]
        if len(picked) > _PREVIEW_MAX:
            lines.append(u"… и ещё {}".format(len(picked) - _PREVIEW_MAX))
        warning = core.mask_warning(mask, len(picked))
        if warning:
            lines.append(u"Внимание: " + warning)
        preview.Text = u"\n".join(lines)

    mask_box.TextChanged += update_preview
    for r in rows:
        r.check.Checked += update_preview
        r.check.Unchecked += update_preview
        r.value_box.TextChanged += update_preview

    def set_all(flag):
        def handler(sender, args):
            for r in rows:
                r.check.IsChecked = flag
        return handler

    _button(select_buttons, u"Отметить все", set_all(True))
    _button(select_buttons, u"Снять все", set_all(False))

    def on_ok(sender, args):
        mask = mask_box.Text
        error = core.validate_mask(mask)
        if error:
            forms.alert(u"Маска имени вида: " + error, title=TITLE)
            return
        picked = chosen()
        if not picked:
            forms.alert(u"Отметьте хотя бы один шаблон вида.", title=TITLE)
            return
        values = dict((r.name, r.value()) for r in rows)
        result["value"] = (mask, [(r.template, r.value()) for r in picked], values)
        win.Close()

    _button(buttons, u"Отмена", lambda s, a: win.Close())
    _button(buttons, u"Создать виды", on_ok, bold=True)

    update_preview()
    win.Content = outer
    win.ShowDialog()
    return result["value"]
