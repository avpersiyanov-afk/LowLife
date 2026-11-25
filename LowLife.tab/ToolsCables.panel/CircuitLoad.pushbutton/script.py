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
        xaml = u'''<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" Title="Нагрузка электрических цепей" Width="1100" Height="700" WindowStartupLocation="CenterScreen"><Grid Margin="12"><Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions><StackPanel Orientation="Horizontal"><TextBlock Text="Фильтр:" VerticalAlignment="Center" Margin="0,0,8,0"/><TextBox x:Name="filter" Width="360" Height="26"/><TextBlock x:Name="count" Margin="16,4,0,0"/></StackPanel><ListView x:Name="circuits" Grid.Row="1" Margin="0,10,0,8"><ListView.View><GridView><GridViewColumn Header="Цепь" DisplayMemberBinding="{Binding Number}" Width="110"/><GridViewColumn Header="Панель" DisplayMemberBinding="{Binding Panel}" Width="180"/><GridViewColumn Header="Имя" DisplayMemberBinding="{Binding Name}" Width="220"/><GridViewColumn Header="Оборудование" DisplayMemberBinding="{Binding EquipmentCount}" Width="110"/><GridViewColumn Header="Типы оборудования" DisplayMemberBinding="{Binding EquipmentTypes}" Width="380"/></GridView></ListView.View></ListView><ListView x:Name="equipment" Grid.Row="2"><ListView.View><GridView><GridViewColumn Header="Категория" DisplayMemberBinding="{Binding category}" Width="220"/><GridViewColumn Header="Тип" DisplayMemberBinding="{Binding type}" Width="300"/><GridViewColumn Header="Имя" DisplayMemberBinding="{Binding name}" Width="300"/><GridViewColumn Header="ID" DisplayMemberBinding="{Binding id}" Width="100"/></GridView></ListView.View></ListView><Button Grid.Row="3" Content="Закрыть" Width="100" Height="28" HorizontalAlignment="Right" Click="close_click"/></Grid></Window>'''
        forms.WPFWindow.__init__(self, xaml, literal_string=True)
        self.rows = rows
        self.filter.TextChanged += self.filter_changed
        self.circuits.SelectionChanged += self.circuit_selected
        self.refresh()
    def refresh(self, sender=None, args=None):
        query = self.filter.Text.lower()
        visible = []
        for row in self.rows:
            text = u" ".join((row["number"], row["panel"], row["name"], u" ".join(e["category"] + u" " + e["type"] for e in row["equipment"]))).lower()
            if not query or query in text:
                visible.append(_Row(row))
        self.circuits.ItemsSource = visible
        self.count.Text = u"Показано: {} из {}".format(len(visible), len(self.rows))
    filter_changed = refresh
    def circuit_selected(self, sender, args):
        item = self.circuits.SelectedItem
        self.equipment.ItemsSource = item.row["equipment"] if item else []
    def close_click(self, sender, args):
        self.Close()

class _Row(object):
    def __init__(self, row):
        self.row = row
        self.Number = row["number"] or str(row["id"])
        self.Panel = row["panel"]
        self.Name = row["name"]
        self.EquipmentCount = row["element_count"]
        types = {}
        for item in row["equipment"]:
            key = item["category"] + (u" / " + item["type"] if item["type"] else u"")
            types[key] = types.get(key, 0) + 1
        self.EquipmentTypes = u", ".join(k + u" (" + str(v) + u")" for k, v in sorted(types.items()))

CircuitWindow(records).ShowDialog()
