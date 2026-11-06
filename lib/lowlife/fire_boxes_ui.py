# -*- coding: utf-8 -*-
"""Resizable cross-section editor. All coordinates displayed in millimetres."""
try:
    unicode
except NameError:
    unicode = str

import copy
from lowlife.i18n import tr
from lowlife import fire_boxes_core as core, fire_boxes_settings as cfg


def show(doc, values=None, preview_path=None, preview_tab=1):
    from pyrevit import forms
    from System.Windows import Thickness, TextWrapping, VerticalAlignment, HorizontalAlignment, FontWeights, Visibility
    from System.Windows.Controls import StackPanel, TextBlock, TextBox, Button, Grid, ColumnDefinition, Canvas
    from lowlife import fire_boxes, param_autocomplete, select_list, settings_transfer

    class Editor(forms.WPFWindow):
        def __init__(self):
            forms.WPFWindow.__init__(self, u'''<Window
              xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
              xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
              Width="1360" Height="900" MinWidth="1200" MinHeight="780" Background="White" Foreground="#202020"
              FontFamily="Segoe UI" FontSize="13"
              WindowStartupLocation="CenterScreen">
              <Window.Resources>
                <Style TargetType="TextBox">
                  <Setter Property="Padding" Value="7,5"/>
                  <Setter Property="MinHeight" Value="32"/>
                  <Setter Property="VerticalContentAlignment" Value="Center"/>
                </Style>
                <Style TargetType="ComboBox">
                  <Setter Property="Padding" Value="7,5"/>
                  <Setter Property="MinHeight" Value="32"/>
                  <Setter Property="VerticalContentAlignment" Value="Center"/>
                </Style>
                <Style TargetType="Button">
                  <Setter Property="Padding" Value="10,4"/>
                  <Setter Property="MinHeight" Value="32"/>
                  <Setter Property="VerticalContentAlignment" Value="Center"/>
                </Style>
                <Style TargetType="TabItem">
                  <Setter Property="Padding" Value="16,8"/>
                </Style>
              </Window.Resources>
              <Grid Margin="18" Background="White" TextElement.FontFamily="Segoe UI" TextElement.FontSize="13" UseLayoutRounding="True">
                <Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
                <Grid.ColumnDefinitions><ColumnDefinition Width="570"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions>
                <TextBlock x:Name="heading" Grid.ColumnSpan="2" FontSize="16" FontWeight="Bold" Margin="0,0,0,16"/>
                <TabControl x:Name="tabs" Grid.Row="1" Margin="0,0,18,0" BorderBrush="#D8DCE0" Background="White"/>
                <Border Grid.Row="1" Grid.Column="1" BorderBrush="#D8DCE0" BorderThickness="1" CornerRadius="4" Padding="16" Background="#FAFBFC">
                <Grid>
                  <Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
                  <TextBlock x:Name="summary" FontSize="16" FontWeight="Bold" TextWrapping="Wrap"/>
                  <Viewbox Grid.Row="1" Stretch="Uniform" Margin="0,12,0,12"><Canvas x:Name="diagram" Width="800" Height="650"/></Viewbox>
                  <TextBlock x:Name="explanation" Grid.Row="2" FontSize="12" Foreground="#606770" TextWrapping="Wrap"/>
                </Grid>
                </Border>
                <DockPanel Grid.Row="2" Grid.ColumnSpan="2" Margin="0,16,0,0" LastChildFill="False">
                  <StackPanel x:Name="transfer" DockPanel.Dock="Left" Orientation="Horizontal"/>
                  <StackPanel x:Name="footer" DockPanel.Dock="Right" Orientation="Horizontal"/>
                </DockPanel>
              </Grid>
            </Window>''', literal_string=True)
            self.Title = tr(u'Огнезащитные короба — настройки', u'Fire enclosures — settings')
            self.heading.Text = self.Title
            self.values = cfg.normalize(values if values is not None else cfg.load())
            self.result = None
            self.loading = True
            self.rows = []
            self.boxes = {}
            self.custom_side_spacing = self.values.get('rod_to_tray_mm') is not None
            self.spacing_updating = False
            self.diagram_editors = {}
            editor_panel = StackPanel()
            editor_panel.Width = 230
            for key, caption in [
                    ('rod_inset_mm', tr(u'Стенка → ось шпильки, мм *', u'Wall → rod axis, mm *')),
                    ('rod_to_tray_mm', tr(u'Ось шпильки → лоток, мм *', u'Rod axis → tray, mm *'))]:
                label = TextBlock()
                label.Text, label.TextWrapping = caption, TextWrapping.Wrap
                label.Margin = Thickness(0, 14 if key == 'rod_to_tray_mm' else 0, 0, 4)
                editor_panel.Children.Add(label)
                box = TextBox()
                box.Width, box.Height, box.FontSize = 110, 34, 16
                box.HorizontalAlignment = HorizontalAlignment.Left
                value = self.values.get(key)
                box.Text = unicode(value) if value is not None else ''
                box.ToolTip = caption + u'\n' + tr(u'Введите размер в мм. Ширина короба и разрез обновляются сразу.',
                                  u'Enter a dimension in mm. Enclosure width and section update immediately.')
                box.TextChanged += self.spacing_changed
                self.diagram_editors[key] = box
                editor_panel.Children.Add(box)
            self.boxes['rod_inset_mm'] = self.diagram_editors['rod_inset_mm']
            reset_spacing = Button()
            reset_spacing.Content = tr(u'По калькулятору 2Ф', u'Use 2F calculator')
            reset_spacing.HorizontalAlignment = HorizontalAlignment.Left
            reset_spacing.Margin = Thickness(0, 16, 0, 8)
            reset_spacing.Click += self.reset_spacing
            self.diagram_editors['reset'] = reset_spacing
            editor_panel.Children.Add(reset_spacing)
            hint = TextBlock()
            hint.Text = tr(u'Ширина меняется сразу', u'Width updates immediately')
            editor_panel.Children.Add(hint)
            self.diagram_editors['panel'] = editor_panel
            Canvas.SetLeft(editor_panel,560)
            Canvas.SetTop(editor_panel,250)
            Canvas.SetZIndex(editor_panel,10)
            self.diagram.Children.Add(editor_panel)
            from System.Windows.Controls import TabItem, ScrollViewer
            from System.Windows.Controls import ScrollBarVisibility
            self.pages = []
            for title in [tr(u'Короб', u'Enclosure'), tr(u'Лотки', u'Trays'), tr(u'Параметры', u'Parameters')]:
                tab = TabItem()
                tab.Header = title
                scroll = ScrollViewer()
                scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
                page = StackPanel()
                page.Margin = Thickness(16)
                scroll.Content, tab.Content = page, scroll
                self.tabs.Items.Add(tab)
                self.pages.append(page)
            self.fields = self.pages[0]
            self.product = self.combo(tr(u'Конструкция', u'Construction'), ['FIREBOX', 'OSK'], self.values['product'])
            self.rating = self.combo(tr(u'Огнестойкость, мин', u'Fire resistance, min'), [], None)
            self.wall_configuration = self.combo(tr(u'Стенки короба', u'Enclosure walls'),
                [tr(u'Четыре стенки', u'Four sides'),
                 tr(u'Без верхней — к перекрытию', u'No top — against slab'),
                 tr(u'Без левой — к стене', u'No left — against wall'),
                 tr(u'Без правой — к стене', u'No right — against wall')], None)
            self.wall_configuration.SelectedIndex = core.WALL_CONFIGURATIONS.index(self.values['wall_configuration'])
            self.worksets = fire_boxes.workset_options(doc)
            self.workset_boxes = {}
            self.workset_field('box_workset_name', tr(u'Рабочий набор коробов', u'Enclosure workset'))
            self.arrangement_page = self.pages[1]
            self.fields = self.arrangement_page
            self.workset_field('tray_workset_name', tr(u'Рабочий набор новых лотков', u'New tray workset'))
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
                button.Margin = Thickness(0, 0, 0, 12)
                button.HorizontalContentAlignment = HorizontalAlignment.Stretch
                caption = TextBlock()
                caption.Text = self.type_label(key)
                caption.TextWrapping = TextWrapping.Wrap
                button.Content = caption
                self.choose_buttons[key] = button
            for key, label in [
                ('support_bottom_mm', tr(u'От днища в свету до низа лотков, мм (0 — авто)', u'Clear floor to tray bottom, mm (0 — auto)')),
                ('top_clearance_mm', tr(u'Запас над верхним лотком, мм (пусто — авто)', u'Gap above the top tray, mm (blank — auto)')),
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
            add = self.button(self.fields, tr(u'+ Добавить лоток', u'+ Add tray'), self.add_row)
            add.HorizontalAlignment = HorizontalAlignment.Left
            cancel = self.button(self.footer, tr(u'Отмена', u'Cancel'), lambda s, e: self.Close())
            cancel.IsCancel = True
            save = self.button(self.footer, tr(u'Сохранить', u'Save'), self.accept)
            save.FontWeight = FontWeights.Bold
            save.Margin = Thickness(0)
            settings_transfer.add_transfer_buttons(self.transfer, cfg.STORE.read, cfg.STORE.write,
                                                  tr(u'огнезащитных коробов', u'fire enclosures'), self.reload)
            self.rebuild_rows(self.values['trays'])
            self.update_ratings(self.values['rating'])
            self.update_wall_controls()
            self.product.SelectionChanged += self.product_changed
            self.rating.SelectionChanged += self.rating_changed
            self.wall_configuration.SelectionChanged += self.wall_changed
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
            block.Margin = Thickness(0, 12, 0, 8)
            block.FontWeight = FontWeights.SemiBold
            self.fields.Children.Add(block)

        def field_row(self, label, control):
            from System.Windows import GridLength, GridUnitType
            panel = Grid()
            panel.Margin = Thickness(0, 0, 0, 12)
            for width in (230, None):
                column = ColumnDefinition()
                column.Width = GridLength(1, GridUnitType.Star) if width is None else GridLength(width)
                panel.ColumnDefinitions.Add(column)
            caption = TextBlock()
            caption.Text = label
            caption.TextWrapping = TextWrapping.Wrap
            caption.VerticalAlignment = VerticalAlignment.Center
            caption.Margin = Thickness(0, 0, 16, 0)
            panel.Children.Add(caption)
            Grid.SetColumn(control, 1)
            panel.Children.Add(control)
            self.fields.Children.Add(panel)

        def field(self, label, value):
            box = TextBox()
            box.Text = unicode(value) if value is not None else ''
            box.TextChanged += self.refresh
            if self.fields == self.pages[2]:
                self.label(label)
                self.fields.Children.Add(box)
            else:
                self.field_row(label, box)
            return box

        def combo(self, label, choices, value):
            from System.Windows.Controls import ComboBox
            box = ComboBox()
            for item in choices:
                box.Items.Add(item)
            if value in choices:
                box.SelectedIndex = choices.index(value)
            self.field_row(label, box)
            return box

        def button(self, panel, label, handler):
            button = Button()
            button.Content = label
            button.Margin = Thickness(0, 0, 8, 0)
            button.MinWidth = 90
            button.ToolTip = label
            button.Click += handler
            panel.Children.Add(button)
            return button

        def workset_field(self, key, label):
            active = tr(u'Активный рабочий набор', u'Active workset')
            names = sorted(self.worksets, key=lambda name: name.lower())
            selected = self.values.get(key, '')
            # Keep a missing saved choice visible; never silently substitute a set.
            if selected and selected not in names:
                names.append(selected)
            box = self.combo(label, [active] + names, selected or active)
            box.IsEnabled = doc.IsWorkshared
            box.ToolTip = (tr(u'Назначается новым участкам и соединительным деталям.',
                              u'Assigned to new segments and fittings.') if doc.IsWorkshared else
                           tr(u'В этой модели рабочие наборы не включены.',
                              u'Worksharing is not enabled in this model.'))
            self.workset_boxes[key] = box

        def type_label(self, key):
            el = doc.GetElement(self.values.get(key, '')) if self.values.get(key) else None
            return fire_boxes.type_label(el) if el is not None else tr(u'Выбрать…', u'Choose…')

        def pick_type(self, key, kind):
            options = fire_boxes.type_options(doc, kind)
            choice = select_list.SelectFromList.show(sorted(options), multiselect=False,
                                                      title=tr(u'Выберите тип', u'Select type'))
            if choice:
                self.values[key] = options[choice].UniqueId
                self.choose_buttons[key].Content.Text = choice
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
            self.update_wall_controls()
            self.refresh(None, None)

        def update_wall_controls(self):
            supported = unicode(self.product.SelectedItem) == 'OSK' and self.rating.SelectedItem in (90, 180)
            self.wall_configuration.IsEnabled = supported
            self.wall_configuration.ToolTip = tr(u'Трёхсторонние конфигурации ОСК-90/180 по АТР. Слева и справа — как на разрезе.',
                                                 u'Three-sided OSK-90/180 configurations from the ATR. Left and right follow the preview.')
            if not supported:
                self.wall_configuration.SelectedIndex = 0
            self.boxes['top_clearance_mm'].IsEnabled = supported
            self.boxes['top_clearance_mm'].ToolTip = tr(
                u'Для ОСК-90/180. Пусто — прежняя высота по калькулятору 2Ф. Число, включая 0, задаёт зазор до крышки или перекрытия и пересчитывает высоту, сохраняя нижний отступ.',
                u'For OSK-90/180. Blank keeps the 2F calculator height. A number, including 0, sets the gap to the lid or slab and recalculates height while preserving the bottom clearance.')
            self.boxes['ceiling_gap_mm'].IsEnabled = self.wall_configuration.SelectedIndex != 1
            self.boxes['ceiling_gap_mm'].ToolTip = tr(
                u'Без верхней стенки короб примыкает к перекрытию: на схеме зазор равен 0. Для остальных конфигураций используется введённое значение.',
                u'Without the top panel the enclosure meets the slab: the preview gap is 0. Other configurations use the entered value.')

        def rating_changed(self, sender, event):
            if self.loading:
                return
            self.update_wall_controls()
            self.refresh(None, None)

        def wall_changed(self, sender, event):
            if self.loading:
                return
            self.update_wall_controls()
            self.refresh(None, None)

        def spacing_changed(self, sender, event):
            if self.loading or self.spacing_updating:
                return
            self.custom_side_spacing = True
            self.refresh(None, None)

        def reset_spacing(self, sender, event):
            self.custom_side_spacing = False
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
                panel.Margin = Thickness(0, 0, 0, 8)
                self.row_panel.Children.Add(panel)
                return panel
            header = grid()
            for index, title in enumerate([u'№', tr(u'Тип лотка', u'Tray type'),
                                            tr(u'Ш, мм', u'W, mm'), tr(u'В, мм', u'H, mm')]):
                label = TextBlock()
                label.Text = title
                label.FontWeight = FontWeights.SemiBold
                label.Margin = Thickness(0, 8, 0, 4)
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
                button.Padding = Thickness(7, 5, 7, 5)
                button.HorizontalContentAlignment = HorizontalAlignment.Left
                button.Margin = Thickness(0, 0, 6, 0)
                Grid.SetColumn(button, 1)
                panel.Children.Add(button)
                row = dict(uid=uid, button=button, caption=caption)
                button.Click += lambda s, e, r=row: self.pick_row_type(r)
                for column_index, key in enumerate(('width_mm', 'height_mm'), 2):
                    box = TextBox()
                    box.Text = unicode(size[key])
                    box.Margin = Thickness(0, 0, 6, 0)
                    box.HorizontalContentAlignment = HorizontalAlignment.Right
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
            values['wall_configuration'] = core.WALL_CONFIGURATIONS[self.wall_configuration.SelectedIndex]
            if doc.IsWorkshared:
                for key, box in self.workset_boxes.items():
                    values[key] = unicode(box.SelectedItem) if box.SelectedIndex > 0 else ''
            spacing_supported = values['product'] == 'OSK' and values['rating'] in (90, 180)
            for key, box in self.boxes.items():
                if key == 'rod_inset_mm' and not spacing_supported:
                    continue
                if key == 'top_clearance_mm':
                    if spacing_supported:
                        values[key] = core.number(box.Text) if box.Text.strip() else None
                    continue
                values[key] = box.Text.strip() if key.endswith('_param') else core.number(box.Text, minimum=-1000000 if key == 'elevation_mm' else 0)
            if spacing_supported:
                values['rod_to_tray_mm'] = (core.number(self.diagram_editors['rod_to_tray_mm'].Text, positive=True)
                                            if self.custom_side_spacing else None)
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
            spacing_supported = unicode(self.product.SelectedItem) == 'OSK' and self.rating.SelectedItem in (90, 180)
            for editor in self.diagram_editors.values():
                editor.Visibility = Visibility.Visible if spacing_supported else Visibility.Collapsed
            try:
                values = self.read()
                section = core.mounting_section(values)
                if section['mounting_supported'] and not self.custom_side_spacing:
                    self.spacing_updating = True
                    try:
                        self.diagram_editors['rod_to_tray_mm'].Text = u'{:g}'.format(float(section['rod_to_tray']))
                    finally:
                        self.spacing_updating = False
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
                    u'Исходный габарит — по калькулятору 2Ф. Стенки, каркас и траверсы ОСК-90/180 — по АТР. '
                    u'* Отступы шпилек и высота подвеса уточняются проектом. Подвесы показаны на схеме и не создаются в модели.',
                    u'The initial envelope follows the 2F calculator. OSK-90/180 walls, frame and crossbars follow the ATR. '
                    u'* Rod insets and suspension height are project inputs. Supports are previewed and are not created in the model.')
                if section['custom_side_spacing']:
                    self.explanation.Text += u'\n' + tr(
                        u'Ширина задана размерами на схеме. Боковые расстояния применяются с двух сторон. Дополнительный запас задаёт минимальный боковой зазор.',
                        u'Width follows the diagram dimensions. Side distances apply on both sides. Extra clearance sets the minimum side gap.')
                if section['custom_top_clearance']:
                    self.explanation.Text += u'\n' + tr(
                        u'Высота пересчитана по заданному запасу над лотком: {:g} мм. Нижний отступ сохранён.',
                        u'Height follows the specified top gap: {:g} mm. Bottom clearance is preserved.').format(float(section['top_clear']))
                if section['mounting_supported']:
                    self.explanation.Text += u'\n' + tr(u'АТР ОСК-{}, лист {}. Стенка: {:g} мм. Траверса: 30×30 мм.',
                        u'ATR OSK-{}, sheet {}. Wall: {:g} mm. Crossbar: 30×30 mm.').format(values['rating'], section['source_sheet'], float(section['wall']))
                if values['wall_configuration'] != 'closed':
                    self.explanation.Text += u'\n' + tr(
                        u'Габарит уменьшен на толщину одной стенки. В свету размеры сохранены. '
                        u'Отсутствующая стенка заменяется строительной конструкцией; узел примыкания выполняется по АТР.',
                        u'The envelope is reduced by one panel thickness; clear dimensions are preserved. '
                        u'The omitted panel is replaced by the building structure; follow the ATR junction detail.')
                if values['product'] == 'OSK' and not section['mounting_supported']:
                    self.explanation.Text += u'\n' + tr(u'Для ОСК-240 в приложенных АТР нет схемы подвесов и толщины стенки.',
                                                        u'The attached ATRs do not specify OSK-240 suspension or wall thickness.')
                if section['middle_rod_missing']:
                    self.explanation.Text += u'\n' + tr(u'Широкий короб: дополнительная шпилька пересекает лотки. Нужно проектное решение подвеса.',
                                                        u'Wide enclosure: an extra rod would intersect trays. A designed suspension solution is needed.')
                if values['product'] == 'OSK' and values['rating'] == 180 and values['wall_configuration'] != 'no_top' and section['top_clear'] < 100:
                    self.explanation.Text += u'\n' + tr(u'До крышки менее рекомендованных АТР 100 мм.', u'Less than the 100 mm lid clearance recommended by the ATR.')
                from lowlife.fire_boxes_diagram import draw
                draw(self.diagram, values, section, editors=self.diagram_editors)
            except Exception as exc:
                self.summary.Text = tr(u'Проверьте сечение:\n{}', u'Check cross-section:\n{}').format(exc)
                # Keep the last valid preview and its live controls while a
                # number is temporarily blank/invalid; do not steal typing focus.

        def accept(self, sender, event):
            try:
                values = self.read()
                cfg.validate(values)
                for key in self.workset_boxes:
                    fire_boxes.resolve_workset(doc, values.get(key, ''))
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
            window.tabs.SelectedIndex = preview_tab
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
