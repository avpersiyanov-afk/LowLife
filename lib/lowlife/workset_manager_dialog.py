# -*- coding: utf-8 -*-
"""Rule editor and concrete preview; Revit work runs after modal dialogs close."""
import clr
clr.AddReference('PresentationFramework')
from System.Windows import Thickness, Visibility, Window, WindowStartupLocation
from System.Windows.Controls import (Button, ComboBox, Dock, DockPanel, Grid,
    ColumnDefinition, ScrollViewer, ScrollBarVisibility,
    StackPanel, Orientation, TextBlock, TextBox)
from System.Windows import GridLength, GridUnitType, TextWrapping
from pyrevit import forms
from lowlife import select_list, settings_transfer, text_search
from lowlife import model_filter_settings as cfg
from lowlife import workset_manager, workset_manager_core as core
from lowlife.i18n import N_, tr

LABELS = [N_(u'Создать'), N_(u'Переименовать'), N_(u'Перенести элементы')]


def _button(panel, caption, handler):
    button = Button()
    button.Content = tr(caption)
    button.Padding = Thickness(8, 4, 8, 4)
    button.Margin = Thickness(0, 3, 6, 3)
    button.Click += handler
    panel.Children.Add(button)
    return button


def _window(title):
    win = Window()
    win.Title = tr(title)
    win.Width, win.Height = 1000, 740
    win.MinWidth, win.MinHeight = 780, 500
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen
    outer = DockPanel()
    outer.Margin = Thickness(14)
    win.Content = outer
    return win, outer


def _rule_grid():
    grid = Grid()
    for width in (160, 1, 1, 40):
        column = ColumnDefinition()
        column.Width = GridLength(width, GridUnitType.Star if width == 1 else GridUnitType.Pixel)
        grid.ColumnDefinitions.Add(column)
    return grid


def edit(rules, names, linked_names):
    win, outer = _window(N_(u'Управление рабочими наборами'))
    result, rows = {}, []
    header = TextBlock()
    header.Text = tr(u'Правила выполняются сверху вниз. Источник — маска полного имени (*, ?, {часть}). Назначение: {1} — исходное имя, {2} — первая часть маски. Перенос создаёт недостающий набор, исходный набор остаётся. Изменения действуют на весь проект.')
    header.TextWrapping = TextWrapping.Wrap
    DockPanel.SetDock(header, Dock.Top)
    outer.Children.Add(header)
    search_label = TextBlock()
    search_label.Text = tr(u'Поиск по правилу или рабочему набору')
    search_label.Margin = Thickness(0, 8, 0, 0)
    DockPanel.SetDock(search_label, Dock.Top)
    outer.Children.Add(search_label)
    search = TextBox()
    search.ToolTip = tr(u'Поиск по правилу или рабочему набору')
    search.Margin = Thickness(0, 8, 0, 6)
    DockPanel.SetDock(search, Dock.Top)
    outer.Children.Add(search)
    tools = StackPanel()
    tools.Orientation = Orientation.Horizontal
    DockPanel.SetDock(tools, Dock.Top)
    outer.Children.Add(tools)
    columns = _rule_grid()
    for index, caption in enumerate((N_(u'Действие'), N_(u'Маска источника'), N_(u'Имя назначения'))):
        label = TextBlock()
        label.Text = tr(caption)
        label.Margin = Thickness(0, 8, 6, 4)
        Grid.SetColumn(label, index)
        columns.Children.Add(label)
    DockPanel.SetDock(columns, Dock.Top)
    outer.Children.Add(columns)
    footer = StackPanel()
    footer.Orientation = Orientation.Horizontal
    DockPanel.SetDock(footer, Dock.Bottom)
    outer.Children.Add(footer)
    status = TextBlock()
    status.TextWrapping = TextWrapping.Wrap
    DockPanel.SetDock(status, Dock.Bottom)
    outer.Children.Add(status)
    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    content = StackPanel()
    scroll.Content = content
    outer.Children.Add(scroll)

    def filter_rows(sender=None, args=None):
        for row in rows:
            text = row['source'].Text + u' ' + row['target'].Text
            row['panel'].Visibility = Visibility.Visible if text_search.matches(text, search.Text) else Visibility.Collapsed

    def add(rule):
        grid = _rule_grid()
        action = ComboBox()
        for label in LABELS:
            action.Items.Add(tr(label))
        action.SelectedIndex = core.ACTIONS.index(rule['action'])
        source, target = TextBox(), TextBox()
        source.Text, target.Text = rule['source'], rule['target']
        source.ToolTip = tr(u'Маска исходного рабочего набора; для создания оставьте пустой')
        target.ToolTip = tr(u'Имя рабочего набора назначения')
        remove = Button()
        remove.Content = u'×'
        remove.ToolTip = tr(u'Удалить правило')
        row = dict(panel=grid, action=action, source=source, target=target)
        for index, control in enumerate((action, source, target, remove)):
            control.Margin = Thickness(0, 4, 6, 4)
            control.MinHeight = 28
            Grid.SetColumn(control, index)
            grid.Children.Add(control)
        def delete(sender, args):
            content.Children.Remove(grid)
            rows.remove(row)
        remove.Click += delete
        source.TextChanged += filter_rows
        target.TextChanged += filter_rows
        rows.append(row)
        content.Children.Add(grid)
        filter_rows()

    def read_rules():
        # Search only hides rows; all rules retain their order and are saved/applied.
        return core.normalize_rules([dict(action=core.ACTIONS[row['action'].SelectedIndex],
            source=row['source'].Text, target=row['target'].Text) for row in rows])

    def save(sender, args):
        try:
            cfg.SETTINGS.store.update({core.RULES_KEY: read_rules()})
            status.Text = tr(u'Правила сохранены.')
        except Exception as exc:
            status.Text = tr(u'Ошибка: {0}').format(exc)

    def accept(sender, args):
        try:
            result['rules'] = read_rules()
            win.Close()
        except Exception as exc:
            status.Text = tr(u'Ошибка: {0}').format(exc)

    def from_model(sender, args):
        chosen = select_list.SelectFromList.show(names, multiselect=True,
            title=N_(u'Рабочие наборы'), button_name=N_(u'Добавить'))
        for name in chosen or []:
            add(dict(action='rename', source=name, target=name))

    def from_links(sender, args):
        chosen = select_list.SelectFromList.show(sorted(linked_names), multiselect=True,
            title=N_(u'Создать рабочие наборы из связей'), button_name=N_(u'Добавить'))
        for name in chosen or []:
            add(dict(action='create', source=u'', target=linked_names[name]))

    def reload():
        result['reload'] = True
        win.Close()

    def export_rules():
        return {core.RULES_KEY: read_rules()}

    def import_rules(data):
        cfg.SETTINGS.store.update({core.RULES_KEY: core.normalize_rules(data.get(core.RULES_KEY))})

    _button(tools, N_(u'Новое правило'), lambda sender, args: add(dict(action='create', source=u'', target=u'')))
    _button(tools, N_(u'Из текущей модели…'), from_model)
    _button(tools, N_(u'Из связей…'), from_links)
    _button(tools, N_(u'Сохранить правила'), save)
    _button(footer, N_(u'Предварительный просмотр…'), accept)
    close = _button(footer, N_(u'Отмена'), lambda sender, args: win.Close())
    close.IsCancel = True
    # Reuse common JSON import/export. Invalid imported rules never replace settings.
    settings_transfer.add_transfer_buttons(footer, export_rules, import_rules,
                                          N_(u'правил рабочих наборов'), reload)
    for rule in rules:
        add(rule)
    search.TextChanged += filter_rows
    win.ShowDialog()
    return result


