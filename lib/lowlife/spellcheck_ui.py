# -*- coding: utf-8 -*-
"""Two-column spelling review. WPF is loaded only when opening the dialog."""
from lowlife.i18n import tr
from lowlife import spellcheck_core as core


def review(proposals, targets):
    """Return checked proposals, or None on Cancel/window close."""
    from pyrevit import forms
    from System.Windows import Thickness, TextWrapping, FontWeights
    from System.Windows.Controls import Grid, TextBlock, CheckBox
    from System.Windows.Documents import Run
    from System.Windows.Media import Brushes
    from System.Windows.Markup import XamlReader

    class ReviewWindow(forms.WPFWindow):
        def __init__(self):
            forms.WPFWindow.__init__(self, u'''<Window
                xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
                Width="1180" Height="740" MinWidth="760" MinHeight="420"
                WindowStartupLocation="CenterScreen" ResizeMode="CanResize">
              <Grid Margin="16">
                <Grid.RowDefinitions>
                  <RowDefinition Height="Auto"/><RowDefinition Height="Auto"/>
                  <RowDefinition Height="*"/><RowDefinition Height="Auto"/>
                </Grid.RowDefinitions>
                <DockPanel Margin="0,0,0,12">
                  <CheckBox x:Name="toggle" IsThreeState="True" VerticalAlignment="Center"/>
                  <TextBlock x:Name="summary" HorizontalAlignment="Right"/>
                </DockPanel>
                <Grid Grid.Row="1" Margin="0,0,20,0" Background="#F1F3F5">
                  <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="38"/><ColumnDefinition Width="*"/>
                    <ColumnDefinition Width="*"/>
                  </Grid.ColumnDefinitions>
                  <TextBlock x:Name="before_title" Grid.Column="1" Margin="10" FontWeight="Bold"/>
                  <TextBlock x:Name="after_title" Grid.Column="2" Margin="10" FontWeight="Bold"/>
                </Grid>
                <ListBox x:Name="rows" Grid.Row="2" BorderBrush="#D7DBDF"
                         ScrollViewer.HorizontalScrollBarVisibility="Disabled"
                         ScrollViewer.VerticalScrollBarVisibility="Auto"
                         HorizontalContentAlignment="Stretch"
                         VirtualizingStackPanel.IsVirtualizing="True">
                  <ListBox.ItemContainerStyle>
                    <Style TargetType="ListBoxItem">
                      <Setter Property="HorizontalContentAlignment" Value="Stretch"/>
                      <Setter Property="Padding" Value="0"/>
                      <Setter Property="Margin" Value="0"/>
                      <Setter Property="Focusable" Value="False"/>
                      <Setter Property="Template">
                        <Setter.Value><ControlTemplate TargetType="ListBoxItem">
                          <Border BorderBrush="#E3E6E9" BorderThickness="0,0,0,1">
                            <ContentPresenter/>
                          </Border>
                        </ControlTemplate></Setter.Value>
                      </Setter>
                    </Style>
                  </ListBox.ItemContainerStyle>
                </ListBox>
                <StackPanel Grid.Row="3" Orientation="Horizontal" HorizontalAlignment="Right" Margin="0,14,0,0">
                  <Button x:Name="apply" IsDefault="True" Padding="18,8" Margin="0,0,10,0"/>
                  <Button x:Name="cancel" IsCancel="True" Padding="18,8"/>
                </StackPanel>
              </Grid>
            </Window>''', literal_string=True)
            self.Title = tr(u"Проверка орфографии — исправления", u"Spell check — corrections")
            self.before_title.Text = tr(u"Было — ошибка выделена красным", u"Before — errors in red")
            self.after_title.Text = tr(u"Как будет", u"After")
            self.toggle.Content = tr(u"Выбрать все", u"Select all")
            self.apply.Content = tr(u"Исправить отмеченные")
            self.cancel.Content = tr(u"Отмена")
            self.result = None
            self.checks = []
            self.updating = False
            for proposal in proposals:
                self.add_row(proposal)
            self.toggle.Click += self.toggle_all
            self.apply.Click += self.accept
            self.cancel.Click += lambda sender, event: self.Close()
            self.update_selection()

        def add_row(self, proposal):
            row = XamlReader.Parse(u'''<Grid xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">
                <Grid.ColumnDefinitions><ColumnDefinition Width="38"/>
                  <ColumnDefinition Width="*"/><ColumnDefinition Width="*"/>
                </Grid.ColumnDefinitions>
                <Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/>
                </Grid.RowDefinitions>
              </Grid>''')
            check = CheckBox()
            check.IsChecked = True
            check.Margin = Thickness(12, 14, 6, 0)
            check.ToolTip = tr(u"Применить это исправление", u"Apply this correction")
            check.Checked += self.update_selection
            check.Unchecked += self.update_selection
            row.Children.Add(check)
            self.checks.append((check, proposal))
            before, after = core.comparison_runs(proposal['item']['text'], proposal['new_body'])
            for column, runs, color in ((1, before, Brushes.Firebrick), (2, after, Brushes.DarkGreen)):
                block = TextBlock()
                block.TextWrapping = TextWrapping.Wrap
                block.FontSize = 14
                block.Margin = Thickness(10, 10, 16, 6)
                for text, changed in runs:
                    run = Run(text)
                    if changed:
                        run.Foreground = color
                        run.FontWeight = FontWeights.SemiBold
                    block.Inlines.Add(run)
                Grid.SetColumn(block, column)
                row.Children.Add(block)
            source = TextBlock()
            source.Text = tr(u"Источников: {}", u"Sources: {}").format(len(proposal['item']['notes']))
            labels = [targets[index].label for index, old in proposal['item']['notes']]
            if labels:
                source.Text += u" — " + labels[0]
            source.ToolTip = u"\n".join(labels)
            source.TextWrapping = TextWrapping.Wrap
            source.Foreground = Brushes.DimGray
            source.FontSize = 11
            source.Margin = Thickness(10, 0, 16, 10)
            Grid.SetRow(source, 1)
            Grid.SetColumn(source, 1)
            Grid.SetColumnSpan(source, 2)
            row.Children.Add(source)
            self.rows.Items.Add(row)

        def update_selection(self, sender=None, event=None):
            if self.updating:
                return
            count = sum(1 for check, proposal in self.checks if check.IsChecked)
            self.summary.Text = tr(u"Отмечено: {} из {}", u"Selected: {} of {}").format(count, len(self.checks))
            self.toggle.IsChecked = True if count == len(self.checks) else (False if count == 0 else None)

        def toggle_all(self, sender, event):
            value = not all(check.IsChecked for check, proposal in self.checks)
            self.updating = True
            try:
                for check, proposal in self.checks:
                    check.IsChecked = value
            finally:
                self.updating = False
            self.update_selection()

        def accept(self, sender, event):
            self.result = [proposal for check, proposal in self.checks if check.IsChecked]
            self.Close()

    window = ReviewWindow()
    window.ShowDialog()
    return window.result
