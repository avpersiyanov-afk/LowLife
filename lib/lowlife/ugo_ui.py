# -*- coding: utf-8 -*-
"""Modal UGO catalog editor; writes are performed after closing the dialog."""
try:
    unicode
except NameError:
    unicode = str

import copy
import uuid
import math
import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
from System.Collections.Generic import List
from System.Windows import Window, Thickness, WindowStartupLocation, TextWrapping
from System.Windows.Controls import (DockPanel, Dock, StackPanel, Orientation,
    TextBlock, TextBox, Button, ComboBox, CheckBox, DataGrid, DataGridTextColumn,
    DataGridLength, DataGridLengthUnitType, DataGridEditingUnit, DataGridSelectionMode)
from System.Windows.Data import Binding, BindingMode, UpdateSourceTrigger
from Autodesk.Revit.DB import FilteredElementCollector, TextNoteType
from pyrevit import forms
from lowlife.i18n import tr
from lowlife.scs_settings import _safe_element_name
from lowlife import text_search, ugo_core as core, ugo_revit as api


class Row(object):
    def __init__(self, data):
        self.uid = data['uid']
        self.name = data['name']
        self.label = data['label']
        self.systems = data['systems']
        self.groups = data['groups']
        self.status = tr(u'Доступен', u'Available') if data.get('available', True) else tr(u'Тип удалён', u'Type deleted')

    def data(self):
        return dict(uid=self.uid, name=self.name, label=self.label,
                    systems=self.systems or u'', groups=self.groups or u'')


