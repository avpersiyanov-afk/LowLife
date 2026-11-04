# -*- coding: utf-8 -*-
"""Independent linked-view assignments, grouped by host view."""
import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from System.Windows import (Window, WindowStartupLocation, Thickness,
                            GridLength, GridUnitType, HorizontalAlignment,
                            VerticalAlignment, TextWrapping)
from System.Windows.Controls import (DockPanel, Dock, StackPanel, Orientation,
                                     TextBlock, Button, CheckBox, Grid,
                                     ColumnDefinition, RowDefinition,
                                     ScrollViewer, ScrollBarVisibility)
from pyrevit import forms
from lowlife import link_views, select_list
from lowlife.i18n import tr


class _ViewOption(object):
    def __init__(self, view):
        self.view = view
        self.label = link_views.safe_name(view)


def _place(grid, control, row, col):
    Grid.SetRow(control, row)
    Grid.SetColumn(control, col)
    control.Margin = Thickness(4, 6, 8, 6)
    control.VerticalAlignment = VerticalAlignment.Center
    grid.Children.Add(control)


def _text(value):
    block = TextBlock()
    block.Text = value
    block.TextWrapping = TextWrapping.Wrap
    return block


def show(host_views, rows_by_host):
    result = {'choices': None}
    states = []
    win = Window()
    win.Title = tr(u"Виды связанных моделей", u"Linked model views")
    win.Width, win.Height = 1000, 650
    win.MinWidth, win.MinHeight = 700, 400
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen
    outer = DockPanel()
    outer.Margin = Thickness(16)
    header = _text(tr(u"Выбрано видов: {}. Настройте связи отдельно для каждого основного вида. Галочка означает изменение; снятая галочка сохраняет текущее отображение.",
                      u"Selected views: {}. Configure links separately for each host view. Checked links will change; unchecked links keep their current display.").format(len(host_views)))
    header.ToolTip = u'\n'.join(link_views.safe_name(v) for v in host_views)
    header.Margin = Thickness(0, 0, 0, 12)
    DockPanel.SetDock(header, Dock.Top)
    outer.Children.Add(header)

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(0, 12, 0, 0)
    DockPanel.SetDock(buttons, Dock.Bottom)
    outer.Children.Add(buttons)

    grid = Grid()
    for fraction in (4, 3, 4):
        col = ColumnDefinition()
        col.Width = GridLength(fraction, GridUnitType.Star)
        grid.ColumnDefinitions.Add(col)
    grid.RowDefinitions.Add(RowDefinition())
    for col, caption in enumerate((tr(u"Связанная модель", u"Linked model"),
                                   tr(u"Сейчас", u"Current display"),
                                   tr(u"Новый вид", u"New view"))):
        _place(grid, _text(caption), 0, col)

    def picker(state):
        def on_click(sender, args):
            options = [_ViewOption(v) for v in state['row']['views']]
            picked = select_list.SelectFromList.show(
                options, name_attr='label', multiselect=False,
                title=tr(u"Вид связи: {}", u"Linked view: {}").format(state['row']['name']),
                button_name=tr(u"Выбрать", u"Select"), width=650, height=650)
            if picked is not None:
                state['view'] = picked.view
                state['button'].Content = picked.label
                state['button'].ToolTip = picked.label
                state['check'].IsChecked = True
        return on_click

    def copy_picker(source_host):
        def on_click(sender, args):
            source = [s for s in states if s['host'] == source_host
                      and s['check'].IsChecked and s['view'] is not None]
            if not source:
                forms.alert(tr(u"Сначала выберите виды связей в этом блоке.",
                               u"Choose linked views in this section first."), title=win.Title)
                return
            targets = select_list.SelectFromList.show(
                [_ViewOption(v) for v in host_views if v != source_host],
                name_attr='label', multiselect=True,
                title=tr(u"Копировать настройки на виды", u"Copy settings to views"),
                button_name=tr(u"Копировать", u"Copy"))
            for target in targets or []:
                for dest in states:
                    if dest['host'] != target.view or dest['row']['reason']:
                        continue
                    for item in source:
                        if dest['row']['link'].Id == item['row']['link'].Id:
                            dest['view'] = item['view']
                            dest['button'].Content = link_views.safe_name(item['view'])
                            dest['button'].ToolTip = dest['button'].Content
                            dest['check'].IsChecked = True
        return on_click

    entries = []
    for host, rows in zip(host_views, rows_by_host):
        entries.append((host, None))
        entries.extend((host, row) for row in rows)
    for i, (host, row) in enumerate(entries, 1):
        grid.RowDefinitions.Add(RowDefinition())
        if row is None:
            label = _text(link_views.safe_name(host))
            label.FontSize = 16
            _place(grid, label, i, 0)
            Grid.SetColumnSpan(label, 2)
            copy_button = Button()
            copy_button.Content = tr(u"Копировать на другие виды…", u"Copy to other views…")
            copy_button.Padding = Thickness(8, 5, 8, 5)
            copy_button.IsEnabled = len(host_views) > 1
            copy_button.Click += copy_picker(host)
            _place(grid, copy_button, i, 2)
            continue
        check = CheckBox()
        check.Content = _text(row['name'])
        check.IsEnabled = row['reason'] is None
        check.IsChecked = False
        _place(grid, check, i, 0)
        _place(grid, _text(row['current']), i, 1)
        button = Button()
        button.Content = row['reason'] or tr(u"Выбрать вид…", u"Choose view…")
        button.IsEnabled = row['reason'] is None
        button.Padding = Thickness(8, 5, 8, 5)
        _place(grid, button, i, 2)
        state = dict(host=host, row=row, view=None, check=check, button=button)
        states.append(state)
        button.Click += picker(state)

    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scroll.Content = grid
    outer.Children.Add(scroll)

    def on_apply(sender, args):
        chosen = [s for s in states if s['check'].IsChecked]
        if not chosen:
            forms.alert(tr(u"Отметьте хотя бы одну связь.", u"Check at least one link."), title=win.Title)
            return
        missing = [u"{} / {}".format(link_views.safe_name(s['host']), s['row']['name'])
                   for s in chosen if s['view'] is None]
        if missing:
            forms.alert(tr(u"Выберите вид для связей:\n{}", u"Choose a view for these links:\n{}").format(u'\n'.join(missing)), title=win.Title)
            return
        result['choices'] = [(host, [(s['row']['link'], s['view']) for s in chosen
                                     if s['host'] == host]) for host in host_views
                             if any(s['host'] == host for s in chosen)]
        win.Close()

    cancel = Button()
    cancel.Content = tr(u"Отмена", u"Cancel")
    cancel.IsCancel = True
    cancel.Padding = Thickness(14, 5, 14, 5)
    cancel.Click += lambda sender, args: win.Close()
    buttons.Children.Add(cancel)
    apply_button = Button()
    apply_button.Content = tr(u"Применить", u"Apply")
    apply_button.Padding = Thickness(14, 5, 14, 5)
    apply_button.Margin = Thickness(8, 0, 0, 0)
    apply_button.Click += on_apply
    buttons.Children.Add(apply_button)
    win.Content = outer
    win.ShowDialog()
    return result['choices']
