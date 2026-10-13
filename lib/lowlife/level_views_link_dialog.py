# -*- coding: utf-8 -*-
"""
Окно выбора видов связанных моделей для «Видов по уровням» — открывается
перед созданием видов, если у выбранных групп включены связи «По
связанному виду» и галочка «Показывать окно выбора» (без неё виды связей
подбираются молча, тем же подбором).

На каждую такую группу — вкладка: сверху фильтр видов связи (вид фильтра
level_views_core.LINK_VIEW_MODES + значение, начальные — из настроек
группы), ниже таблица «уровень × связь»: в каждой ячейке список планов
связи под фильтр. Подставлено заранее: выбранное в прошлый раз, иначе план
на «таком же» уровне связи (level_views_core.pick_link_view). «<Не задавать>» — связь на этом виде не
трогается. Изменённый фильтр сохраняется в настройки группы, выбор — как
подстановка для следующего раза.
"""

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from pyrevit import forms

from lowlife import geometry, level_views, level_views_core as core

from System.Windows import (
    Window, WindowStartupLocation, Thickness, FontWeights,
    HorizontalAlignment, VerticalAlignment, TextWrapping, GridLength,
    GridUnitType
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, Orientation, ComboBox, DockPanel,
    Dock, Grid, ColumnDefinition, RowDefinition, ScrollViewer,
    ScrollBarVisibility, TabControl, TabItem
)
from System.Windows.Media import Brushes

TITLE = u"Виды по уровням — виды связей"
NOT_SET = u"<Не задавать>"


def _hint(parent, text):
    tb = TextBlock()
    tb.Text = text
    tb.FontSize = 11
    tb.Foreground = Brushes.Gray
    tb.TextWrapping = TextWrapping.Wrap
    tb.Margin = Thickness(0, 2, 0, 0)
    parent.Children.Add(tb)
    return tb


def _cell(grid, element, row, col):
    Grid.SetRow(element, row)
    Grid.SetColumn(element, col)
    grid.Children.Add(element)


class _Cell(object):
    """Список выбора вида одной связи для одного уровня."""

    def __init__(self, level, level_z, level_key, values, link, combo):
        self.level = level
        self.level_key = level_key
        self.level_name = geometry.level_name(level)
        self.level_z = level_z
        self.values = values
        self.link = link
        self.combo = combo
        self.candidates = []

    def selected(self):
        item = self.combo.SelectedItem
        if item is None or unicode(item) == NOT_SET:
            return u""
        return unicode(item)

    def fill(self, candidates, prefer):
        """prefer — имя вида, "" — «не задавать», None — подобрать (pick_link_view)."""
        self.candidates = candidates
        self.combo.Items.Clear()
        self.combo.Items.Add(NOT_SET)
        for c in candidates:
            self.combo.Items.Add(c[0])
        if prefer == u"":
            self.combo.SelectedIndex = 0
            return
        picked = core.default_link_view(candidates, self.level_z, prefer,
                                        self.level_name, self.level_key)
        names = [c[0] for c in candidates]
        self.combo.SelectedIndex = names.index(picked[0]) + 1 if picked is not None else 0


