# -*- coding: utf-8 -*-
"""
Окно настроек кнопки «Виды по уровням» (Tools.panel/LevelViews): слева —
список групп видов (добавить/копировать/удалить/переставить), справа —
поля выбранной группы, сверху — шаблон имени уровня. Хранение —
level_views_settings.py, проверка — level_views_core.
"""

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from pyrevit import forms

from lowlife import level_name_template, settings_transfer
from lowlife import level_views, level_views_core as core

from System.Windows import (
    Window, WindowStartupLocation, Thickness, FontWeights,
    HorizontalAlignment, TextWrapping, GridLength, GridUnitType
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, Orientation, ComboBox, CheckBox,
    DockPanel, Dock, Grid, ColumnDefinition, ListBox, ScrollViewer,
    ScrollBarVisibility
)
from System.Windows.Media import Brushes

TITLE = u"Виды по уровням"
NO_TEMPLATE = u"<Без шаблона>"
DEFAULT_TYPE = u"<Первый тип «План этажа»>"
MISSING = u" (нет в проекте)"

_GROUPS_KEY = "groups"
_LEVEL_TEMPLATE_KEY = "level_name_template"


def _label(parent, text, bold=False, top=10):
    tb = TextBlock()
    tb.Text = text
    tb.TextWrapping = TextWrapping.Wrap
    tb.Margin = Thickness(0, top, 0, 2)
    if bold:
        tb.FontWeight = FontWeights.Bold
    parent.Children.Add(tb)
    return tb


def _hint(parent, text):
    tb = TextBlock()
    tb.Text = text
    tb.FontSize = 11
    tb.Foreground = Brushes.Gray
    tb.TextWrapping = TextWrapping.Wrap
    tb.Margin = Thickness(0, 2, 0, 0)
    parent.Children.Add(tb)
    return tb


def _textbox(parent, text=u""):
    tb = TextBox()
    tb.Text = text
    tb.Padding = Thickness(4)
    parent.Children.Add(tb)
    return tb


def _button(parent, text, handler, bold=False, right=6):
    b = Button()
    b.Content = text
    b.Padding = Thickness(10, 4, 10, 4)
    b.Margin = Thickness(0, 0, right, 0)
    if bold:
        b.FontWeight = FontWeights.Bold
    b.Click += handler
    parent.Children.Add(b)
    return b


def _range_row(parent, label):
    row = DockPanel()
    row.Margin = Thickness(0, 4, 0, 0)
    tb = TextBlock()
    tb.Text = label
    tb.Width = 300
    tb.TextWrapping = TextWrapping.Wrap
    DockPanel.SetDock(tb, Dock.Left)
    row.Children.Add(tb)
    box = TextBox()
    box.Padding = Thickness(4)
    row.Children.Add(box)
    parent.Children.Add(row)
    return box


class _Combo(object):
    """ComboBox, в который можно поставить значение, которого нет в списке."""

    def __init__(self, parent, items, empty_label):
        self.items = list(items)
        self.empty_label = empty_label
        self.cb = ComboBox()
        parent.Children.Add(self.cb)

    def set(self, value):
        self.cb.Items.Clear()
        self.cb.Items.Add(self.empty_label)
        for item in self.items:
            self.cb.Items.Add(item)
        if not value:
            self.cb.SelectedIndex = 0
        elif value in self.items:
            self.cb.SelectedIndex = self.items.index(value) + 1
        else:
            self.cb.Items.Add(value + MISSING)
            self.cb.SelectedIndex = self.cb.Items.Count - 1

    def get(self):
        item = self.cb.SelectedItem
        if item is None or item == self.empty_label:
            return u""
        item = unicode(item)
        if item.endswith(MISSING):
            item = item[:-len(MISSING)]
        return item


