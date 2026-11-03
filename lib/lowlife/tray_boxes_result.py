# -*- coding: utf-8 -*-
u"""Окно результата расстановки: выбор добавки и схема отверстия."""

from lowlife.i18n import tr
from lowlife import tray_boxes_core as core


def show(result, clearance_mm, uidoc):
    u"""(нужно применить, добавка в мм); None — автоматический выбор."""
    from pyrevit import forms
    from System.Windows import Thickness, TextWrapping
    from System.Windows.Controls import Canvas, TextBlock
    from System.Windows.Documents import Hyperlink, Run
    from System.Collections.Generic import List
    from Autodesk.Revit.DB import ElementId
    from System.Windows.Media import Brushes, DoubleCollection
    from System.Windows.Shapes import Line, Rectangle

    class ResultWindow(forms.WPFWindow):
        def __init__(self):
            forms.WPFWindow.__init__(self, u'''<Window
                xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
                Width="820" Height="730" MinWidth="760" MinHeight="650"
                WindowStartupLocation="CenterScreen" ResizeMode="CanResize">
              <Grid Margin="20">
                <Grid.RowDefinitions>
                  <RowDefinition Height="Auto"/><RowDefinition Height="Auto"/>
                  <RowDefinition Height="Auto"/><RowDefinition Height="245"/>
                  <RowDefinition Height="Auto"/><RowDefinition Height="*"/>
                  <RowDefinition Height="Auto"/>
                </Grid.RowDefinitions>
                <TextBlock x:Name="summary" TextWrapping="Wrap" Margin="0,0,0,12"/>
                <TextBlock x:Name="prompt" Grid.Row="1" TextWrapping="Wrap" Margin="0,0,0,8"/>
                <ComboBox x:Name="increase" Grid.Row="2" Margin="0,0,0,10"/>
                <Canvas x:Name="diagram" Grid.Row="3" ClipToBounds="True"/>
                <TextBlock x:Name="rules" Grid.Row="4" TextWrapping="Wrap" Margin="0,0,0,10"/>
                <ScrollViewer Grid.Row="5" VerticalScrollBarVisibility="Auto">
                  <StackPanel x:Name="preview"/>
                </ScrollViewer>
                <StackPanel Grid.Row="6" Orientation="Horizontal" HorizontalAlignment="Right" Margin="0,14,0,0">
                  <Button x:Name="apply" MinWidth="160" Padding="12,6" Margin="0,0,10,0"/>
                  <Button x:Name="close" MinWidth="160" Padding="12,6" IsCancel="True"/>
                </StackPanel>
              </Grid>
            </Window>''', literal_string=True)
            self.Title = tr(u"Боксы на лотки — результат", u"Opening boxes for trays — results")
            self.selection = (False, 0)
            self.values = [0, None, 50, 100, 150]
            self.summary.Text = tr(
                u"Поставлено: {}. Уже были: {}. Пропущено: {}. Ошибок: {}.",
                u"Placed: {}. Already present: {}. Skipped: {}. Errors: {}.").format(
                    len(result.created), len(result.existing), len(result.skipped), len(result.failed))
            self.prompt.Text = tr(
                u"Дополнительно увеличить обе стороны новых отверстий на:",
                u"Additionally increase both sides of new openings by:")
            for label in [tr(u"Без увеличения", u"No increase"),
                          tr(u"Автоматически: +50 / +100 / +150 мм", u"Automatic: +50 / +100 / +150 mm"),
                          tr(u"+50 мм", u"+50 mm"), tr(u"+100 мм", u"+100 mm"),
                          tr(u"+150 мм", u"+150 mm")]:
                self.increase.Items.Add(label)
            self.rules.Text = tr(
                u"Авто: большая сторона до 300 мм включительно → +50 мм; свыше 300 до 600 мм включительно → +100 мм; свыше 600 мм → +150 мм. Размер берётся после запасов. Добавка — к каждому из двух размеров, поровну с противоположных сторон. Толщина конструкции не увеличивается.",
                u"Auto: larger side up to 300 mm inclusive → +50 mm; over 300 up to 600 mm inclusive → +100 mm; over 600 mm → +150 mm. Based on the opening including clearances. The increase applies to each of the two dimensions, split equally between opposite sides. Host thickness stays unchanged.")
            self.apply.Content = tr(u"Применить и закрыть", u"Apply and close")
            self.close.Content = tr(u"Оставить как есть", u"Keep as placed")
            self.apply.IsEnabled = not bool(result.missing_params)
            if result.missing_params:
                self.rules.Text += u"\n" + tr(u"Нет параметров: ", u"Missing parameters: ") + u", ".join(sorted(result.missing_params))
            self.increase.SelectionChanged += self.update
            self.increase.SelectedIndex = 0
            self.apply.Click += self.accept
            self.close.Click += lambda s, e: self.Close()

        def amount(self, box):
            value = self.values[self.increase.SelectedIndex]
            return (core.recommended_increase_mm(max(core.opening_sides(box)) * 304.8)
                    if value is None else value)

        def update(self, sender, event):
            self.preview.Children.Clear()
            trays_by_box = {inst.Id: tray for tray, crossing, inst in result.created}
            for inst, box in result.boxes:
                a, b = [v * 304.8 for v in core.opening_sides(box)]
                enlarged = core.enlarge_opening(box, self.amount(box) / 304.8)
                x, y = [v * 304.8 for v in core.opening_sides(enlarged)]
                tray = trays_by_box[inst.Id]
                row = TextBlock()
                row.TextWrapping = TextWrapping.Wrap
                row.Margin = Thickness(0, 0, 0, 10)
                link = Hyperlink()
                link.Inlines.Add(Run(tr(u"Лоток {}", u"Tray {}").format(tray.Id)))
                link.Click += lambda sender, event, eid=tray.Id: uidoc.Selection.SetElementIds(List[ElementId]([eid]))
                row.Inlines.Add(link)
                row.Inlines.Add(Run(tr(u" — сечение {:.0f} × {:.0f} мм\n",
                                      u" — cross-section {:.0f} × {:.0f} mm\n").format(
                                          float(tray.Width * 304.8), float(tray.Height * 304.8))))
                row.Inlines.Add(Run(tr(u"Бокс {}: {:.0f} × {:.0f} → {:.0f} × {:.0f} мм (+{:.0f})",
                                u"Box {}: {:.0f} × {:.0f} → {:.0f} × {:.0f} mm (+{:.0f})").format(
                                    inst.Id, float(a), float(b), float(x), float(y), float(self.amount(box)))))
                self.preview.Children.Add(row)
            self.draw()

        def label(self, x, y, text):
            block = TextBlock()
            block.Text = text
            block.FontSize = 13
            Canvas.SetLeft(block, x)
            Canvas.SetTop(block, y)
            self.diagram.Children.Add(block)

        def line(self, x1, y1, x2, y2):
            line = Line()
            line.X1, line.Y1, line.X2, line.Y2 = x1, y1, x2, y2
            line.Stroke = Brushes.Gray
            line.StrokeThickness = 1
            self.diagram.Children.Add(line)

        def rect(self, x, y, w, h, color, dashed=False):
            rect = Rectangle()
            rect.Width, rect.Height = w, h
            rect.Stroke, rect.StrokeThickness = color, 2
            if dashed:
                rect.StrokeDashArray = DoubleCollection([4.0, 3.0])
            Canvas.SetLeft(rect, x)
            Canvas.SetTop(rect, y)
            self.diagram.Children.Add(rect)

        def draw(self):
            self.diagram.Children.Clear()
            # Схема условная: большая сторона показана горизонтально.
            box = result.boxes[0][1]
            a, b = sorted([v * 304.8 for v in core.opening_sides(box)], reverse=True)
            delta = float(self.amount(box))
            self.rect(85, 65, 280, 105, Brushes.Gray, True)
            self.rect(110, 85, 230, 65, Brushes.Black)
            pad = 20 if delta else 0
            self.rect(85 - pad, 65 - pad, 280 + 2 * pad, 105 + 2 * pad, Brushes.DarkOrange)
            self.label(125, 105, tr(u"Сечение лотка", u"Tray cross-section"))
            self.line(85, 50, 365, 50)
            self.label(95, 28, tr(u"Отверстие A = {:.0f} мм", u"Opening A = {:.0f} mm").format(float(a)))
            self.line(85 - pad, 195, 365 + pad, 195)
            self.label(75, 202, tr(u"A + Δ = {:.0f} + {:.0f} = {:.0f} мм",
                                 u"A + Δ = {:.0f} + {:.0f} = {:.0f} mm").format(float(a), delta, float(a + delta)))
            self.label(410, 48, tr(u"Серый пунктир — исходное отверстие", u"Gray dashed — original opening"))
            self.label(410, 78, tr(u"Оранжевый — после увеличения", u"Orange — enlarged opening"))
            self.label(410, 108, tr(u"Запас s = {:.0f} мм с каждой стороны", u"Clearance s = {:.0f} mm on each side").format(float(clearance_mm)))
            self.label(410, 138, tr(u"Дополнительно Δ/2 = {:.0f} мм с двух сторон", u"Additional Δ/2 = {:.0f} mm at both ends").format(delta / 2.0))
            self.label(410, 168, tr(u"B + Δ = {:.0f} + {:.0f} = {:.0f} мм", u"B + Δ = {:.0f} + {:.0f} = {:.0f} mm").format(float(b), delta, float(b + delta)))
            self.label(65, 5, tr(u"Схема первого нового отверстия (условно)", u"First new opening (schematic)"))

        def accept(self, sender, event):
            self.selection = (True, self.values[self.increase.SelectedIndex])
            self.Close()

    window = ResultWindow()
    window.ShowDialog()
    return window.selection
