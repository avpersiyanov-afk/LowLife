# -*- coding: utf-8 -*-
"""Missing datums and target system family types/worksets in one window."""
import clr
clr.AddReference('PresentationFramework')
from System.Windows import Window, Thickness, WindowStartupLocation, TextWrapping, Visibility
from System.Windows.Controls import (DockPanel, Dock, StackPanel, Orientation,
                                     TextBlock, TextBox, Button, CheckBox, ComboBox,
                                     ScrollViewer, ScrollBarVisibility, GroupBox)
from Autodesk.Revit import DB
from pyrevit import forms
from lowlife import text_search
from lowlife.i18n import tr
from lowlife.link_datums_copy import missing_rows
from lowlife.link_views import safe_name
from lowlife.cable_tray import find_worksets


def show(doc, levels, grids):
    result = {'choices': None}
    states = []
    win = Window()
    win.Title = tr(u'Недостающие уровни и оси', u'Missing levels and grids')
    win.Width, win.Height = 760, 760
    win.MinWidth, win.MinHeight = 580, 400
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen
    outer = DockPanel()
    outer.Margin = Thickness(16)
    win.Content = outer
    note = TextBlock()
    note.Text = tr(
        u'Для выбранных уровней создаётся 3D-вид, для осей — план. На видах остаются только выбранные элементы связи. '
        u'Откроется штатное Копирование/Мониторинг Revit. Выберите связь: «Копировать» и «Несколько» включатся автоматически. '
        u'Выделите отмеченные элементы рамкой, при необходимости используйте фильтр, затем нажмите «Готово» в строке параметров и на ленте. После завершения к новым '
        u'копиям со штатным мониторингом будут применены выбранные типы, рабочие наборы и закрепление. '
        u'Выбор в этом списке не автоматизирует щелчки по элементам на виде.',
        u'A 3D view is created for selected levels and a plan for grids. Only the selected linked datums remain visible. '
        u'Native Revit Copy/Monitor will open. Select the link: Copy and Multiple will be enabled automatically. Select the checked elements with a rectangle, use the filter if needed, '
        u'then click Finish on the options bar and ribbon. Selected types, worksets and pinning will be applied to new '
        u'copies with native monitoring. Selection in this list does not automate view picks.')
    note.TextWrapping = TextWrapping.Wrap
    note.Margin = Thickness(0, 0, 0, 12)
    DockPanel.SetDock(note, Dock.Top)
    outer.Children.Add(note)
    search = TextBox()
    search.ToolTip = tr(u'Поиск', u'Search')
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
    missing = missing_rows(levels, grids)
    worksets = sorted(find_worksets(doc, u''), key=lambda w: w.Name.lower()) if doc.IsWorkshared else []

    for kind, caption, type_class in (
            ('level', tr(u'Уровни', u'Levels'), DB.LevelType),
            ('grid', tr(u'Оси', u'Grids'), DB.GridType)):
        rows = [row for row_kind, row in missing if row_kind == kind]
        if not rows:
            continue
        types = sorted(DB.FilteredElementCollector(doc).OfClass(type_class), key=safe_name)
        group = GroupBox()
        group.Header = caption
        group.Margin = Thickness(0, 0, 0, 12)
        panel = StackPanel()
        panel.Margin = Thickness(8)
        group.Content = panel
        content.Children.Add(group)
        combos = []
        for label, objects, names in (
                (tr(u'Тип семейства', u'Family type'), types, [safe_name(t) for t in types]),
                (tr(u'Рабочий набор', u'Workset'), worksets, [w.Name for w in worksets])):
            text = TextBlock()
            text.Text = label
            panel.Children.Add(text)
            combo = ComboBox()
            combo.Margin = Thickness(0, 4, 0, 8)
            for name in names:
                item = TextBlock()
                item.Text = name
                combo.Items.Add(item)
            if objects:
                combo.SelectedIndex = 0
            else:
                item = TextBlock()
                item.Text = tr(u'Недоступно', u'Unavailable')
                combo.Items.Add(item)
                combo.SelectedIndex = 0
                combo.IsEnabled = False
            panel.Children.Add(combo)
            combos.append(combo)
        if worksets:
            active = doc.GetWorksetTable().GetActiveWorksetId()
            for index, workset in enumerate(worksets):
                if workset.Id == active:
                    combos[1].SelectedIndex = index
        checks = []
        for row in rows:
            check = CheckBox()
            label = TextBlock()
            label.Text = u'{} [{}]'.format(row.link['name'], row.link['id_int'])
            check.Content = label
            check.IsChecked = False
            check.Margin = Thickness(0, 5, 0, 5)
            panel.Children.Add(check)
            checks.append((check, row))
        states.append((kind, types, combos, checks))

    def filter_rows(sender, args):
        for kind, types, combos, checks in states:
            for check, row in checks:
                check.Visibility = (Visibility.Visible if text_search.matches(row.link['name'], search.Text)
                                    else Visibility.Collapsed)

    def accept(sender, args):
        choices = []
        for kind, types, combos, checks in states:
            chosen = [row for check, row in checks if check.IsChecked]
            if not chosen:
                continue
            if not types or (doc.IsWorkshared and not worksets):
                forms.alert(tr(u'Выберите доступный тип и рабочий набор.',
                               u'Select an available type and workset.'))
                return
            workset_id = worksets[combos[1].SelectedIndex].Id if worksets else None
            choices.extend((kind, row, types[combos[0].SelectedIndex], workset_id) for row in chosen)
        if not choices:
            forms.alert(tr(u'Выберите хотя бы один элемент.', u'Select at least one element.'))
            return
        result['choices'] = choices
        win.Close()

    search.TextChanged += filter_rows
    for caption, handler in ((tr(u'Открыть Копирование/Мониторинг', u'Open Copy/Monitor'), accept),
                             (tr(u'Закрыть', u'Close'), lambda sender, args: win.Close())):
        button = Button()
        button.Content = caption
        button.Margin = Thickness(0, 10, 8, 0)
        button.Padding = Thickness(16, 6, 16, 6)
        button.Click += handler
        footer.Children.Add(button)
    button.IsCancel = True
    win.ShowDialog()
    return result['choices']
