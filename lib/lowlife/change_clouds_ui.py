# -*- coding: utf-8 -*-
"""Окно кнопки «Внесение изменений» (Tools.panel/ChangeClouds): все изменения
в проекте (типы семейства облака с шифром/номером/датой и числом вставленных
экземпляров) + кнопки «Новое изменение» и «Настройки».

Возвращает строку-действие: "new" — начать создание изменения, "settings" —
открыть настройки, None — окно закрыто; (u"instance", symbol_id) — двойной
клик по строке: вставить ещё один экземпляр этого типа.
"""

from lowlife.i18n import tr


def show_changes_window(family_name, rows):
    """Показать окно. family_name может быть None (семейство не настроено/не
    загружено) — окно тогда показывает подсказку вместо списка."""
    from pyrevit import forms
    from System.Windows import Visibility
    from System.Windows.Controls import ListView, GridView, GridViewColumn
    from System.Windows.Data import Binding

    class ChangesWindow(forms.WPFWindow):
        def __init__(self):
            forms.WPFWindow.__init__(self, u'''<Window
                xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
                Width="760" Height="520" MinWidth="560" MinHeight="360"
                WindowStartupLocation="CenterScreen" ResizeMode="CanResize">
              <Grid Margin="16">
                <Grid.RowDefinitions>
                  <RowDefinition Height="Auto"/><RowDefinition Height="*"/>
                  <RowDefinition Height="Auto"/><RowDefinition Height="Auto"/>
                </Grid.RowDefinitions>
                <TextBlock x:Name="heading" FontSize="16" FontWeight="Bold" Margin="0,0,0,10"/>
                <TextBlock x:Name="empty" Grid.Row="1" TextWrapping="Wrap" VerticalAlignment="Center"/>
                <ListView x:Name="rows" Grid.Row="1" BorderBrush="#D7DBDF">
                  <ListView.View>
                    <GridView>
                      <GridViewColumn x:Name="col_type"/>
                      <GridViewColumn x:Name="col_cipher"/>
                      <GridViewColumn x:Name="col_number"/>
                      <GridViewColumn x:Name="col_date"/>
                      <GridViewColumn x:Name="col_placed"/>
                    </GridView>
                  </ListView.View>
                </ListView>
                <TextBlock x:Name="hint" Grid.Row="2" FontSize="11" Foreground="Gray"
                           TextWrapping="Wrap" Margin="0,8,0,0"/>
                <StackPanel Grid.Row="3" Orientation="Horizontal" HorizontalAlignment="Right" Margin="0,14,0,0">
                  <Button x:Name="settings" Padding="18,8" Margin="0,0,10,0"/>
                  <Button x:Name="create" IsDefault="True" Padding="18,8" Margin="0,0,10,0"/>
                  <Button x:Name="close" IsCancel="True" Padding="18,8"/>
                </StackPanel>
              </Grid>
            </Window>''', literal_string=True)
            self.Title = tr(u"Внесение изменений", u"Enter changes")
            self.heading.Text = tr(u"Изменения в проекте: {}", u"Changes in model: {}").format(
                family_name or tr(u"семейство не задано", u"no family set"))
            self.col_type.Header = tr(u"Тип", u"Type")
            self.col_cipher.Header = tr(u"Шифр", u"Cipher")
            self.col_number.Header = tr(u"Номер", u"Number")
            self.col_date.Header = tr(u"Дата", u"Date")
            self.col_placed.Header = tr(u"Вставлено", u"Placed")
            for column, attr in ((self.col_type, u"type"), (self.col_cipher, u"cipher"),
                                 (self.col_number, u"number"), (self.col_date, u"date"),
                                 (self.col_placed, u"placed")):
                column.DisplayMemberBinding = Binding(attr)
            self.settings.Content = tr(u"Настройки", u"Settings")
            self.create.Content = tr(u"Новое изменение", u"New change")
            self.close.Content = tr(u"Закрыть", u"Close")
            self.hint.Text = tr(
                u"Двойной клик по строке — вставить ещё один экземпляр этого типа "
                u"(код и содержание спросит, шифр/номер/дата — из типа).",
                u"Double-click a row to place another instance of that type "
                u"(asks for the code and content; cipher/number/date come from the type).")
            self.result = None

            if not rows:
                self.rows.Visibility = Visibility.Collapsed
                self.hint.Visibility = Visibility.Collapsed
                self.empty.Text = tr(
                    u"Изменений пока нет. Нажмите «Новое изменение», чтобы создать первый тип.",
                    u"No changes yet. Click “New change” to create the first type.")
                if family_name is None:
                    self.empty.Text = tr(
                        u"Семейство облака изменений не задано в настройках или не загружено в проект.",
                        u"The change cloud family is not set in the settings or not loaded in the model.")
            else:
                self.empty.Visibility = Visibility.Collapsed
                for row in rows:
                    self.rows.Items.Add(_RowItem(row))

            self.settings.Click += self._settings
            self.create.Click += self._create
            self.rows.MouseDoubleClick += self._row_double_click
            self.close.Click += lambda sender, event: self.Close()

        def _settings(self, sender, event):
            self.result = u"settings"
            self.Close()

        def _create(self, sender, event):
            self.result = u"new"
            self.Close()

        def _row_double_click(self, sender, event):
            from System.Windows.Controls import ListViewItem
            from System.Windows.Media import Visual, VisualTreeHelper
            # клик по строке, а не по заголовку колонки/пустому месту
            node = event.OriginalSource
            while node is not None and not isinstance(node, ListViewItem):
                if not isinstance(node, Visual):
                    node = getattr(node, "Parent", None)
                    continue
                node = VisualTreeHelper.GetParent(node)
            if node is None:
                return
            self.result = (u"instance", node.Content.symbol_id)
            self.Close()

    class _RowItem(object):
        """Обёртка строки для GridView (DisplayMemberBinding по атрибутам)."""
        def __init__(self, row):
            self.type = row.get(u"name") or u""
            self.cipher = row.get(u"cipher") or u""
            self.number = u"{}".format(row.get(u"number") or u"")
            self.date = row.get(u"date") or u""
            self.placed = u"{}".format(row.get(u"placed") if row.get(u"placed") is not None else u"")
            self.symbol_id = row.get(u"symbol_id")

    window = ChangesWindow()
    window.ShowDialog()
    return window.result
