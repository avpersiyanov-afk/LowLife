# -*- coding: utf-8 -*-
"""One modal window for loaded models and their workset loading state."""
import clr
clr.AddReference('PresentationFramework')
from System.Windows import Window, Thickness, WindowStartupLocation, TextWrapping, Visibility
from System.Windows.Controls import (DockPanel, Dock, StackPanel, Orientation,
                                     TextBlock, TextBox, Button, CheckBox,
                                     ScrollViewer, ScrollBarVisibility, GroupBox)
from lowlife import text_search
from lowlife.i18n import tr


def show(rows):
    result = {'choices': None}
    states = []
    win = Window()
    win.Title = tr(u'Рабочие наборы связей', u'Linked worksets')
    win.Width, win.Height = 850, 680
    win.MinWidth, win.MinHeight = 620, 400
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen
    outer = DockPanel()
    outer.Margin = Thickness(16)
    win.Content = outer

    header = TextBlock()
    header.Text = tr(
        u'Флажок = рабочий набор открыт. Изменения действуют на все экземпляры связи во всём проекте. '
        u'Применение перезагрузит изменённые связи и очистит историю отмены Revit. Файлы связанных моделей не сохраняются.',
        u'Checked = workset open. Changes affect all link instances throughout this project. '
        u'Apply reloads changed links and clears Revit Undo history. Linked model files are not saved.')
    header.TextWrapping = TextWrapping.Wrap
    header.Margin = Thickness(0, 0, 0, 12)
    DockPanel.SetDock(header, Dock.Top)
    outer.Children.Add(header)
    search_label = TextBlock()
    search_label.Text = tr(u'Поиск по модели или рабочему набору', u'Search models or worksets')
    DockPanel.SetDock(search_label, Dock.Top)
    outer.Children.Add(search_label)
    search = TextBox()
    search.ToolTip = tr(u'Поиск по модели или рабочему набору', u'Search models or worksets')
    search.Margin = Thickness(0, 0, 0, 10)
    DockPanel.SetDock(search, Dock.Top)
    outer.Children.Add(search)

    footer = StackPanel()
    footer.Orientation = Orientation.Horizontal
    DockPanel.SetDock(footer, Dock.Bottom)
    outer.Children.Add(footer)
    content = StackPanel()
    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scroll.Content = content
    outer.Children.Add(scroll)

    def set_group(checks, value):
        def clicked(sender, args):
            for check, workset in checks:
                if check.Visibility == Visibility.Visible:
                    check.IsChecked = value
        return clicked

    for row in rows:
        group = GroupBox()
        model_label = TextBlock()
        model_label.Text = u'{} ({})'.format(row['name'], row['instances'])
        group.Header = model_label
        group.Margin = Thickness(0, 0, 0, 10)
        panel = StackPanel()
        panel.Margin = Thickness(8)
        group.Content = panel
        content.Children.Add(group)
        checks = []
        state = dict(row=row, group=group, checks=checks)
        states.append(state)
        if row['reason']:
            note = TextBlock()
            note.Text = row['reason']
            note.TextWrapping = TextWrapping.Wrap
            panel.Children.Add(note)
        else:
            actions = StackPanel()
            actions.Orientation = Orientation.Horizontal
            panel.Children.Add(actions)
            for caption, value in ((tr(u'Открыть все', u'Open all'), True),
                                   (tr(u'Закрыть все', u'Close all'), False)):
                button = Button()
                button.Content = caption
                button.Margin = Thickness(0, 0, 8, 6)
                button.Padding = Thickness(10, 4, 10, 4)
                button.Click += set_group(checks, value)
                actions.Children.Add(button)
        for workset in row['worksets']:
            check = CheckBox()
            workset_label = TextBlock()
            workset_label.Text = workset['name']
            check.Content = workset_label
            check.ToolTip = workset['name']
            check.IsChecked = workset['opened']
            check.IsEnabled = not bool(row['reason'])
            check.Margin = Thickness(2, 4, 2, 4)
            panel.Children.Add(check)
            checks.append((check, workset))

    def filter_rows(sender, args):
        for state in states:
            any_match = False
            for check, workset in state['checks']:
                visible = text_search.matches(u'{} {}'.format(state['row']['name'], workset['name']), search.Text)
                check.Visibility = Visibility.Visible if visible else Visibility.Collapsed
                any_match = any_match or visible
            visible = any_match or text_search.matches(state['row']['name'], search.Text)
            state['group'].Visibility = Visibility.Visible if visible else Visibility.Collapsed

    def accept(sender, args):
        result['choices'] = [(s['row'], [w['id'] for check, w in s['checks'] if check.IsChecked])
                             for s in states if not s['row']['reason']]
        win.Close()

    search.TextChanged += filter_rows
    for caption, handler in ((tr(u'Применить', u'Apply'), accept),
                             (tr(u'Отмена', u'Cancel'), lambda sender, args: win.Close())):
        button = Button()
        button.Content = caption
        button.Margin = Thickness(0, 10, 8, 0)
        button.Padding = Thickness(16, 6, 16, 6)
        button.Click += handler
        footer.Children.Add(button)
    button.IsCancel = True
    win.ShowDialog()
    return result['choices']
