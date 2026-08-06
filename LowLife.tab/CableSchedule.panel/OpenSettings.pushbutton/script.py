# -*- coding: utf-8 -*-

__title__ = "Настройки\nплагина"
__doc__ = "Настройка параметров проекта, используемых при формировании журнала цепей."
__author__ = "Pipers"

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('RevitAPI')

from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory
from Autodesk.Revit.DB.Electrical import ElectricalSystem

from pyrevit import revit

from System.Windows import (
    Window, WindowStartupLocation, Thickness, GridLength, GridUnitType,
    HorizontalAlignment, VerticalAlignment, FontWeights, ResizeMode
)
from System.Windows.Controls import (
    Grid, RowDefinition, ColumnDefinition, Label, ComboBox, TextBlock,
    StackPanel, Button, Orientation
)
from System.Windows.Data import CollectionViewSource
from System.Windows.Input import Key

from lowlife.cable_schedule import load_settings, save_settings

doc = revit.doc


def collect_circuit_param_names():
    names = set()
    circuits = FilteredElementCollector(doc) \
        .OfCategory(BuiltInCategory.OST_ElectricalCircuit) \
        .WhereElementIsNotElementType() \
        .ToElements()

    for circuit in list(circuits)[:50]:
        for p in circuit.Parameters:
            name = p.Definition.Name if p.Definition else None
            if name and name.strip():
                names.add(name)

    return sorted(names)


class SettingsWindow(Window):

    def __init__(self, settings, all_params):
        self._settings = settings
        self._last_filter_text = ""

        source = sorted(all_params, key=lambda p: p.lower())
        self._view = CollectionViewSource.GetDefaultView(source)

        grid = Grid()
        grid.Margin = Thickness(14)
        grid.RowDefinitions.Add(RowDefinition(Height=GridLength.Auto))
        grid.RowDefinitions.Add(RowDefinition(Height=GridLength(10)))
        grid.RowDefinitions.Add(RowDefinition(Height=GridLength.Auto))
        grid.RowDefinitions.Add(RowDefinition(Height=GridLength(14)))
        grid.RowDefinitions.Add(RowDefinition(Height=GridLength.Auto))

        title = TextBlock()
        title.Text = u"Настройка параметров цепей"
        title.FontWeight = FontWeights.SemiBold
        title.FontSize = 13
        Grid.SetRow(title, 0)
        grid.Children.Add(title)

        row = Grid()
        row.ColumnDefinitions.Add(ColumnDefinition(Width=GridLength(190)))
        row.ColumnDefinitions.Add(ColumnDefinition(Width=GridLength(1, GridUnitType.Star)))

        label = Label()
        label.Content = u"Марка кабеля, провода:"
        label.VerticalAlignment = VerticalAlignment.Center
        label.Padding = Thickness(0, 0, 8, 0)
        Grid.SetColumn(label, 0)
        row.Children.Add(label)

        self._combo = ComboBox()
        self._combo.IsEditable = True
        self._combo.IsTextSearchEnabled = False
        self._combo.StaysOpenOnEdit = True
        self._combo.ItemsSource = self._view
        self._combo.Text = settings["cable_mark_parameter"]
        self._combo.VerticalAlignment = VerticalAlignment.Center
        self._combo.KeyUp += self._on_key_up
        Grid.SetColumn(self._combo, 1)
        row.Children.Add(self._combo)

        Grid.SetRow(row, 2)
        grid.Children.Add(row)

        buttons = StackPanel()
        buttons.Orientation = Orientation.Horizontal
        buttons.HorizontalAlignment = HorizontalAlignment.Right

        save_btn = Button()
        save_btn.Content = u"Сохранить"
        save_btn.Width = 100
        save_btn.Margin = Thickness(0, 0, 8, 0)
        save_btn.IsDefault = True
        save_btn.Click += self._on_save
        buttons.Children.Add(save_btn)

        cancel_btn = Button()
        cancel_btn.Content = u"Отмена"
        cancel_btn.Width = 80
        cancel_btn.IsCancel = True
        buttons.Children.Add(cancel_btn)

        Grid.SetRow(buttons, 4)
        grid.Children.Add(buttons)

        self.Title = u"Настройки плагина — Кабельный журнал"
        self.Width = 530
        self.Height = 160
        self.ResizeMode = ResizeMode.NoResize
        self.WindowStartupLocation = WindowStartupLocation.CenterScreen
        self.Content = grid

    def _on_key_up(self, sender, e):
        if e.Key in (Key.Down, Key.Up, Key.Return, Key.Escape):
            return

        text = self._combo.Text
        if text == self._last_filter_text:
            return
        self._last_filter_text = text

        if text:
            self._view.Filter = lambda item: text.lower() in item.lower()
        else:
            self._view.Filter = None

        self._combo.Text = text
        self._combo.IsDropDownOpen = any(True for _ in self._view)

    def _on_save(self, sender, e):
        self._settings["cable_mark_parameter"] = self._combo.Text
        self.DialogResult = True


settings = load_settings()
param_names = collect_circuit_param_names()

window = SettingsWindow(settings, param_names)
if window.ShowDialog():
    save_settings(settings)
