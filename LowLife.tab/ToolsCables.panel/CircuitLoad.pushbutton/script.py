# -*- coding: utf-8 -*-
from pyrevit import revit, forms, EXEC_PARAMS, script
from Autodesk.Revit.DB import FilteredElementCollector
from Autodesk.Revit.DB.Electrical import ElectricalSystem
from lowlife import circuit_load

__title__ = u"Нагрузка\nцепей"
__doc__ = u"Интерактивный просмотр цепей и подключённого оборудования."
if EXEC_PARAMS.config_mode:
    forms.alert(u"Настройки нагрузки будут добавлены после выбора параметров кабельных линий.")
    script.exit()

systems = list(FilteredElementCollector(revit.doc).OfClass(ElectricalSystem).WhereElementIsNotElementType())
records = [circuit_load.circuit_record(system, {"section_mm2": 2.5}) for system in systems]

class CircuitWindow(forms.WPFWindow):
    def __init__(self, rows):
        xaml = u'''<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Title="Нагрузка электрических цепей" Width="1300" Height="760" WindowStartupLocation="CenterScreen"><Grid Margin="12"><Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions><StackPanel Orientation="Horizontal"><TextBlock Text="Фильтр:" VerticalAlignment="Center" Margin="0,0,8,0"/><TextBox x:Name="filter" Width="360" Height="26"/><Button Content="Обновить из модели" Margin="12,0,0,0" Click="refresh_click"/><TextBlock x:Name="count" Margin="16,4,0,0"/></StackPanel><ListView x:Name="circuits" Grid.Row="1" Margin="0,10,0,8"><ListView.View><GridView><GridViewColumn Header="Цепь" DisplayMemberBinding="{Binding Number}" Width="90"/><GridViewColumn Header="Панель" DisplayMemberBinding="{Binding Panel}" Width="160"/><GridViewColumn Header="Оборудование" DisplayMemberBinding="{Binding EquipmentCount}" Width="90"/><GridViewColumn Header="U, V" DisplayMemberBinding="{Binding Voltage}" Width="70"/><GridViewColumn Header="I, A" DisplayMemberBinding="{Binding Current}" Width="70"/><GridViewColumn Header="Проводник" DisplayMemberBinding="{Binding Conductor}" Width="180"/><GridViewColumn Header="Падение" DisplayMemberBinding="{Binding Drop}" Width="100"/><GridViewColumn Header="Типы оборудования" DisplayMemberBinding="{Binding EquipmentTypes}" Width="420"/></GridView></ListView.View></ListView><ListView x:Name="equipment" Grid.Row="2"><ListView.View><GridView><GridViewColumn Header="Категория" DisplayMemberBinding="{Binding Category}" Width="220"/><GridViewColumn Header="Тип" DisplayMemberBinding="{Binding Type}" Width="300"/><GridViewColumn Header="U, V" DisplayMemberBinding="{Binding Voltage}" Width="70"/><GridViewColumn Header="I, A" DisplayMemberBinding="{Binding Current}" Width="70"/><GridViewColumn Header="P, W" DisplayMemberBinding="{Binding Power}" Width="70"/><GridViewColumn Header="Имя" DisplayMemberBinding="{Binding Name}" Width="280"/></GridView></ListView.View></ListView><Button Grid.Row="3" Content="Закрыть" Width="100" Height="28" HorizontalAlignment="Right" Click="close_click"/></Grid></Window>'''
        forms.WPFWindow.__init__(self, xaml, literal_string=True)
        self.rows = rows
        self.filter.TextChanged += self.filter_changed
        self.circuits.SelectionChanged += self.circuit_selected
        self.refresh()
    def refresh(self, sender=None, args=None):
        query = self.filter.Text
        visible = []
        for row in circuit_load.filter_records(self.rows, query):
            visible.append(_Row(row))
        self.circuits.ItemsSource = visible
        self.count.Text = u"Показано: {} из {}".format(len(visible), len(self.rows))
    filter_changed = refresh
    def circuit_selected(self, sender, args):
        item = self.circuits.SelectedItem
        self.equipment.ItemsSource = circuit_load.equipment_rows(item.row) if item else []
    def close_click(self, sender, args):
        self.Close()
    def refresh_click(self, sender, args):
        self.refresh()

class _Row(object):
    def __init__(self, row):
        self.row = row
        self.Number = row["number"] or str(row["id"])
        self.Panel = row["panel"]
        self.Name = row["name"]
        self.EquipmentCount = row["element_count"]
        self.EquipmentTypes = circuit_load.equipment_type_summary(row["equipment"])
        self.Voltage = "{:.1f}".format(row["voltage_v"]) if row["voltage_v"] is not None else u"—"
        self.Current = "{:.2f}".format(row["current_a"]) if row["current_a"] is not None else u"—"
        conductor = row["conductor"]
        self.Conductor = conductor["label"] or u"—"
        self.Drop = "{:.2f}%".format(row["voltage_drop_pct"]) if row["voltage_drop_pct"] is not None else u"—"

CircuitWindow(records).ShowDialog()


