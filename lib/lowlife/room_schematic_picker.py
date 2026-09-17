# -*- coding: utf-8 -*-
"""
Окно выбора помещений для кнопки Schematic.panel/BuildRoomSchematic
(«Рыба структурной схемы»).

Список помещений приходит от room_finder.get_records(doc) — та же база
(хост + все связи, с кэшем на сессию), что уже использует ToolsRooms.panel/
FindRoom. Пользователь выбирает параметр группировки (ComboBox сверху —
объединение имён параметров, реально встречающихся хоть на одном
помещении), после чего окно строит по одному блоку на уровень (порядок —
sot_levels.sorted_level_names, та же сортировка этажей, что у СОТ/СПС/СКС):
сначала группы — помещения с непустым значением выбранного параметра,
собранные по значению, с чекбоксом «как один бокс» на группу и read-only
списком её помещений под ним; затем — помещения с пустым значением,
каждое своей строкой с отдельным чекбоксом.

Чекбокс группы и чекбоксы отдельных помещений НЕЗАВИСИМЫ друг от друга —
можно отметить и группу целиком, и вдобавок одно из её помещений отдельно
(тогда оно попадёт на схему дважды: в составе группового бокса и своим
собственным) — это осознанно: комбинированный сценарий из ТЗ («на этаже —
общее название по группе, и одновременно несколько отдельных помещений»)
не пытается угадывать, что именно пользователь хочет исключить из группы,
раскладка всё равно черновая и правится руками.

WPF собирается в коде (без XAML) — тот же приём, что и в rename_by_list.py
(там DataGrid, тут набор CheckBox в StackPanel/ScrollViewer): в репозитории
не заведено использовать XAML-файлы для кастомных окон.
"""

from collections import OrderedDict

import clr
clr.AddReference('System')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System.Windows import (
    Window, WindowStartupLocation, Thickness, FontWeights,
    HorizontalAlignment, VerticalAlignment, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, TextBlock, Button, Orientation, DockPanel, Dock,
    CheckBox, ComboBox, ScrollViewer, ScrollBarVisibility, Separator
)
from System.Windows.Media import Brushes

from lowlife.params import get_param_any
from lowlife.sot_levels import sorted_level_names, get_level_label

_NO_GROUPING = u"(без группировки)"


def list_room_param_names(records):
    """
    Отсортированный список имён параметров, встречающихся хотя бы на одном
    помещении из records — для ComboBox выбора параметра группировки.
    Объединение (не пересечение): у части помещений (особенно из разных
    связей/типов) набор параметров может отличаться, показываем всё, что
    вообще где-то есть, а не только общее для всех сразу.
    """
    names = set()
    for record in records:
        try:
            for p in record.room.Parameters:
                name = p.Definition.Name if p and p.Definition else None
                if name:
                    names.add(name)
        except Exception:
            continue
    return sorted(names, key=lambda n: n.lower())


def _room_label(record):
    number = (record.number or u"").strip()
    name = (record.name or u"").strip()
    if number and name:
        return u"{} {}".format(number, name)
    return number or name or u"(без имени)"


def _build_level_groups(records):
    """
    OrderedDict(level_name -> {"elements": [...], "level": Level|None,
    "order": int}) — форма, ожидаемая sot_levels.sorted_level_names.
    Level берётся с самого room (record.room.Level) — он резолвится Revit
    API на родном документе помещения (хост или связь), поэтому безопасен
    и для помещений из связи, в отличие от doc.GetElement(record.room.LevelId)
    на документе-хосте (см. sot_levels.group_elements_by_level — та функция
    для этого случая не подходит).
    """
    groups = OrderedDict()
    for index, record in enumerate(records):
        name = record.level_name or u"Без уровня"
        if name not in groups:
            level = None
            try:
                level = record.room.Level
            except Exception:
                level = None
            groups[name] = {"elements": [], "level": level, "order": index}
        groups[name]["elements"].append(record)
    return groups


def _group_records_by_param(records, param_name):
    """
    (groups, singles) для одного уровня: groups — OrderedDict(value ->
    [record, ...]) для непустых значений param_name (в порядке первого
    появления), singles — записи с пустым/отсутствующим значением.
    param_name=None -> всё в singles (группировка выключена).
    """
    groups = OrderedDict()
    singles = []
    for record in records:
        value = get_param_any(record.room, param_name) if param_name else None
        value = value.strip() if value else u""
        if value:
            groups.setdefault(value, []).append(record)
        else:
            singles.append(record)
    return groups, singles


class _RoomRow(object):
    __slots__ = ("record", "checkbox")

    def __init__(self, record, checkbox):
        self.record = record
        self.checkbox = checkbox


class _GroupRow(object):
    __slots__ = ("value", "records", "checkbox")

    def __init__(self, value, records, checkbox):
        self.value = value
        self.records = records
        self.checkbox = checkbox