class _GroupTab(object):
    def __init__(self, ctx, group, levels, remembered):
        self.ctx = ctx
        self.group = group
        self.cells = []
        self.view_type = level_views.group_view_type(ctx, group)[1]
        self.links = level_views.group_links(ctx, group)

        self.tab = TabItem()
        self.tab.Header = group[core.G_NAME]
        root = DockPanel()
        root.Margin = Thickness(8)
        self.tab.Content = root

        top = StackPanel()
        DockPanel.SetDock(top, Dock.Top)
        root.Children.Add(top)

        row = StackPanel()
        row.Orientation = Orientation.Horizontal
        label = TextBlock()
        label.Text = u"Фильтр видов связи:"
        label.VerticalAlignment = VerticalAlignment.Center
        label.Margin = Thickness(0, 0, 8, 0)
        row.Children.Add(label)
        self.mode_cb = ComboBox()
        self.mode_cb.Width = 190
        for _key, lbl in core.LINK_VIEW_MODES:
            self.mode_cb.Items.Add(lbl)
        self.mode_cb.SelectedItem = core.mode_label(group[core.G_LINK_VIEW_MODE])
        row.Children.Add(self.mode_cb)
        self.value_box = TextBox()
        self.value_box.Width = 300
        self.value_box.Margin = Thickness(8, 0, 0, 0)
        self.value_box.Padding = Thickness(4)
        self.value_box.Text = group[core.G_LINK_VIEW_FILTER]
        row.Children.Add(self.value_box)
        auto_btn = Button()
        auto_btn.Content = u"Подобрать заново"
        auto_btn.Padding = Thickness(10, 2, 10, 2)
        auto_btn.Margin = Thickness(8, 0, 0, 0)
        auto_btn.Click += lambda s, a: self.refill(auto=True)
        row.Children.Add(auto_btn)
        top.Children.Add(row)
        _hint(top, u"Несколько значений — через запятую (подходит любое; для «Не содержит» — "
                   u"ни одно). Регистр не важен. Можно с подстановками уровня: {Этаж}, "
                   u"{Корпус}, {Уровень}, {Отметка}, {Комментарий} — тогда у каждого уровня "
                   u"свой список. Пусто — все планы связи. В списке — только планы того же "
                   u"типа (план этажа / потолка), что и создаваемый вид.")
        self.status = _hint(top, u"")
        self.status.Margin = Thickness(0, 4, 0, 6)

        if not self.links:
            msg = TextBlock()
            msg.Text = (u"Нет загруженных связей" + (
                u" с «{}» в имени".format(group[core.G_LINK_FILTER])
                if group[core.G_LINK_FILTER] else u"") + u" — связи на этих видах не трогаются.")
            msg.Foreground = Brushes.Firebrick
            msg.TextWrapping = TextWrapping.Wrap
            root.Children.Add(msg)
            return

        scroll = ScrollViewer()
        scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
        scroll.HorizontalScrollBarVisibility = ScrollBarVisibility.Auto
        root.Children.Add(scroll)

        grid = Grid()
        scroll.Content = grid
        first = ColumnDefinition()
        first.Width = GridLength(1, GridUnitType.Auto)
        grid.ColumnDefinitions.Add(first)
        for _link in self.links:
            col = ColumnDefinition()
            col.Width = GridLength(1, GridUnitType.Star)
            col.MinWidth = 220
            grid.ColumnDefinitions.Add(col)

        grid.RowDefinitions.Add(RowDefinition())
        head = TextBlock()
        head.Text = u"Уровень"
        head.FontWeight = FontWeights.Bold
        head.Margin = Thickness(0, 0, 12, 4)
        _cell(grid, head, 0, 0)
        for j, link in enumerate(self.links):
            tb = TextBlock()
            tb.Text = link.name
            tb.FontWeight = FontWeights.Bold
            tb.TextWrapping = TextWrapping.Wrap
            tb.Margin = Thickness(0, 0, 8, 4)
            _cell(grid, tb, 0, j + 1)

        group_memory = remembered.get(group[core.G_NAME]) or {}
        self._remembered = group_memory
        for i, level in enumerate(levels):
            grid.RowDefinitions.Add(RowDefinition())
            name = TextBlock()
            name.Text = geometry.level_name(level)
            name.VerticalAlignment = VerticalAlignment.Center
            name.Margin = Thickness(0, 2, 12, 2)
            _cell(grid, name, i + 1, 0)
            values = level_views.level_values(level, ctx.level_template)
            z = level.ProjectElevation * core.MM_IN_FOOT
            key = level_views.level_match_key(level, ctx.level_template)
            for j, link in enumerate(self.links):
                combo = ComboBox()
                combo.Margin = Thickness(0, 2, 8, 2)
                _cell(grid, combo, i + 1, j + 1)
                self.cells.append(_Cell(level, z, key, values, link, combo))

        self.refill(initial=True)
        self.mode_cb.SelectionChanged += lambda s, a: self.refill()
        self.value_box.TextChanged += lambda s, a: self.refill()

    def mode(self):
        return core.mode_by_label(unicode(self.mode_cb.SelectedItem or u""))

    def value(self):
        return unicode(self.value_box.Text or u"")

    def error(self):
        return core.validate_link_view_filter(self.mode(), self.value())

    def refill(self, initial=False, auto=False):
        error = self.error()
        if error:
            self.status.Text = u"Фильтр: " + error
            self.status.Foreground = Brushes.Firebrick
            return
        mode, value = self.mode(), self.value()
        empty = 0
        for cell in self.cells:
            candidates = core.filter_link_views(
                cell.link.plans(self.view_type), mode,
                core.apply_mask(value, cell.values).strip())
            if auto:
                prefer = None
            elif initial:
                prefer = (self._remembered.get(cell.link.name) or {}).get(cell.level_name)
            else:
                prefer = cell.selected() if cell.combo.SelectedIndex > 0 else None
            cell.fill(candidates, prefer)
            if not candidates:
                empty += 1
        text = u""
        if u"{" not in value:
            text = u"Планов под фильтр: " + u", ".join(
                u"«{}» — {}".format(link.name, len(core.filter_link_views(
                    link.plans(self.view_type), mode, value.strip())))
                for link in self.links)
        if empty:
            text += (u"; " if text else u"") + u"у {} ячеек список пуст".format(empty)
        self.status.Text = text
        self.status.Foreground = Brushes.Gray

    def choices(self):
        """{имя связи: {имя уровня: имя вида или ""}}."""
        result = {}
        for cell in self.cells:
            result.setdefault(cell.link.name, {})[cell.level_name] = cell.selected()
        return result


