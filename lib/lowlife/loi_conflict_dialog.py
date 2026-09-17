# -*- coding: utf-8 -*-
"""
Окно разрешения конфликтов для кнопки «Заполнение LOI» (LOI.panel).

Показывается только для элементов, попавших сразу в НЕСКОЛЬКО «Форм»
(типичный случай — линейный элемент типа лотка, проходящий через границу
двух форм, см. loi_fill.classify_elements): для каждого такого элемента
пользователь выбирает, из какой конкретно формы брать значения параметров
— клонировать автоматически здесь нечего однозначно.

Строка таблицы — ID (клик по строке подсвечивает/выбирает элемент в
модели), тип элемента, значения-кандидаты по каждой форме и выпадающий
список для выбора формы-источника. Возвращает {ElementId: FormRecord} —
по строкам, где источник выбран (не пропущена).
"""

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System.Collections.Generic import List

from System.Windows import (
    Window, WindowStartupLocation, Thickness, FontWeights,
    HorizontalAlignment, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, TextBlock, Button, Orientation, DockPanel, Dock,
    DataGrid, DataGridTextColumn, DataGridComboBoxColumn, DataGridLength,
    DataGridLengthUnitType, DataGridHeadersVisibility,
    DataGridGridLinesVisibility, DataGridSelectionMode, DataGridSelectionUnit
)
from System.Windows.Data import Binding, BindingMode, UpdateSourceTrigger

from lowlife import loi_fill

from Autodesk.Revit.DB import ElementId


def _star(n):
    return DataGridLength(n, DataGridLengthUnitType.Star)


class _ConflictRow(object):
    def __init__(self, doc, match, param_names):
        self.match = match
        el = match.element

        self.IdText = unicode(el.Id.IntegerValue)
        self.TypeName = loi_fill.element_display_name(doc, el)

        self._forms_by_label = {}
        previews = []
        for form in match.forms:
            self._forms_by_label[form.label] = form
            values = loi_fill.collect_form_values(form.element, param_names)
            previews.append(u"{}: {}".format(form.label, loi_fill.format_values(values, param_names)))

        self.Candidates = List[object]([form.label for form in match.forms])
        self.SelectedCandidate = self.Candidates[0] if self.Candidates.Count > 0 else None
        self.ValuesPreview = u"\n".join(previews)

    def selected_form(self):
        if not self.SelectedCandidate:
            return None
        return self._forms_by_label.get(self.SelectedCandidate)


def show_conflict_dialog(doc, uidoc, matches, param_names):
    """
    matches — список loi_fill.MatchRecord с len(forms) >= 2. Возвращает
    {ElementId: FormRecord} для строк с выбранным источником, либо None,
    если пользователь нажал «Отмена».
    """
    rows = [_ConflictRow(doc, m, param_names) for m in matches]
    data = List[object]()
    for row in rows:
        data.Add(row)

    result = {"mapping": None}

    win = Window()
    win.Title = u"Заполнение LOI — конфликты (элемент в нескольких формах)"
    win.Width = 920
    win.Height = 560
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True
    outer.Margin = Thickness(0)

    header = StackPanel()
    header.Margin = Thickness(16, 12, 16, 8)
    DockPanel.SetDock(header, Dock.Top)

    title = TextBlock()
    title.Text = u"Элементы, найденные сразу в нескольких «Формах»"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    header.Children.Add(title)

    info = TextBlock()
    info.Text = (
        u"Для каждого элемента выберите форму-источник значений в столбце "
        u"«Форма-источник» — значения её параметров ({}) будут записаны в "
        u"этот элемент. Клик по строке выделяет элемент в модели. Строки без "
        u"выбора источника пропускаются.".format(u", ".join(param_names))
    )
    info.FontSize = 11
    info.TextWrapping = TextWrapping.Wrap
    info.Margin = Thickness(0, 4, 0, 0)
    header.Children.Add(info)

    grid = DataGrid()
    grid.Margin = Thickness(16, 0, 16, 0)
    grid.AutoGenerateColumns = False
    grid.CanUserAddRows = False
    grid.CanUserDeleteRows = False
    grid.CanUserResizeRows = False
    grid.HeadersVisibility = DataGridHeadersVisibility.Column
    grid.GridLinesVisibility = DataGridGridLinesVisibility.Horizontal
    grid.SelectionMode = DataGridSelectionMode.Single
    grid.SelectionUnit = DataGridSelectionUnit.FullRow
    grid.IsReadOnly = False
    grid.ItemsSource = data

    id_col = DataGridTextColumn()
    id_col.Header = u"ID"
    id_col.Binding = Binding("IdText")
    id_col.IsReadOnly = True
    id_col.Width = _star(0.5)
    grid.Columns.Add(id_col)

    type_col = DataGridTextColumn()
    type_col.Header = u"Тип элемента"
    type_col.Binding = Binding("TypeName")
    type_col.IsReadOnly = True
    type_col.Width = _star(2)
    grid.Columns.Add(type_col)

    preview_col = DataGridTextColumn()
    preview_col.Header = u"Значения по формам-кандидатам"
    preview_col.Binding = Binding("ValuesPreview")
    preview_col.IsReadOnly = True
    preview_col.Width = _star(3)
    grid.Columns.Add(preview_col)

    source_col = DataGridComboBoxColumn()
    source_col.Header = u"Форма-источник"
    source_col.ItemsSourceBinding = Binding("Candidates")
    selected_binding = Binding("SelectedCandidate")
    selected_binding.Mode = BindingMode.TwoWay
    selected_binding.UpdateSourceTrigger = UpdateSourceTrigger.PropertyChanged
    source_col.SelectedItemBinding = selected_binding
    source_col.Width = _star(2)
    grid.Columns.Add(source_col)

    def on_selection_changed(sender, args):
        try:
            row = grid.SelectedItem
            if row is None:
                return
            ids = List[ElementId]()
            ids.Add(row.match.element.Id)
            uidoc.Selection.SetElementIds(ids)
        except:
            pass

    grid.SelectionChanged += on_selection_changed

    bottom = StackPanel()
    bottom.Margin = Thickness(16, 8, 16, 12)
    bottom.Orientation = Orientation.Horizontal
    bottom.HorizontalAlignment = HorizontalAlignment.Right
    DockPanel.SetDock(bottom, Dock.Bottom)

    cancel_btn = Button()
    cancel_btn.Content = u"Отмена"
    cancel_btn.Padding = Thickness(10, 4, 10, 4)
    cancel_btn.Margin = Thickness(0, 0, 8, 0)

    ok_btn = Button()
    ok_btn.Content = u"Записать значения"
    ok_btn.Padding = Thickness(10, 4, 10, 4)
    ok_btn.FontWeight = FontWeights.Bold

    def on_cancel(sender, args):
        win.Close()

    def on_ok(sender, args):
        try:
            grid.CommitEdit()
        except:
            pass

        mapping = {}
        for row in rows:
            form = row.selected_form()
            if form is not None:
                mapping[row.match.element.Id] = form

        result["mapping"] = mapping
        win.Close()

    ok_btn.Click += on_ok
    cancel_btn.Click += on_cancel

    bottom.Children.Add(cancel_btn)
    bottom.Children.Add(ok_btn)

    outer.Children.Add(header)
    outer.Children.Add(bottom)
    outer.Children.Add(grid)

    win.Content = outer
    win.ShowDialog()

    return result["mapping"]
