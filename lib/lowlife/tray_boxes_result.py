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
                Width="860" Height="850" MinWidth="780" MinHeight="780"
                WindowStartupLocation="CenterScreen" ResizeMode="CanResize">
              <Grid Margin="20">
                <Grid.RowDefinitions>
                  <RowDefinition Height="Auto"/><RowDefinition Height="Auto"/>
                  <RowDefinition Height="Auto"/><RowDefinition Height="350"/>
                  <RowDefinition Height="Auto"/><RowDefinition Height="*"/>
                  <RowDefinition Height="Auto"/>
                </Grid.RowDefinitions>
                <TextBlock x:Name="summary" TextWrapping="Wrap" Margin="0,0,0,12"/>
                <TextBlock x:Name="prompt" Grid.Row="1" TextWrapping="Wrap" Margin="0,0,0,8"/>
                <ComboBox x:Name="increase" Grid.Row="2" Margin="0,0,0,10"/>
                <Viewbox Grid.Row="3" Margin="0,12,0,16" Stretch="Uniform">
                  <Canvas x:Name="diagram" Width="780" Height="340"/>
                </Viewbox>
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
                u"Дополнительно по ЗНП увеличить оба размера отверстия на:",
                u"Additionally per ZNP, increase both opening dimensions by:")
            for label in [tr(u"Без увеличения", u"No increase"),
                          tr(u"Автоматически: +50 / +100 / +150 мм", u"Automatic: +50 / +100 / +150 mm"),
                          tr(u"+50 мм", u"+50 mm"), tr(u"+100 мм", u"+100 mm"),
                          tr(u"+150 мм", u"+150 mm")]:
                self.increase.Items.Add(label)
            self.rules.Text = tr(
                u"Авто: большая сторона до 300 мм включительно → +50 мм; свыше 300 до 600 мм включительно → +100 мм; свыше 600 мм → +150 мм. Размер берётся после запаса по EIR. Добавка — к каждому из двух размеров, поровну с противоположных сторон. Толщина конструкции не увеличивается.",
                u"Auto: larger side up to 300 mm inclusive → +50 mm; over 300 up to 600 mm inclusive → +100 mm; over 600 mm → +150 mm. Based on the opening including EIR clearance. The increase applies to each of the two dimensions, split equally between opposite sides. Host thickness stays unchanged.")
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

        def dimension(self, x1, y1, x2, y2):
            self.line(x1, y1, x2, y2)
            for x, y in ((x1, y1), (x2, y2)):
                self.line(x - 4, y - 4, x + 4, y + 4)

        def draw(self):
            self.diagram.Children.Clear()
            box = result.boxes[0][1]
            a, b = [v * 304.8 for v in core.opening_sides(box)]
            delta = float(self.amount(box))
            tray = result.created[0][0]
            self.label(95, 0, tr(u"Первое отверстие — схема без масштаба", u"First opening — schematic, not to scale"))
            # Сечение лотка, отверстие с EIR и (только при ненулевой дельте) ЗНП.
            self.rect(140, 130, 200, 80, Brushes.Black)
            self.rect(115, 105, 250, 130, Brushes.Gray, True)
            pad = 20 if delta else 0
            if delta:
                self.rect(115 - pad, 105 - pad, 250 + 2 * pad, 130 + 2 * pad, Brushes.DarkOrange)
            self.label(155, 147, tr(u"Лоток, мм", u"Tray, mm"))
            self.label(155, 172, u"{:.0f} × {:.0f}".format(float(tray.Width * 304.8), float(tray.Height * 304.8)))
            # Размер A — горизонтальный; B — вертикальный. Выносные линии
            # и подписи вынесены за контуры, с отдельным местом сверху/снизу.
            self.line(115, 105, 115, 65)
            self.line(365, 105, 365, 65)
            self.dimension(115, 70, 365, 70)
            self.label(130, 38, tr(u"A = {:.0f} мм (по EIR)", u"A = {:.0f} mm (per EIR)").format(float(a)))
            self.line(115, 105, 68, 105)
            self.line(115, 235, 68, 235)
            self.dimension(75, 105, 75, 235)
            self.label(0, 145, u"B")
            self.label(0, 168, u"{:.0f}".format(float(b)))
            self.label(0, 190, tr(u"мм", u"mm"))
            if delta:
                self.line(95, 255, 95, 295)
                self.line(385, 255, 385, 295)
                self.dimension(95, 285, 385, 285)
                self.label(95, 310, tr(u"A + Δ = {:.0f} мм; B + Δ = {:.0f} мм",
                                      u"A + Δ = {:.0f} mm; B + Δ = {:.0f} mm").format(float(a + delta), float(b + delta)))
            self.label(435, 45, tr(u"A — горизонтальный размер отверстия", u"A — horizontal opening dimension"))
            self.label(435, 70, tr(u"B — вертикальный размер отверстия", u"B — vertical opening dimension"))
            self.label(435, 100, tr(u"Пунктир — отверстие с запасом по EIR", u"Dashed — opening with EIR clearance"))
            # Размер запаса между сечением и пунктиром, с выноской.
            self.dimension(340, 155, 365, 155)
            self.line(352, 155, 410, 155)
            self.line(410, 155, 430, 173)
            self.label(435, 160, tr(u"Запас по EIR: s = {:.0f} мм", u"EIR clearance: s = {:.0f} mm").format(float(clearance_mm)))
            self.label(435, 183, tr(u"с каждой стороны лотка", u"on each side of the tray"))
            if delta:
                self.dimension(365, 215, 385, 215)
                self.line(375, 215, 410, 215)
                self.line(410, 215, 430, 238)
                self.label(435, 225, tr(u"Дополнительно по ЗНП:", u"Additionally per ZNP:"))
                self.label(435, 248, tr(u"Δ/2 = {:.0f} мм с каждой стороны", u"Δ/2 = {:.0f} mm on each side").format(delta / 2.0))
                self.label(435, 280, tr(u"Оранжевый — итоговое отверстие", u"Orange — final opening"))

        def accept(self, sender, event):
            self.selection = (True, self.values[self.increase.SelectedIndex])
            self.Close()

    window = ResultWindow()
    window.ShowDialog()
    return window.selection