def show(ctx, levels, groups, remembered):
    """
    Окно выбора. Возвращает (choices, filters) — choices: {группа: {связь:
    {уровень: вид или ""}}}, filters: {группа: (вид фильтра, значение)} —
    или None при отмене. Групп со связями нет — ({}, {}) без окна.
    """
    link_groups = [g for g in groups if g[core.G_LINKS] and g[core.G_LINK_PICK_DIALOG]]
    if not link_groups or not ctx.links_supported:
        return {}, {}
    levels = sorted(levels, key=lambda l: l.ProjectElevation)

    result = {"value": None}
    win = Window()
    win.Title = TITLE
    win.Width = 1000
    win.Height = 700
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.Margin = Thickness(16, 12, 16, 12)

    header = StackPanel()
    DockPanel.SetDock(header, Dock.Top)
    title = TextBlock()
    title.Text = u"По какому виду связи показывать связанные модели"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    header.Children.Add(title)
    _hint(header, u"Для каждого уровня и каждой связи выберите план связи — он станет "
                  u"«связанным видом» в настройке «Связи RVT» создаваемого вида. Заранее "
                  u"подставлено выбранное в прошлый раз, иначе план на таком же уровне связи: "
                  u"с тем же именем, иначе тот же этаж, иначе ближайший по отметке.")
    outer.Children.Add(header)

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(0, 12, 0, 0)
    DockPanel.SetDock(buttons, Dock.Bottom)
    outer.Children.Add(buttons)

    tabs_control = TabControl()
    tabs_control.Margin = Thickness(0, 10, 0, 0)
    tabs = [_GroupTab(ctx, g, levels, remembered) for g in link_groups]
    for t in tabs:
        tabs_control.Items.Add(t.tab)
    outer.Children.Add(tabs_control)

    def on_ok(sender, args):
        for t in tabs:
            error = t.error()
            if error:
                tabs_control.SelectedItem = t.tab
                forms.alert(u"Группа «{}», фильтр видов связи: {}".format(
                    t.group[core.G_NAME], error), title=TITLE)
                return
        choices = {}
        filters = {}
        for t in tabs:
            name = t.group[core.G_NAME]
            choices[name] = t.choices()
            filters[name] = (t.mode(), t.value().strip())
        result["value"] = (choices, filters)
        win.Close()

    def on_cancel(sender, args):
        win.Close()

    for text, handler, bold in ((u"Отмена", on_cancel, False),
                                (u"Создать виды", on_ok, True)):
        b = Button()
        b.Content = text
        b.Padding = Thickness(10, 4, 10, 4)
        b.Margin = Thickness(8, 0, 0, 0)
        if bold:
            b.FontWeight = FontWeights.Bold
        b.Click += handler
        buttons.Children.Add(b)

    win.Content = outer
    win.ShowDialog()
    return result["value"]