def show(doc, original):
    data = copy.deepcopy(original)
    rows = [Row(r) for r in api.catalog(doc, data)]
    window = Window()
    window.Title = tr(u'Списки УГО', u'UGO lists')
    window.Width, window.Height = 1150, 760
    window.MinWidth, window.MinHeight = 900, 620
    window.WindowStartupLocation = WindowStartupLocation.CenterScreen
    root = DockPanel()
    root.Margin = Thickness(12)
    window.Content = root
    result = []

    def panel(dock=Dock.Top):
        p = StackPanel()
        p.Orientation = Orientation.Horizontal
        p.Margin = Thickness(0, 4, 0, 4)
        DockPanel.SetDock(p, dock)
        root.Children.Add(p)
        return p

    def label(parent, ru, en):
        value = TextBlock()
        value.Text = tr(ru, en)
        value.Margin = Thickness(4, 5, 8, 0)
        parent.Children.Add(value)
        return value

    def button(parent, ru, en, callback):
        value = Button()
        value.Content = tr(ru, en)
        value.Margin = Thickness(4, 0, 4, 0)
        value.Padding = Thickness(10, 5, 10, 5)
        value.Click += callback
        parent.Children.Add(value)
        return value

    def box(parent, value, width):
        control = TextBox()
        control.Text = unicode(value)
        control.Width = width
        parent.Children.Add(control)
        return control

    hint = TextBlock()
    hint.Text = tr(u'Системы и списки в строках — через запятую. Список включает явно назначенные узлы и узлы его систем. Подпись можно изменить.',
                   u'Separate systems and lists with commas. A list includes explicitly assigned items and items matching its systems. Labels are editable.')
    hint.TextWrapping = TextWrapping.Wrap
    DockPanel.SetDock(hint, Dock.Top)
    root.Children.Add(hint)
    group_bar = panel()
    label(group_bar, u'Список:', u'List:')
    groups = ComboBox()
    groups.Width = 235
    group_bar.Children.Add(groups)
    system_bar = panel()
    label(system_bar, u'Системы выбранного списка:', u'Systems in selected list:')
    group_systems = box(system_bar, '', 420)
    template_bar = panel()
    label(template_bar, u'Пустая легенда-образец:', u'Empty source legend:')
    templates = ComboBox()
    templates.Width = 275
    template_bar.Children.Add(templates)
    template_views = api.legends(doc)
    for view in template_views:
        templates.Items.Add(view.Name)
    templates.SelectedIndex = next((i for i, v in enumerate(template_views)
                                    if v.UniqueId == data.get('template_uid')), -1)
    label(template_bar, u'Тип текста:', u'Text type:')
    texts = ComboBox()
    texts.Width = 260
    template_bar.Children.Add(texts)
    text_types = sorted(list(FilteredElementCollector(doc).OfClass(TextNoteType)),
                        key=lambda t: _safe_element_name(t) or '')
    for t in text_types:
        texts.Items.Add(_safe_element_name(t))
    texts.SelectedIndex = next((i for i, t in enumerate(text_types)
                               if t.UniqueId == data.get('text_uid')), 0 if text_types else -1)
    layout_bar = panel()
    label(layout_bar, u'Масштаб 1:', u'Scale 1:')
    scale = box(layout_bar, data.get('scale', 1), 55)
    label(layout_bar, u'Мин. шаг, мм:', u'Min. row, mm:')
    row_mm = box(layout_bar, data.get('row_mm', 12), 55)
    label(layout_bar, u'Отступ текста, мм:', u'Text gap, mm:')
    gap_mm = box(layout_bar, data.get('gap_mm', 8), 55)
    label(layout_bar, u'Ширина текста, мм:', u'Text width, mm:')
    width_mm = box(layout_bar, data.get('width_mm', 90), 55)
    search_bar = panel()
    label(search_bar, u'Поиск:', u'Search:')
    search = box(search_bar, '', 330)
    only_group = CheckBox()
    only_group.Content = tr(u'Только выбранный список', u'Selected list only')
    only_group.Margin = Thickness(12, 4, 0, 0)
    search_bar.Children.Add(only_group)
    bottom = panel(Dock.Bottom)
    bulk = panel(Dock.Bottom)
    grid = DataGrid()
    grid.AutoGenerateColumns = False
    grid.CanUserAddRows = grid.CanUserDeleteRows = False
    grid.SelectionMode = DataGridSelectionMode.Extended
    for key, ru, en, weight in [('name', u'Семейство : тип', u'Family : type', 2),
                                ('label', u'Подпись', u'Label', 2),
                                ('systems', u'Системы', u'Systems', 1),
                                ('groups', u'Списки', u'Lists', 1),
                                ('status', u'Состояние', u'Status', 0.6)]:
        col = DataGridTextColumn()
        col.Header = tr(ru, en)
        binding = Binding(key)
        binding.Mode = BindingMode.TwoWay
        binding.UpdateSourceTrigger = UpdateSourceTrigger.PropertyChanged
        col.Binding = binding
        col.IsReadOnly = key in ('name', 'status')
        col.Width = DataGridLength(weight, DataGridLengthUnitType.Star)
        grid.Columns.Add(col)
    root.Children.Add(grid)
    current = [None]

    def commit():
        if not grid.CommitEdit(DataGridEditingUnit.Cell, True):
            raise ValueError(tr(u'Завершите редактирование ячейки.', u'Finish editing the cell.'))
        if not grid.CommitEdit(DataGridEditingUnit.Row, True):
            raise ValueError(tr(u'Завершите редактирование строки.', u'Finish editing the row.'))

    def refresh(*args):
        values = List[object]()
        keep_group()
        for row in rows:
            if only_group.IsChecked and (current[0] is None or
                    not core.selected_rows([row.data()], current[0])):
                continue
            if text_search.matches(u' '.join([row.name, row.label or '', row.systems or '', row.groups or '']), search.Text):
                values.Add(row)
        grid.ItemsSource = values

    def keep_group():
        if current[0] is not None:
            current[0]['systems'] = group_systems.Text.strip()

    def switch_group(*args):
        keep_group()
        index = groups.SelectedIndex
        current[0] = data['groups'][index] if index >= 0 else None
        group_systems.Text = current[0].get('systems', '') if current[0] else ''
        refresh()

    def refresh_groups(index=0):
        keep_group()
        current[0] = None
        groups.Items.Clear()
        for g in data['groups']:
            groups.Items.Add(g['name'])
        groups.SelectedIndex = min(index, len(data['groups']) - 1)

    def edit_group(rename=False):
        commit()
        old = current[0]
        if rename and old is None:
            return
        name = forms.ask_for_string(default=old['name'] if rename else '',
                                    prompt=tr(u'Имя списка (без запятых и точек с запятой)', u'List name (no commas or semicolons)'),
                                    title=window.Title)
        if name is None:
            return
        name = name.strip()
        if not name or any(c in name for c in ',;\r\n') or any(g['name'] == name and (not rename or g is not old) for g in data['groups']):
            forms.alert(tr(u'Введите уникальное непустое имя без разделителей.', u'Enter a unique nonempty name without separators.'))
            return
        if rename:
            core.rename_group(list(data['rows'].values()), old['name'], name)
            for row in rows:
                value = row.data()
                core.rename_group([value], old['name'], name)
                row.groups = value['groups']
            old['name'] = name
            index = data['groups'].index(old)
        else:
            data['groups'].append(dict(id=unicode(uuid.uuid4()), name=name, systems='', items=[]))
            index = len(data['groups']) - 1
        refresh_groups(index)
        refresh()

    def delete_group(*args):
        commit()
        group = current[0]
        if group is None:
            return
        if not forms.alert(tr(u'Удалить список? Созданная легенда останется в проекте.',
                              u'Delete the list? Its legend will remain in the project.'), yes=True, no=True):
            return
        for row in rows:
            row.groups = u', '.join(n for n in core.tokens(row.groups) if n != group['name'])
        for row in data['rows'].values():
            row['groups'] = u', '.join(n for n in core.tokens(row.get('groups')) if n != group['name'])
        keep_group()
        current[0] = None
        data['groups'].remove(group)
        refresh_groups()
        refresh()

    button(group_bar, u'Новый', u'New', lambda s, e: edit_group())
    button(group_bar, u'Переименовать', u'Rename', lambda s, e: edit_group(True))
    button(group_bar, u'Удалить', u'Delete', delete_group)

    def assign(*args):
        commit()
        if current[0]:
            for row in list(grid.SelectedItems):
                row.groups = u', '.join(core.tokens(row.groups + u', ' + current[0]['name']))
            refresh()

    def reset_labels(*args):
        commit()
        for row in list(grid.SelectedItems):
            row.label = row.name
        refresh()

    button(bulk, u'Выделенные → в список', u'Add selected to list', assign)
    button(bulk, u'Подпись из имени', u'Label from name', reset_labels)

    def finish(build=False):
        try:
            commit()
            keep_group()
            values = [r.data() for r in rows]
            core.validate(values, data['groups'])
            for field, control in [('row_mm', row_mm), ('gap_mm', gap_mm), ('width_mm', width_mm)]:
                value = float(control.Text.replace(',', '.'))
                if math.isnan(value) or math.isinf(value) or not 0 < value <= 1000:
                    raise ValueError(tr(u'Размеры должны быть больше 0 и не больше 1000 мм.', u'Dimensions must be above 0 and up to 1000 mm.'))
                data[field] = value
            data['scale'] = int(scale.Text)
            if not 1 <= data['scale'] <= 1000:
                raise ValueError(tr(u'Масштаб должен быть от 1 до 1000.', u'Scale must be between 1 and 1000.'))
            data['template_uid'] = template_views[templates.SelectedIndex].UniqueId if templates.SelectedIndex >= 0 else ''
            data['text_uid'] = text_types[texts.SelectedIndex].UniqueId if texts.SelectedIndex >= 0 else ''
            data['rows'].update({r['uid']: r for r in values})
            group = current[0] if build else None
            data['selected_group_id'] = current[0]['id'] if current[0] else ''
            if build and group is None:
                raise ValueError(tr(u'Выберите список.', u'Select a list.'))
            # Missing types are retained in the registry, never silently omitted.
            chosen = core.selected_rows(list(data['rows'].values()), group) if group else []
            result.append((data, group, sorted(chosen, key=lambda r: r['name'].lower())))
            window.Close()
        except Exception as error:
            forms.alert(unicode(error), title=window.Title)

    button(bottom, u'Сохранить списки', u'Save lists', lambda s, e: finish())
    button(bottom, u'Создать / обновить легенду', u'Create / update legend', lambda s, e: finish(True))
    button(bottom, u'Отмена', u'Cancel', lambda s, e: window.Close())
    groups.SelectionChanged += switch_group
    search.TextChanged += refresh
    only_group.Checked += refresh
    only_group.Unchecked += refresh
    group_systems.TextChanged += refresh
    refresh_groups(next((i for i, g in enumerate(data['groups'])
                         if g['id'] == data.get('selected_group_id')), 0))
    refresh()
    window.ShowDialog()
    return result[0] if result else None


def run(uidoc):
    from pyrevit import revit
    doc = uidoc.Document
    try:
        pending = api.load(doc)
    except Exception as error:
        forms.alert(unicode(error), title=tr(u'Списки УГО', u'UGO lists'))
        return
    while True:
        try:
            choice = show(doc, pending)
        except Exception as error:
            forms.alert(unicode(error), title=tr(u'Списки УГО', u'UGO lists'))
            return
        if choice is None:
            return
        data, group, rows = choice
        # build mutates UID mappings; do not retain a rolled-back run's mappings.
        pending = copy.deepcopy(data)
        view = None
        try:
            with revit.Transaction(tr(u'Списки УГО', u'UGO lists')):
                if group is not None:
                    view = api.build(doc, data, group, rows)
                api.save(doc, data)
        except Exception as error:
            forms.alert(unicode(error), title=tr(u'Списки УГО', u'UGO lists'))
            continue
        if view is not None:
            try:
                uidoc.ActiveView = view
            except Exception as error:
                forms.alert(tr(u'Легенда сохранена, но открыть её не удалось: {}',
                               u'The legend was saved but could not be opened: {}').format(error))
        forms.alert(tr(u'Сохранено.', u'Saved.'))
        return