def show(doc, records):
    """
    Показывает окно выбора. Возвращает OrderedDict(level_name -> [box, ...])
    (box = {"kind": "group"|"room", "label": unicode, "room_ids": [int, ...]})
    по нажатию «Построить», либо None по «Отмена»/закрытию окна.
    """
    if not records:
        return None

    level_groups = _build_level_groups(records)
    level_order = sorted_level_names(level_groups)
    param_names = list_room_param_names(records)

    result = {"boxes": None}
    # level_name -> list of _GroupRow/_RoomRow, перестраивается при смене
    # параметра группировки в _rebuild_body.
    level_rows = {}

    win = Window()
    win.Title = u"Рыба структурной схемы — выбор помещений"
    win.Width = 620
    win.Height = 720
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.Margin = Thickness(16)

    header = StackPanel()
    header.Margin = Thickness(0, 0, 0, 10)
    DockPanel.SetDock(header, Dock.Top)

    title = TextBlock()
    title.Text = u"Выбор помещений и групп по этажам"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    header.Children.Add(title)

    info = TextBlock()
    info.Text = (
        u"Параметр группировки — общее значение, по которому несколько "
        u"помещений объединяются в один бокс схемы (например «Название "
        u"группы»). Отметьте группу целиком чекбоксом рядом с её "
        u"значением, и/или отдельные помещения — независимо друг от друга: "
        u"можно добавить группу и вдобавок отдельное помещение из неё же."
    )
    info.FontSize = 11
    info.TextWrapping = TextWrapping.Wrap
    info.Margin = Thickness(0, 4, 0, 8)
    header.Children.Add(info)

    param_row = StackPanel()
    param_row.Orientation = Orientation.Horizontal
    param_label = TextBlock()
    param_label.Text = u"Параметр группировки: "
    param_label.VerticalAlignment = VerticalAlignment.Center
    param_row.Children.Add(param_label)

    combo = ComboBox()
    combo.Width = 320
    combo.Items.Add(_NO_GROUPING)
    for name in param_names:
        combo.Items.Add(name)
    combo.SelectedIndex = 0
    param_row.Children.Add(combo)

    recalc_btn = Button()
    recalc_btn.Content = u"Пересчитать группы"
    recalc_btn.Margin = Thickness(10, 0, 0, 0)
    recalc_btn.Padding = Thickness(8, 2, 8, 2)
    param_row.Children.Add(recalc_btn)

    header.Children.Add(param_row)

    body_panel = StackPanel()

    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scroll.Content = body_panel
    scroll.Margin = Thickness(0, 0, 0, 10)

    bottom = StackPanel()
    bottom.Orientation = Orientation.Horizontal
    bottom.HorizontalAlignment = HorizontalAlignment.Right
    bottom.Margin = Thickness(0, 8, 0, 0)
    DockPanel.SetDock(bottom, Dock.Bottom)

    cancel_btn = Button()
    cancel_btn.Content = u"Отмена"
    cancel_btn.Padding = Thickness(12, 4, 12, 4)
    cancel_btn.Margin = Thickness(0, 0, 8, 0)

    ok_btn = Button()
    ok_btn.Content = u"Построить"
    ok_btn.Padding = Thickness(12, 4, 12, 4)
    ok_btn.FontWeight = FontWeights.Bold

    bottom.Children.Add(cancel_btn)
    bottom.Children.Add(ok_btn)

    def _rebuild_body(sender=None, args=None):
        body_panel.Children.Clear()
        level_rows.clear()

        selected = combo.SelectedItem
        param_name = None if (selected is None or selected == _NO_GROUPING) else unicode(selected)

        for level_name in level_order:
            level_records = level_groups[level_name]["elements"]
            groups, singles = _group_records_by_param(level_records, param_name)

            if not groups and not singles:
                continue

            level_header = TextBlock()
            level_header.Text = get_level_label(level_name)
            level_header.FontWeight = FontWeights.Bold
            level_header.FontSize = 13
            level_header.Margin = Thickness(0, 12, 0, 4)
            body_panel.Children.Add(level_header)
            body_panel.Children.Add(Separator())

            rows = []

            for value, group_records in groups.items():
                group_cb = CheckBox()
                group_cb.Content = u"{} ({} пом.) — как один бокс".format(value, len(group_records))
                group_cb.FontWeight = FontWeights.SemiBold
                group_cb.Margin = Thickness(4, 6, 0, 2)
                body_panel.Children.Add(group_cb)
                rows.append(_GroupRow(value, group_records, group_cb))

                members_text = u", ".join(_room_label(r) for r in group_records)
                members_block = TextBlock()
                members_block.Text = members_text
                members_block.TextWrapping = TextWrapping.Wrap
                members_block.Foreground = Brushes.Gray
                members_block.FontSize = 11
                members_block.Margin = Thickness(24, 0, 0, 4)
                body_panel.Children.Add(members_block)

            for record in singles:
                room_cb = CheckBox()
                room_cb.Content = _room_label(record)
                room_cb.Margin = Thickness(4, 2, 0, 2)
                body_panel.Children.Add(room_cb)
                rows.append(_RoomRow(record, room_cb))

            level_rows[level_name] = rows

    recalc_btn.Click += _rebuild_body

    def on_cancel(sender, args):
        win.Close()

    def on_ok(sender, args):
        boxes = OrderedDict()
        for level_name in level_order:
            rows = level_rows.get(level_name, [])
            level_boxes = []
            for row in rows:
                if not row.checkbox.IsChecked:
                    continue
                if isinstance(row, _GroupRow):
                    level_boxes.append({
                        "kind": "group",
                        "label": row.value,
                        "room_ids": [r.room_id for r in row.records if r.room_id is not None],
                    })
                else:
                    level_boxes.append({
                        "kind": "room",
                        "label": _room_label(row.record),
                        "room_ids": [row.record.room_id] if row.record.room_id is not None else [],
                    })
            if level_boxes:
                boxes[level_name] = level_boxes

        if not boxes:
            from pyrevit import forms
            forms.alert(u"Не выбрано ни одного помещения/группы.",
                        title=u"Рыба структурной схемы")
            return

        result["boxes"] = boxes
        win.Close()

    cancel_btn.Click += on_cancel
    ok_btn.Click += on_ok

    outer.Children.Add(header)
    outer.Children.Add(bottom)
    outer.Children.Add(scroll)
    win.Content = outer

    _rebuild_body()

    win.ShowDialog()

    return result["boxes"]