def confirm(preview):
    win, outer = _window(N_(u'План изменений рабочих наборов'))
    result = {'apply': False}
    footer = StackPanel()
    footer.Orientation = Orientation.Horizontal
    DockPanel.SetDock(footer, Dock.Bottom)
    outer.Children.Add(footer)
    text = TextBox()
    text.IsReadOnly = True
    text.TextWrapping = TextWrapping.Wrap
    text.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    lines = []
    for op in preview['operations']:
        label = tr(LABELS[core.ACTIONS.index(op['action'])])
        line = u'{0}: {1} → {2}'.format(label, op['source'], op['target'])
        if op['action'] == 'map':
            line += tr(u' (элементов: {0})').format(len(op['elements']))
        lines.append(line)
    text.Text = u'\n'.join(lines) or tr(u'Изменений нет.')
    outer.Children.Add(text)
    def apply(sender, args):
        result['apply'] = True
        win.Close()
    _button(footer, N_(u'Применить к проекту'), apply)
    back = _button(footer, N_(u'Вернуться к правилам'), lambda sender, args: win.Close())
    back.IsCancel = True
    win.ShowDialog()
    return result['apply']


def run(doc):
    from lowlife.cable_tray import find_worksets
    from lowlife.link_worksets import collect_rows

    workset_manager.available(doc)
    rules = cfg.SETTINGS.store.read().get(core.RULES_KEY, [])
    while True:
        names = sorted(w.Name for w in find_worksets(doc, u''))
        linked_names = dict((row['name'] + u' — ' + w['name'], w['name'])
                            for row in collect_rows(doc) for w in row['worksets'])
        result = edit(rules, names, linked_names)
        if result.get('reload'):
            rules = cfg.SETTINGS.store.read().get(core.RULES_KEY, [])
            continue
        if 'rules' not in result:
            return
        rules = result['rules']
        try:
            preview = workset_manager.prepare(doc, rules)
            if not confirm(preview):
                continue
            count = workset_manager.apply(doc, preview)
            cfg.SETTINGS.store.update({core.RULES_KEY: rules})
            forms.alert(tr(u'Выполнено операций: {0}.').format(count))
            return
        except Exception as exc:
            forms.alert(tr(u'Ошибка: {0}').format(exc))
