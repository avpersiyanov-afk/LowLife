# -*- coding: utf-8 -*-
"""Resizable cross-section editor. All coordinates displayed in millimetres."""
import copy
from lowlife.i18n import tr
from lowlife import fire_boxes_core as core, fire_boxes_settings as cfg

try:
    unicode
except NameError:
    unicode = str


def show(doc, values=None, preview_path=None):
    from pyrevit import forms
    from System.Windows import Thickness, TextWrapping
    from System.Windows.Controls import StackPanel, TextBlock, TextBox, Button, Canvas
    from System.Windows.Media import Brushes
    from System.Windows.Shapes import Rectangle, Line
    from lowlife import fire_boxes, param_autocomplete, select_list, settings_transfer

    class Editor(forms.WPFWindow):
        def __init__(self):
            forms.WPFWindow.__init__(self, u'''<Window
              xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
              xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
              Width="1100" Height="820" MinWidth="960" MinHeight="700" Background="White" Foreground="#202020"
              WindowStartupLocation="CenterScreen">
              <Grid Margin="18" Background="White">
                <Grid.RowDefinitions><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
                <Grid.ColumnDefinitions><ColumnDefinition Width="440"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions>
                <TabControl x:Name="tabs" Margin="0,0,18,0"/>
                <Grid Grid.Column="1">
                  <Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
                  <TextBlock x:Name="summary" FontSize="18" FontWeight="SemiBold" TextWrapping="Wrap"/>
                  <Viewbox Grid.Row="1" Stretch="Uniform"><Canvas x:Name="diagram" Width="560" Height="450"/></Viewbox>
                  <TextBlock x:Name="explanation" Grid.Row="2" TextWrapping="Wrap" Margin="0,10,0,0"/>
                </Grid>
                <StackPanel x:Name="footer" Grid.Row="1" Grid.ColumnSpan="2" Orientation="Horizontal" HorizontalAlignment="Right" Margin="0,16,0,0"/>
              </Grid>
            </Window>''', literal_string=True)
            self.Title = tr(u'Огнезащитные короба — настройки', u'Fire enclosures — settings')
            self.values = copy.deepcopy(values if values is not None else cfg.load())
            self.result = None
            self.loading = True
            self.rows = []
            self.boxes = {}
            from System.Windows.Controls import TabItem, ScrollViewer
            from System.Windows.Controls import ScrollBarVisibility
            self.pages = []
            for title in [tr(u'Короб', u'Enclosure'), tr(u'Лотки', u'Trays'), tr(u'Параметры', u'Parameters')]:
                tab = TabItem()
                tab.Header = title
                scroll = ScrollViewer()
                scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
                page = StackPanel()
                page.Margin = Thickness(8)
                scroll.Content, tab.Content = page, scroll
                self.tabs.Items.Add(tab)
                self.pages.append(page)
            self.fields = self.pages[0]
            self.product = self.combo(tr(u'Конструкция', u'Construction'), ['FIREBOX', 'OSK'], self.values['product'])
            self.rating = self.combo(tr(u'Огнестойкость, мин', u'Fire resistance, min'), [], None)
            self.arrangement_page = self.pages[1]
            self.fields = self.arrangement_page
            self.arrangement = self.combo(tr(u'Расположение лотков', u'Tray arrangement'),
                                          [tr(u'Ярусами снизу вверх', u'Stacked bottom to top'),
                                           tr(u'Рядом слева направо', u'Side by side, left to right')], None)
            self.arrangement.SelectedIndex = 0 if self.values['arrangement'] == 'vertical' else 1
            for key, label in [
                ('gap_mm', tr(u'Расстояние между лотками, мм', u'Clear gap between trays, mm')),
                ('clearance_mm', tr(u'Дополнительный запас с каждой стороны, мм', u'Additional clearance on each side, mm'))]:
                self.boxes[key] = self.field(label, self.values[key])
            self.fields = self.pages[0]
            self.boxes['elevation_mm'] = self.field(tr(u'Высота оси короба от уровня при рисовании, мм', u'Enclosure axis above level when drawing, mm'), self.values['elevation_mm'])
            self.choose_buttons = {}
            for key, label, kind in [
                ('box_type_uid', tr(u'Тип короба', u'Enclosure type'), 'box'),
                ('system_type_uid', tr(u'Система воздуховода для короба', u'Enclosure duct system'), 'system'),
                ('tray_type_uid', tr(u'Тип внутренних лотков', u'Internal tray type'), 'tray')]:
                self.fields = self.pages[1] if kind == 'tray' else self.pages[0]
                self.label(label)
                button = self.button(self.fields, self.type_label(key), lambda s, e, k=key, t=kind: self.pick_type(k, t))
                self.choose_buttons[key] = button
            self.fields = self.pages[2]
            for key, label in [
                ('inside_flag_param', tr(u'Параметр Да/Нет: элемент в ОКК', u'Yes/No parameter: inside enclosure')),
                ('enclosure_note_param', tr(u'Параметр примечания (пусто — штатные Комментарии)', u'Note parameter (blank — built-in Comments)'))]:
                self.boxes[key] = self.field(label, self.values[key])
            param_autocomplete.attach_by_keys(self.boxes, param_autocomplete.NameSource(doc))
            self.fields = self.pages[1]
            self.count_box = self.field(tr(u'Количество лотков (1–32)', u'Number of trays (1–32)'), len(self.values['trays']))
            self.button(self.fields, tr(u'Применить количество', u'Apply count'), self.change_count)
            self.label(tr(u'Внутренние лотки: ширина × высота, мм', u'Internal trays: width × height, mm'))
            self.row_panel = StackPanel()
            self.fields.Children.Add(self.row_panel)
            self.button(self.footer, tr(u'Сохранить', u'Save'), self.accept)
            cancel = self.button(self.footer, tr(u'Отмена', u'Cancel'), lambda s, e: self.Close())
            cancel.IsCancel = True
            settings_transfer.add_transfer_buttons(self.footer, cfg.STORE.read, cfg.STORE.write,
                                                  tr(u'огнезащитных коробов', u'fire enclosures'), self.reload)
            self.rebuild_rows(self.values['trays'])
            self.update_ratings(self.values['rating'])
            self.product.SelectionChanged += self.product_changed
            self.rating.SelectionChanged += self.refresh
            self.arrangement.SelectionChanged += self.refresh
            self.loading = False
            self.tabs.SelectedIndex = 1
            self.refresh(None, None)

        def reload(self):
            self.result = settings_transfer.RELOAD
            self.Close()

        def label(self, text):
            block = TextBlock()
            block.Text = text
            block.TextWrapping = TextWrapping.Wrap
            block.Margin = Thickness(0, 12, 0, 4)
            self.fields.Children.Add(block)

        def field(self, label, value):
            self.label(label)
            box = TextBox()
            box.Text = unicode(value)
            box.Padding = Thickness(5)
            box.TextChanged += self.refresh
            self.fields.Children.Add(box)
            return box

        def combo(self, label, choices, value):
            from System.Windows.Controls import ComboBox
            self.label(label)
            box = ComboBox()
            for item in choices:
                box.Items.Add(item)
            if value in choices:
                box.SelectedIndex = choices.index(value)
            self.fields.Children.Add(box)
            return box

        def button(self, panel, label, handler):
            button = Button()
            button.Content = label
            button.Padding = Thickness(10, 6, 10, 6)
            button.Margin = Thickness(0, 4, 8, 0)
            button.ToolTip = label
            button.Click += handler
            panel.Children.Add(button)
            return button

        def type_label(self, key):
            el = doc.GetElement(self.values.get(key, '')) if self.values.get(key) else None
            return fire_boxes.type_label(el) if el is not None else tr(u'Выбрать…', u'Choose…')

        def pick_type(self, key, kind):
            options = fire_boxes.type_options(doc, kind)
            choice = select_list.SelectFromList.show(sorted(options), multiselect=False,
                                                      title=tr(u'Выберите тип', u'Select type'))
            if choice:
                self.values[key] = options[choice].UniqueId
                self.choose_buttons[key].Content = choice
                self.choose_buttons[key].ToolTip = choice

        def update_ratings(self, selected):
            self.rating.Items.Clear()
            supported = core.ratings(unicode(self.product.SelectedItem))
            for value in supported:
                self.rating.Items.Add(value)
            self.rating.SelectedItem = selected if selected in supported else supported[0]

        def product_changed(self, sender, event):
            selected = self.rating.SelectedItem
            self.loading = True
            self.update_ratings(selected)
            self.loading = False
            self.refresh(None, None)

        def rebuild_rows(self, sizes):
            self.row_panel.Children.Clear()
            self.rows = []
            for index, size in enumerate(sizes):
                panel = StackPanel()
                from System.Windows.Controls import Orientation
                panel.Orientation = Orientation.Horizontal
                panel.Margin = Thickness(0, 3, 0, 3)
                label = TextBlock()
                label.Text = u'{}:  '.format(index + 1)
                label.Width = 35
                panel.Children.Add(label)
                boxes = []
                for key in ('width_mm', 'height_mm'):
                    box = TextBox()
                    box.Text = unicode(size[key])
                    box.Width = 145
                    box.Margin = Thickness(0, 0, 8, 0)
                    box.Padding = Thickness(5)
                    box.TextChanged += self.refresh
                    panel.Children.Add(box)
                    boxes.append(box)
                self.rows.append(boxes)
                self.row_panel.Children.Add(panel)

        def read(self):
            values = copy.deepcopy(self.values)
            values['product'] = unicode(self.product.SelectedItem)
            values['rating'] = int(self.rating.SelectedItem)
            values['arrangement'] = 'vertical' if self.arrangement.SelectedIndex == 0 else 'horizontal'
            for key, box in self.boxes.items():
                values[key] = box.Text.strip() if key.endswith('_param') else core.number(box.Text, minimum=-1000000 if key == 'elevation_mm' else 0)
            values['trays'] = [dict(width_mm=core.number(w.Text, positive=True),
                                   height_mm=core.number(h.Text, positive=True)) for w, h in self.rows]
            return values

        def change_count(self, sender, event):
            try:
                value = core.number(self.count_box.Text, minimum=1)
                if value != int(value) or value > 32:
                    raise ValueError()
                sizes = self.read()['trays']
                while len(sizes) < int(value):
                    sizes.append(dict(sizes[-1]))
                self.loading = True
                self.rebuild_rows(sizes[:int(value)])
                self.loading = False
                self.refresh(None, None)
            except Exception:
                forms.alert(tr(u'Укажите целое количество от 1 до 32 и положительные размеры.',
                               u'Enter an integer count from 1 to 32 and positive dimensions.'))

        def refresh(self, sender, event):
            if self.loading:
                return
            try:
                values = self.read()
                section = core.layout(values)
                summary = (tr(u'Короб: {:.0f} × {:.0f} мм\nПространство для кабелей: {:.0f} × {:.0f} мм',
                              u'Enclosure: {:.0f} × {:.0f} mm\nCable space: {:.0f} × {:.0f} mm')
                           if values['product'] == 'FIREBOX' else
                           tr(u'Короб: {:.0f} × {:.0f} мм\nВнутри: {:.0f} × {:.0f} мм',
                              u'Enclosure: {:.0f} × {:.0f} mm\nInside: {:.0f} × {:.0f} mm'))
                self.summary.Text = summary.format(
                                           float(section['width']), float(section['height']),
                                           float(section['inner_width']), float(section['inner_height']))
                caption = (tr(u'FIREBOX: выделено внутреннее пространство для кабелей.\n',
                              u'FIREBOX: the highlighted interior is cable space.\n')
                           if values['product'] == 'FIREBOX' else
                           tr(u'ОСК: показаны открытые сечения внутренних лотков. Номера соответствуют строкам слева.\n',
                              u'OSK: open internal tray sections are shown. Numbers match the rows on the left.\n'))
                self.explanation.Text = caption + tr(
                    u'Размеры короба — по калькулятору 2Ф. Для ОСК учтены суммарные прибавки калькулятора; это не толщина стенок. '
                    u'Зазоры задаются проектом, значение 0 не означает разрешение монтажа вплотную.\n'
                    u'Рисование: укажите точки оси на плане, Esc завершает трассу. Соединительные детали берутся из настроек выбранного типа.',
                    u'Enclosure dimensions follow the 2F calculator. OSK uses total calculator allowances, not wall thickness. '
                    u'Clearances are project inputs; zero does not approve installation without a gap.\n'
                    u'Draw: pick axis points in plan; Esc ends the route. Fittings use the selected type routing settings.')
                self.draw(section, values['product'])
            except Exception:
                self.summary.Text = tr(u'Проверьте размеры и огнестойкость.', u'Check dimensions and fire resistance.')
                self.diagram.Children.Clear()

        def draw(self, section, product):
            self.diagram.Children.Clear()
            scale = min(400.0 / section['width'], 290.0 / section['height'])
            cx, cy = 280, 225

            def rectangle(x, y, w, h, stroke, fill):
                item = Rectangle()
                item.Width, item.Height = w * scale, h * scale
                item.Stroke, item.Fill, item.StrokeThickness = stroke, fill, 2
                Canvas.SetLeft(item, cx + (x - w / 2) * scale)
                Canvas.SetTop(item, cy - (y + h / 2) * scale)
                self.diagram.Children.Add(item)

            def text(x, y, value):
                item = TextBlock()
                item.Text, item.FontSize = value, 14
                Canvas.SetLeft(item, x)
                Canvas.SetTop(item, y)
                self.diagram.Children.Add(item)

            def tray(row):
                left = cx + (row['x'] - row['width'] / 2) * scale
                right = left + row['width'] * scale
                top = cy - (row['z'] + row['height'] / 2) * scale
                bottom = top + row['height'] * scale
                # The open top distinguishes a tray from a cable-space block.
                for x1, y1, x2, y2 in [(left, top, left, bottom),
                                       (left, bottom, right, bottom),
                                       (right, bottom, right, top)]:
                    edge = Line()
                    edge.X1, edge.Y1, edge.X2, edge.Y2 = x1, y1, x2, y2
                    edge.Stroke, edge.StrokeThickness = Brushes.SteelBlue, 3
                    self.diagram.Children.Add(edge)
                text(cx + row['x'] * scale - 6, cy - row['z'] * scale - 10, unicode(row['index'] + 1))

            def dimension(x1, y1, x2, y2, label):
                item = Line()
                item.X1, item.Y1, item.X2, item.Y2 = x1, y1, x2, y2
                item.Stroke, item.StrokeThickness = Brushes.DimGray, 1
                self.diagram.Children.Add(item)
                text((x1 + x2) / 2 + 6, (y1 + y2) / 2 + 3, label)

            rectangle(0, 0, section['width'], section['height'], Brushes.DarkOrange, Brushes.Bisque)
            if product == 'FIREBOX':
                rectangle(0, 0, section['inner_width'], section['inner_height'], Brushes.SteelBlue, Brushes.LightBlue)
                text(30, 12, tr(u'Пространство для кабелей', u'Cable space'))
                if section['inner_width'] * scale >= 100 and section['inner_height'] * scale >= 40:
                    text(cx - 28, cy - 10, tr(u'Кабели', u'Cables'))
            else:
                rectangle(0, 0, section['inner_width'], section['inner_height'], Brushes.Gray, Brushes.WhiteSmoke)
                for row in section['trays']:
                    tray(row)
                text(30, 12, u' | '.join(u'{}: {:g} × {:g}'.format(r['index'] + 1, float(r['width']), float(r['height'])) for r in section['trays'][:4]))
            w, h = section['width'] * scale / 2, section['height'] * scale / 2
            dimension(cx - w, cy + h + 24, cx + w, cy + h + 24, u'{:g} mm'.format(float(section['width'])))
            dimension(cx + w + 15, cy - h, cx + w + 15, cy + h, u'{:g} mm'.format(float(section['height'])))

        def accept(self, sender, event):
            try:
                value = core.number(self.count_box.Text, minimum=1)
                if value != len(self.rows):
                    raise ValueError(tr(u'Нажмите «Применить количество».', u'Click Apply count.'))
                values = self.read()
                cfg.validate(values)
                box_type = doc.GetElement(values['box_type_uid'])
                if box_type is None:
                    raise ValueError(tr(u'Выберите тип короба в этой модели.', u'Select an enclosure type in this model.'))
                if fire_boxes.is_duct_type(box_type) and not values['system_type_uid']:
                    raise ValueError(tr(u'Выберите систему воздуховода.', u'Select a duct system.'))
                cfg.save(values)
                self.result = values
                self.Close()
            except Exception as exc:
                forms.alert(tr(u'Не удалось сохранить настройки:\n{}', u'Could not save settings:\n{}').format(exc))

    while True:
        window = Editor()
        if preview_path:
            from System.Windows import Size, Rect
            from System.Windows.Media import PixelFormats
            from System.Windows.Media.Imaging import RenderTargetBitmap, PngBitmapEncoder, BitmapFrame
            from System.IO import FileStream, FileMode
            window.Content.Measure(Size(window.Width, window.Height))
            window.Content.Arrange(Rect(0, 0, window.Width, window.Height))
            window.Content.UpdateLayout()
            bitmap = RenderTargetBitmap(int(window.Width), int(window.Height), 96, 96, PixelFormats.Pbgra32)
            bitmap.Render(window.Content)
            encoder = PngBitmapEncoder()
            encoder.Frames.Add(BitmapFrame.Create(bitmap))
            stream = FileStream(preview_path, FileMode.Create)
            try:
                encoder.Save(stream)
            finally:
                stream.Close()
                window.Close()
            return True
        window.ShowDialog()
        if window.result != settings_transfer.RELOAD:
            return window.result
