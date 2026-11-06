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
    from System.Windows.Controls import StackPanel, TextBlock, TextBox, Button
    from lowlife import fire_boxes, param_autocomplete, select_list, settings_transfer

    class Editor(forms.WPFWindow):
        def __init__(self):
            forms.WPFWindow.__init__(self, u'''<Window
              xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
              xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
              Width="1360" Height="900" MinWidth="1200" MinHeight="780" Background="White" Foreground="#202020"
              WindowStartupLocation="CenterScreen">
              <Grid Margin="18" Background="White">
                <Grid.RowDefinitions><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
                <Grid.ColumnDefinitions><ColumnDefinition Width="530"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions>
                <TabControl x:Name="tabs" Margin="0,0,18,0"/>
                <Grid Grid.Column="1">
                  <Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
                  <TextBlock x:Name="summary" FontSize="18" FontWeight="SemiBold" TextWrapping="Wrap"/>
                  <Viewbox Grid.Row="1" Stretch="Uniform"><Canvas x:Name="diagram" Width="800" Height="650"/></Viewbox>
                  <TextBlock x:Name="explanation" Grid.Row="2" TextWrapping="Wrap" Margin="0,10,0,0"/>
                </Grid>
                <StackPanel x:Name="footer" Grid.Row="1" Grid.ColumnSpan="2" Orientation="Horizontal" HorizontalAlignment="Right" Margin="0,16,0,0"/>
              </Grid>
            </Window>''', literal_string=True)
            self.Title = tr(u'Огнезащитные короба — настройки', u'Fire enclosures — settings')
            self.values = cfg.normalize(values if values is not None else cfg.load())
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
                ('system_type_uid', tr(u'Система воздуховода для короба', u'Enclosure duct system'), 'system')]:
                self.fields = self.pages[1] if kind == 'tray' else self.pages[0]
                self.label(label)
                button = self.button(self.fields, self.type_label(key), lambda s, e, k=key, t=kind: self.pick_type(k, t))
                self.choose_buttons[key] = button
            for key, label in [
                ('support_bottom_mm', tr(u'От днища в свету до низа лотков, мм (0 — авто)', u'Clear floor to tray bottom, mm (0 — auto)')),
                ('rod_inset_mm', tr(u'От внутренней стенки до оси шпильки, мм *', u'Inner wall to rod axis, mm *')),
                ('ceiling_gap_mm', tr(u'От крышки до перекрытия, мм *', u'Lid to slab, mm *'))]:
                self.boxes[key] = self.field(label, self.values[key])
            self.fields = self.pages[2]
            for key, label in [
                ('inside_flag_param', tr(u'Параметр Да/Нет: элемент в ОКК', u'Yes/No parameter: inside enclosure')),
                ('enclosure_note_param', tr(u'Параметр примечания (пусто — штатные Комментарии)', u'Note parameter (blank — built-in Comments)'))]:
                self.boxes[key] = self.field(label, self.values[key])
            param_autocomplete.attach_by_keys(self.boxes, param_autocomplete.NameSource(doc))
            self.fields = self.pages[1]
            self.label(tr(u'Каждая строка — отдельный лоток. Размеры в мм.', u'Each row is a separate tray. Dimensions are in mm.'))
            self.row_panel = StackPanel()
            self.fields.Children.Add(self.row_panel)
            self.button(self.fields, tr(u'+ Добавить лоток', u'+ Add tray'), self.add_row)
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
            from System.Windows import GridLength, GridUnitType, VerticalAlignment, TextTrimming
            from System.Windows.Controls import Grid, ColumnDefinition
            self.row_panel.Children.Clear()
            self.rows = []
            def grid():
                panel = Grid()
                for width in (26, None, 65, 65, 28):
                    column = ColumnDefinition()
                    column.Width = GridLength(1, GridUnitType.Star) if width is None else GridLength(width)
                    panel.ColumnDefinitions.Add(column)
                panel.Margin = Thickness(0, 3, 0, 3)
                self.row_panel.Children.Add(panel)
                return panel
            header = grid()
            for index, title in enumerate([u'№', tr(u'Тип лотка', u'Tray type'),
                                            tr(u'Ш, мм', u'W, mm'), tr(u'В, мм', u'H, mm')]):
                label = TextBlock()
                label.Text = title
                Grid.SetColumn(label, index)
                header.Children.Add(label)
            for index, size in enumerate(sizes):
                panel = grid()
                label = TextBlock()
                label.Text = unicode(index + 1)
                label.VerticalAlignment = VerticalAlignment.Center
                panel.Children.Add(label)
                uid = size.get('tray_type_uid') or self.values.get('tray_type_uid', '')
                element = doc.GetElement(uid) if uid else None
                button = Button()
                caption = TextBlock()
                caption.Text = fire_boxes.type_name(element) if element is not None else tr(u'Выбрать тип…', u'Choose type…')
                caption.TextTrimming = TextTrimming.CharacterEllipsis
                button.Content = caption
                button.ToolTip = fire_boxes.type_label(element) if element is not None else caption.Text
                button.Padding = Thickness(5)
                button.Margin = Thickness(0, 0, 6, 0)
                Grid.SetColumn(button, 1)
                panel.Children.Add(button)
                row = dict(uid=uid, button=button, caption=caption)
                button.Click += lambda s, e, r=row: self.pick_row_type(r)
                for column_index, key in enumerate(('width_mm', 'height_mm'), 2):
                    box = TextBox()
                    box.Text = unicode(size[key])
                    box.Margin = Thickness(0, 0, 6, 0)
                    box.Padding = Thickness(5)
                    box.TextChanged += self.refresh
                    Grid.SetColumn(box, column_index)
                    panel.Children.Add(box)
                    row[key] = box
                remove = Button()
                remove.Content = u'×'
                remove.ToolTip = tr(u'Удалить лоток', u'Remove tray')
                remove.IsEnabled = len(sizes) > 1
                remove.Click += lambda s, e, n=index: self.remove_row(n)
                Grid.SetColumn(remove, 4)
                panel.Children.Add(remove)
                self.rows.append(row)

        def pick_row_type(self, row):
            options = fire_boxes.type_options(doc, 'tray')
            choice = select_list.SelectFromList.show(sorted(options), multiselect=False,
                          title=tr(u'Тип этого лотка', u'Type of this tray'))
            if choice:
                row['uid'] = options[choice].UniqueId
                row['caption'].Text = fire_boxes.type_name(options[choice])
                row['button'].ToolTip = choice
                self.refresh(None, None)

        def read(self):
            values = copy.deepcopy(self.values)
            values['product'] = unicode(self.product.SelectedItem)
            values['rating'] = int(self.rating.SelectedItem)
            values['arrangement'] = 'vertical' if self.arrangement.SelectedIndex == 0 else 'horizontal'
            for key, box in self.boxes.items():
                values[key] = box.Text.strip() if key.endswith('_param') else core.number(box.Text, minimum=-1000000 if key == 'elevation_mm' else 0)
            values['trays'] = [dict(width_mm=core.number(row['width_mm'].Text, positive=True),
                                   height_mm=core.number(row['height_mm'].Text, positive=True),
                                   tray_type_uid=row['uid']) for row in self.rows]
            return values

        def set_rows(self, sizes):
            self.loading = True
            try:
                self.rebuild_rows(sizes)
            finally:
                self.loading = False
            self.refresh(None, None)

        def add_row(self, sender, event):
            try:
                sizes = self.read()['trays']
                if len(sizes) >= 32:
                    raise ValueError(tr(u'Максимум 32 лотка.', u'Maximum 32 trays.'))
                sizes.append(dict(sizes[-1]))
                self.set_rows(sizes)
            except Exception as exc:
                forms.alert(unicode(exc))

        def remove_row(self, index):
            try:
                sizes = self.read()['trays']
                if len(sizes) > 1:
                    del sizes[index]
                    self.set_rows(sizes)
            except Exception as exc:
                forms.alert(unicode(exc))

        def refresh(self, sender, event):
            if self.loading:
                return
            try:
                values = self.read()
                section = core.mounting_section(values)
                summary = (tr(u'Короб: {:.0f} × {:.0f} мм\nПространство для кабелей: {:.0f} × {:.0f} мм',
                              u'Enclosure: {:.0f} × {:.0f} mm\nCable space: {:.0f} × {:.0f} mm')
                           if values['product'] == 'FIREBOX' else
                           tr(u'Короб: {:.0f} × {:.0f} мм\nВ свету: {:.0f} × {:.0f} мм',
                              u'Enclosure: {:.0f} × {:.0f} mm\nClear interior: {:.0f} × {:.0f} mm'))
                self.summary.Text = summary.format(
                                           float(section['width']), float(section['height']),
                                           float(section['cavity_width']), float(section['cavity_height']))
                caption = (tr(u'FIREBOX: выделено внутреннее пространство для кабелей.\n',
                              u'FIREBOX: the highlighted interior is cable space.\n')
                           if values['product'] == 'FIREBOX' else
                           tr(u'ОСК: позиции и размеры лотков совпадают с построением в модели.\n',
                              u'OSK: tray positions and dimensions match model placement.\n'))
                self.explanation.Text = caption + tr(
                    u'Габарит — по калькулятору 2Ф. Стенки, каркас и траверсы ОСК-90/180 — по АТР. '
                    u'* Отступы шпилек и высота подвеса уточняются проектом. Подвесы показаны на схеме и не создаются в модели.',
                    u'Overall dimensions follow the 2F calculator. OSK-90/180 walls, frame and crossbars follow the ATR. '
                    u'* Rod insets and suspension height are project inputs. Supports are previewed and are not created in the model.')
                if section['mounting_supported']:
                    self.explanation.Text += u'\n' + tr(u'АТР ОСК-{}, лист {}. Стенка: {:g} мм. Траверса: 30×30 мм.',
                        u'ATR OSK-{}, sheet {}. Wall: {:g} mm. Crossbar: 30×30 mm.').format(values['rating'], section['source_sheet'], float(section['wall']))
                if values['product'] == 'OSK' and not section['mounting_supported']:
                    self.explanation.Text += u'\n' + tr(u'Для ОСК-240 в приложенных АТР нет схемы подвесов и толщины стенки.',
                                                        u'The attached ATRs do not specify OSK-240 suspension or wall thickness.')
                if section['middle_rod_missing']:
                    self.explanation.Text += u'\n' + tr(u'Широкий короб: дополнительная шпилька пересекает лотки. Нужно проектное решение подвеса.',
                                                        u'Wide enclosure: an extra rod would intersect trays. A designed suspension solution is needed.')
                if values['product'] == 'OSK' and values['rating'] == 180 and section['top_clear'] < 100:
                    self.explanation.Text += u'\n' + tr(u'До крышки менее рекомендованных АТР 100 мм.', u'Less than the 100 mm lid clearance recommended by the ATR.')
                from lowlife.fire_boxes_diagram import draw
                draw(self.diagram, values, section)
            except Exception as exc:
                self.summary.Text = tr(u'Проверьте сечение:\n{}', u'Check cross-section:\n{}').format(exc)
                self.diagram.Children.Clear()

        def accept(self, sender, event):
            try:
                values = self.read()
                cfg.validate(values)
                for index, row in enumerate(values['trays']):
                    uid = row.get('tray_type_uid')
                    if not uid or doc.GetElement(uid) is None:
                        raise ValueError(tr(u'Выберите тип для лотка №{}.', u'Select the type for tray #{}.').format(index+1))
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