def show_settings_form(doc, values, read_all, write_all):
    """
    Модальное окно. Возвращает {groups, level_name_template}, None при
    отмене или settings_transfer.RELOAD после загрузки настроек из файла.
    """
    type_labels = [lbl for lbl, _vft in level_views.list_plan_types(doc)]
    template_names = [level_views.safe_name(t) for t in level_views.list_plan_templates(doc)]
    groups = [dict(g) for g in values.get(_GROUPS_KEY) or []]
    state = {"index": -1, "loading": False}
    result = {"values": None}

    win = Window()
    win.Title = u"Настройки: " + TITLE
    win.Width = 980
    win.Height = 760
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.Margin = Thickness(16, 12, 16, 12)

    # --- шапка: заголовок и шаблон имени уровня --------------------------------
    header = StackPanel()
    DockPanel.SetDock(header, Dock.Top)
    title = TextBlock()
    title.Text = TITLE
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    header.Children.Add(title)
    _hint(header, u"Группа видов — один вид на каждый выбранный уровень: тип вида, маска "
                  u"имени, шаблон, секущий диапазон, связи. При запуске кнопки выбираются "
                  u"уровни и группы. Вид, который уже есть (то же имя на том же уровне), "
                  u"не создаётся заново — ему заново назначаются шаблон, диапазон и связи.")
    _label(header, u"Шаблон имени уровня", bold=True)
    level_tpl_box = _textbox(header, values.get(_LEVEL_TEMPLATE_KEY) or u"")
    _hint(header, u"Откуда брать {Корпус}, {Этаж} и {Комментарий} для маски имени и как "
                  u"искать следующий этаж (верх диапазона) — тот же формат, что у кнопки "
                  u"«Секущий диапазон», например «{Дисциплина}_{Корпус}_{Отметка}_{Этаж}_"
                  u"{Комментарий}» или «Этаж {Этаж}».")

    # --- низ: кнопки --------------------------------------------------------------
    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(0, 12, 0, 0)
    DockPanel.SetDock(buttons, Dock.Bottom)

    # --- середина: список групп + поля группы ------------------------------------
    grid = Grid()
    grid.Margin = Thickness(0, 12, 0, 0)
    left_col = ColumnDefinition()
    left_col.Width = GridLength(260)
    right_col = ColumnDefinition()
    right_col.Width = GridLength(1, GridUnitType.Star)
    grid.ColumnDefinitions.Add(left_col)
    grid.ColumnDefinitions.Add(right_col)

    left = DockPanel()
    left.Margin = Thickness(0, 0, 12, 0)
    Grid.SetColumn(left, 0)
    left_title = TextBlock()
    left_title.Text = u"Группы видов"
    left_title.FontWeight = FontWeights.Bold
    left_title.Margin = Thickness(0, 0, 0, 4)
    DockPanel.SetDock(left_title, Dock.Top)
    left.Children.Add(left_title)

    list_buttons = StackPanel()
    list_buttons.Margin = Thickness(0, 6, 0, 0)
    DockPanel.SetDock(list_buttons, Dock.Bottom)
    row1 = StackPanel()
    row1.Orientation = Orientation.Horizontal
    row2 = StackPanel()
    row2.Orientation = Orientation.Horizontal
    row2.Margin = Thickness(0, 6, 0, 0)
    list_buttons.Children.Add(row1)
    list_buttons.Children.Add(row2)
    left.Children.Add(list_buttons)

    group_list = ListBox()
    left.Children.Add(group_list)
    grid.Children.Add(left)

    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    Grid.SetColumn(scroll, 1)
    editor = StackPanel()
    editor.Margin = Thickness(0, 0, 8, 0)
    scroll.Content = editor
    grid.Children.Add(scroll)

    empty_note = _hint(editor, u"Групп пока нет — нажмите «Добавить».")

    fields = StackPanel()
    editor.Children.Add(fields)

    _label(fields, u"Имя группы", bold=True, top=0)
    name_box = _textbox(fields)
    _hint(fields, u"Под этим именем группа показывается при запуске; подстановка {Группа} "
                  u"в маске имени.")

    _label(fields, u"Тип вида", bold=True)
    type_combo = _Combo(fields, type_labels, DEFAULT_TYPE)
    _hint(fields, u"План этажа, план потолка или план несущих конструкций — от типа "
                  u"зависит папка в Диспетчере проекта.")

    _label(fields, u"Маска имени вида", bold=True)
    mask_box = _textbox(fields)
    _hint(fields, u"Подстановки: {Уровень} — имя уровня; {Этаж}, {Корпус}, {Комментарий} — "
                  u"части имени уровня по шаблону выше; {Отметка} — отметка уровня "
                  u"(«+3.300»); {Группа} — имя группы. Например «{Этаж} этаж. ЭОМ» или "
                  u"«{Группа}_{Уровень}».")

    _label(fields, u"Шаблон вида", bold=True)
    template_combo = _Combo(fields, template_names, NO_TEMPLATE)
    _hint(fields, u"Назначается каждому виду группы (шаблоны планов этажа, потолка, "
                  u"несущих конструкций).")

    _label(fields, u"Секущий диапазон, мм", bold=True, top=14)
    _hint(fields, u"Пустое поле — эта плоскость не меняется. Если диапазон задаёт шаблон "
                  u"вида — диапазон не трогается (будет в отчёте).")
    top_box = _range_row(fields, u"Верх — от следующего этажа (выше нет — «Неограниченно»)")
    cut_box = _range_row(fields, u"Секущая плоскость — от уровня вида")
    bottom_box = _range_row(fields, u"Низ — от уровня вида")
    depth_box = _range_row(fields, u"Глубина — от уровня вида (пусто — как низ)")

    _label(fields, u"Связанные модели", bold=True, top=14)
    links_cb = CheckBox()
    links_cb.Content = u"Показывать связи «По связанному виду»"
    fields.Children.Add(links_cb)
    _hint(fields, u"В настройке «Связи RVT» вида связь показывается «По связанному виду» — "
                  u"по плану связи, выбранному для этого уровня. Нужен Revit 2024+, а "
                  u"шаблон вида не должен управлять «Связями RVT».")
    _label(fields, u"Какие связи: имя содержит (через запятую; пусто — все загруженные)")
    link_filter_box = _textbox(fields)
    _label(fields, u"Фильтр видов связи")
    filter_row = DockPanel()
    mode_cb = ComboBox()
    mode_cb.Width = 190
    for _key, lbl in core.LINK_VIEW_MODES:
        mode_cb.Items.Add(lbl)
    DockPanel.SetDock(mode_cb, Dock.Left)
    filter_row.Children.Add(mode_cb)
    link_view_box = TextBox()
    link_view_box.Padding = Thickness(4)
    link_view_box.Margin = Thickness(8, 0, 0, 0)
    filter_row.Children.Add(link_view_box)
    fields.Children.Add(filter_row)
    _hint(fields, u"Из планов связи, прошедших фильтр, для каждого вида берётся план на "
                  u"таком же уровне связи: с тем же именем уровня, иначе тот же корпус и "
                  u"этаж (по шаблону имени уровня выше), иначе ближайший по отметке (до "
                  u"1500 мм). Например «Начинается с» «2_СС-АР». Несколько значений — через "
                  u"запятую; регистр не важен; можно с подстановками уровня ({Этаж}, "
                  u"{Корпус}, {Уровень}, {Отметка}).")
    pick_cb = CheckBox()
    pick_cb.Content = u"Показывать окно выбора видов связи перед созданием"
    pick_cb.Margin = Thickness(0, 8, 0, 0)
    fields.Children.Add(pick_cb)
    _hint(fields, u"Таблица «уровень × связь» с подобранными планами — можно проверить и "
                  u"поменять. Без галочки виды подбираются сами, что выбрано — видно в отчёте.")

    def _sync_links_enabled(*_args):
        on = bool(links_cb.IsChecked)
        link_filter_box.IsEnabled = on
        link_view_box.IsEnabled = on
        mode_cb.IsEnabled = on
        pick_cb.IsEnabled = on

    links_cb.Checked += _sync_links_enabled
    links_cb.Unchecked += _sync_links_enabled

    # --- перенос значений группа <-> поля -----------------------------------------
    def form_fields():
        return {
            core.G_NAME: name_box.Text,
            core.G_VIEW_TYPE: type_combo.get(),
            core.G_NAME_MASK: mask_box.Text,
            core.G_TEMPLATE: template_combo.get(),
            core.G_TOP: top_box.Text,
            core.G_CUT: cut_box.Text,
            core.G_BOTTOM: bottom_box.Text,
            core.G_DEPTH: depth_box.Text,
            core.G_LINKS: bool(links_cb.IsChecked),
            core.G_LINK_FILTER: link_filter_box.Text,
            core.G_LINK_VIEW_MODE: core.mode_by_label(unicode(mode_cb.SelectedItem or u"")),
            core.G_LINK_VIEW_FILTER: link_view_box.Text,
            core.G_LINK_PICK_DIALOG: bool(pick_cb.IsChecked),
        }

    # Тексты полей диапазона хранятся как ввёл пользователь, до «Сохранить»
    # (проверка чисел — в on_ok), поэтому в группе — словарь «как в окне».
    drafts = [None] * len(groups)

    def load(index):
        state["loading"] = True
        try:
            has = 0 <= index < len(groups)
            fields.Visibility = _visible(has)
            empty_note.Visibility = _visible(not groups)
            if not has:
                return
            g = drafts[index] or _to_form(groups[index])
            name_box.Text = g[core.G_NAME]
            type_combo.set(g[core.G_VIEW_TYPE])
            mask_box.Text = g[core.G_NAME_MASK]
            template_combo.set(g[core.G_TEMPLATE])
            top_box.Text = g[core.G_TOP]
            cut_box.Text = g[core.G_CUT]
            bottom_box.Text = g[core.G_BOTTOM]
            depth_box.Text = g[core.G_DEPTH]
            links_cb.IsChecked = bool(g[core.G_LINKS])
            link_filter_box.Text = g[core.G_LINK_FILTER]
            link_view_box.Text = g[core.G_LINK_VIEW_FILTER]
            mode_cb.SelectedItem = core.mode_label(g[core.G_LINK_VIEW_MODE])
            pick_cb.IsChecked = bool(g[core.G_LINK_PICK_DIALOG])
            _sync_links_enabled()
        finally:
            state["loading"] = False

    def commit():
        index = state["index"]
        if 0 <= index < len(groups):
            drafts[index] = form_fields()

    def refresh_list(select):
        state["loading"] = True
        try:
            group_list.Items.Clear()
            for i, g in enumerate(groups):
                name = (drafts[i] or {}).get(core.G_NAME) or g[core.G_NAME]
                group_list.Items.Add(name)
            group_list.SelectedIndex = select
        finally:
            state["loading"] = False
        state["index"] = select
        load(select)

    def on_select(sender, args):
        if state["loading"]:
            return
        commit()
        state["index"] = group_list.SelectedIndex
        load(state["index"])

    def on_name_changed(sender, args):
        index = state["index"]
        if state["loading"] or not (0 <= index < len(groups)):
            return
        state["loading"] = True
        try:
            group_list.Items[index] = name_box.Text
            group_list.SelectedIndex = index
        finally:
            state["loading"] = False

    group_list.SelectionChanged += on_select
    name_box.TextChanged += on_name_changed

    def _taken_names():
        return [(drafts[i] or {}).get(core.G_NAME) or g[core.G_NAME]
                for i, g in enumerate(groups)]

    def on_add(sender, args):
        commit()
        g = core.normalize_group({})
        g[core.G_NAME] = core.unique_group_name(g[core.G_NAME], _taken_names())
        groups.append(g)
        drafts.append(None)
        refresh_list(len(groups) - 1)

    def on_copy(sender, args):
        index = state["index"]
        if not (0 <= index < len(groups)):
            return
        commit()
        draft = dict(drafts[index] or _to_form(groups[index]))
        draft[core.G_NAME] = core.unique_group_name(draft[core.G_NAME], _taken_names())
        groups.insert(index + 1, dict(groups[index]))
        drafts.insert(index + 1, draft)
        refresh_list(index + 1)

    def on_delete(sender, args):
        index = state["index"]
        if not (0 <= index < len(groups)):
            return
        del groups[index]
        del drafts[index]
        state["index"] = -1
        refresh_list(min(index, len(groups) - 1))

    def on_move(step):
        def handler(sender, args):
            index = state["index"]
            other = index + step
            if not (0 <= index < len(groups)) or not (0 <= other < len(groups)):
                return
            commit()
            groups[index], groups[other] = groups[other], groups[index]
            drafts[index], drafts[other] = drafts[other], drafts[index]
            refresh_list(other)
        return handler

    _button(row1, u"Добавить", on_add)
    _button(row1, u"Копия", on_copy)
    _button(row1, u"Удалить", on_delete, right=0)
    _button(row2, u"Выше ↑", on_move(-1))
    _button(row2, u"Ниже ↓", on_move(1), right=0)

    # --- сохранение -------------------------------------------------------------
    def on_ok(sender, args):
        commit()
        errors = []
        level_tpl = (level_tpl_box.Text or u"").strip()
        tpl_error = level_name_template.validate(level_tpl)
        if tpl_error:
            errors.append(u"Шаблон имени уровня: {}".format(tpl_error))

        final = []
        first_bad = None
        for i, g in enumerate(groups):
            group, group_errors = core.group_from_form(drafts[i] or _to_form(g))
            final.append(group)
            if group_errors and first_bad is None:
                first_bad = i
            errors.extend(u"Группа «{}»: {}".format(group[core.G_NAME], e)
                          for e in group_errors)
        for i, error in core.validate_groups(final):
            if first_bad is None:
                first_bad = i
            errors.append(u"Группа «{}»: {}".format(final[i][core.G_NAME], error))

        if errors:
            if first_bad is not None and first_bad != state["index"]:
                refresh_list(first_bad)
            forms.alert(u"\n".join(errors), title=TITLE)
            return
        result["values"] = {_GROUPS_KEY: final, _LEVEL_TEMPLATE_KEY: level_tpl}
        win.Close()

    def on_cancel(sender, args):
        win.Close()

    _button(buttons, u"Отмена", on_cancel, right=8)
    _button(buttons, u"Сохранить", on_ok, bold=True, right=0)

    def _on_settings_imported():
        result["values"] = settings_transfer.RELOAD
        win.Close()

    settings_transfer.add_transfer_buttons(
        buttons, read_all, write_all, u"видов по уровням", _on_settings_imported)

    outer.Children.Add(header)
    outer.Children.Add(buttons)
    outer.Children.Add(grid)
    win.Content = outer

    refresh_list(0 if groups else -1)
    win.ShowDialog()
    return result["values"]


def _to_form(group):
    """Группа → значения полей окна (числа диапазона — текстом)."""
    form = dict(group)
    for key in core.RANGE_KEYS:
        form[key] = core.format_mm(group.get(key))
    return form


def _visible(flag):
    from System.Windows import Visibility
    return Visibility.Visible if flag else Visibility.Collapsed
