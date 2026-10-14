# -*- coding: utf-8 -*-
"""
Окно кнопки «Виды по уровням» (Tools.panel/LevelViews): маска имени вида,
список шаблонов видов планов (галочка «создать» + своя «Группа вида и
назначение» у каждого) и предпросмотр имён на первом уровне. Логика имён —
level_views_core, создание видов — level_views.
"""

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from pyrevit import forms

from lowlife import geometry, level_views, level_views_core as core, settings_transfer

from System.Windows import (
    Window, WindowStartupLocation, Thickness, FontWeights,
    HorizontalAlignment, VerticalAlignment, TextWrapping, GridLength,
    GridUnitType
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, Orientation, CheckBox, DockPanel,
    Dock, Grid, ColumnDefinition, RowDefinition, ScrollViewer,
    ScrollBarVisibility
)
from System.Windows.Media import Brushes

TITLE = u"Виды по уровням"
_PREVIEW_MAX = 8


def _hint(parent, text, top=2):
    tb = TextBlock()
    tb.Text = text
    tb.FontSize = 11
    tb.Foreground = Brushes.Gray
    tb.TextWrapping = TextWrapping.Wrap
    tb.Margin = Thickness(0, top, 0, 0)
    parent.Children.Add(tb)
    return tb


def _place(grid, element, row, col):
    Grid.SetRow(element, row)
    Grid.SetColumn(element, col)
    grid.Children.Add(element)


def _button(parent, text, handler, bold=False):
    b = Button()
    b.Content = text
    b.Padding = Thickness(10, 4, 10, 4)
    b.Margin = Thickness(8, 0, 0, 0)
    if bold:
        b.FontWeight = FontWeights.Bold
    b.Click += handler
    parent.Children.Add(b)
    return b


# Подстановки маски: (подстановка, что в неё попадёт).
_TOKEN_HELP = (
    (u"{Группа вида и назначение}", u"то, что вписано у шаблона в списке ниже"),
    (u"{Уровень}", u"имя уровня целиком"),
    (u"{Корпус}, {Этаж}, {Комментарий}",
     u"части имени уровня — как их выделять, задаёт шаблон имени уровня в настройках "
     u"кнопки «Секущий диапазон» (Shift+клик); не подходит под шаблон — пусто"),
    (u"{Отметка}", u"отметка уровня, например «+3.300»"),
    (u"{Шаблон}", u"имя шаблона вида"),
)


def _tokens_table(parent):
    """Подстановки маски — по одной на строке: слева подстановка, справа пояснение."""
    grid = Grid()
    grid.Margin = Thickness(8, 2, 0, 0)
    for width in (GridLength(1, GridUnitType.Auto), GridLength(1, GridUnitType.Star)):
        col = ColumnDefinition()
        col.Width = width
        grid.ColumnDefinitions.Add(col)
    for i, (token, text) in enumerate(_TOKEN_HELP):
        grid.RowDefinitions.Add(RowDefinition())
        name = TextBlock()
        name.Text = token
        name.FontSize = 11
        name.Margin = Thickness(0, 1, 12, 1)
        _place(grid, name, i, 0)
        desc = TextBlock()
        desc.Text = text
        desc.FontSize = 11
        desc.Foreground = Brushes.Gray
        desc.TextWrapping = TextWrapping.Wrap
        desc.Margin = Thickness(0, 1, 0, 1)
        _place(grid, desc, i, 1)
    parent.Children.Add(grid)


class _Row(object):
    def __init__(self, template, check, value_box):
        self.template = template
        self.name = level_views.safe_name(template)
        self.check = check
        self.value_box = value_box

    def checked(self):
        return bool(self.check.IsChecked)

    def values(self):
        """Группы вида и назначения — по одной на строке."""
        return core.split_values(self.value_box.Text)


def show(doc, templates, levels, settings, level_template, store):
    """
    Окно. store — level_views_settings (save/read_all/write_all — для
    кнопок «Сохранить» и выгрузки/загрузки настроек).

    Возвращает словарь {"action": "run" | "save", "mask", "items" —
    [(шаблон, значение)], "values" — {шаблон: текст групп}, "checked" —
    [имена отмеченных шаблонов], "align", "pick_levels"}, settings_transfer.RELOAD после
    загрузки настроек из файла (окно открыть заново) или None при отмене.
    """
    saved_values = settings[core.VALUES_KEY]
    checked = set(settings[core.CHECKED_KEY])
    first_values = level_views.level_values(levels[0], level_template) if levels else {}
    result = {"value": None}

    win = Window()
    win.Title = TITLE
    win.Width = 760
    win.Height = 800
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.Margin = Thickness(16, 12, 16, 12)

    # --- шапка: маска -------------------------------------------------------------
    header = StackPanel()
    DockPanel.SetDock(header, Dock.Top)
    title = TextBlock()
    title.Text = TITLE
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    header.Children.Add(title)
    _hint(header, u"Для каждого отмеченного шаблона вида создаётся план на каждом уровне "
                  u"модели (уровней: {}) с этим шаблоном. Вид с таким же именем на том же "
                  u"уровне не создаётся заново — ему назначается шаблон.".format(len(levels)))

    mask_label = TextBlock()
    mask_label.Text = u"Маска имени вида"
    mask_label.FontWeight = FontWeights.Bold
    mask_label.Margin = Thickness(0, 12, 0, 2)
    header.Children.Add(mask_label)
    mask_box = TextBox()
    mask_box.Padding = Thickness(4)
    mask_box.Text = settings[core.MASK_KEY]
    header.Children.Add(mask_box)
    _hint(header, u"По умолчанию: «{}». Другой пример: «{{Этаж}} этаж. {{Группа вида и "
                  u"назначение}}».".format(core.DEFAULT_MASK), top=4)
    _hint(header, u"Подстановки:", top=6)
    _tokens_table(header)
    outer.Children.Add(header)

    # --- низ: предпросмотр и кнопки -----------------------------------------------
    bottom = StackPanel()
    DockPanel.SetDock(bottom, Dock.Bottom)
    preview_title = TextBlock()
    preview_title.FontWeight = FontWeights.Bold
    preview_title.Margin = Thickness(0, 10, 0, 2)
    bottom.Children.Add(preview_title)
    preview = TextBlock()
    preview.TextWrapping = TextWrapping.Wrap
    bottom.Children.Add(preview)

    align_cb = CheckBox()
    align_cb.Content = u"Выровнять секущий диапазон (как кнопка «Секущий диапазон»)"
    align_cb.IsChecked = bool(settings[core.ALIGN_RANGE_KEY])
    align_cb.Margin = Thickness(0, 12, 0, 0)
    bottom.Children.Add(align_cb)
    pick_cb = CheckBox()
    pick_cb.Content = u"Выбирать уровни для каждого шаблона"
    pick_cb.IsChecked = bool(settings[core.PICK_LEVELS_KEY])
    pick_cb.Margin = Thickness(0, 6, 0, 0)
    bottom.Children.Add(pick_cb)
    _hint(bottom, u"После «Создать виды» для каждого отмеченного шаблона по очереди откроется "
                  u"список уровней модели — отметьте, для каких уровней создавать его виды. "
                  u"Выбор запоминается для каждого шаблона. Без галочки — все уровни.")
    _hint(bottom, u"Низ и глубина — уровень вида; секущая плоскость +1200 мм (низкий этаж — "
                  u"+900); верх — следующий этаж −200 мм. Если настройка «Секущего "
                  u"диапазона» ещё не заполнена — она откроется перед созданием видов. "
                  u"Планы потолков и виды, чей диапазон задаёт шаблон, не меняются.")

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(0, 12, 0, 0)
    bottom.Children.Add(buttons)
    outer.Children.Add(bottom)

    # --- середина: шаблоны ---------------------------------------------------------
    middle = DockPanel()
    middle.Margin = Thickness(0, 12, 0, 0)

    list_head = DockPanel()
    DockPanel.SetDock(list_head, Dock.Top)
    list_title = TextBlock()
    list_title.Text = u"Шаблоны видов"
    list_title.FontWeight = FontWeights.Bold
    list_title.VerticalAlignment = VerticalAlignment.Center
    list_head.Children.Add(list_title)
    select_buttons = StackPanel()
    select_buttons.Orientation = Orientation.Horizontal
    select_buttons.HorizontalAlignment = HorizontalAlignment.Right
    list_head.Children.Add(select_buttons)
    middle.Children.Add(list_head)
    multi_hint = TextBlock()
    multi_hint.Text = (u"У шаблона может быть несколько групп вида и назначения — по одной на "
                       u"строке (Enter); на каждую создаётся свой вид на каждом уровне.")
    multi_hint.FontSize = 11
    multi_hint.Foreground = Brushes.Gray
    multi_hint.TextWrapping = TextWrapping.Wrap
    multi_hint.Margin = Thickness(0, 2, 0, 0)
    DockPanel.SetDock(multi_hint, Dock.Top)
    middle.Children.Add(multi_hint)

    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scroll.Margin = Thickness(0, 6, 0, 0)
    grid = Grid()
    scroll.Content = grid
    middle.Children.Add(scroll)
    outer.Children.Add(middle)

    for width in (GridLength(1, GridUnitType.Star), GridLength(150),
                  GridLength(1, GridUnitType.Star)):
        col = ColumnDefinition()
        col.Width = width
        grid.ColumnDefinitions.Add(col)

    grid.RowDefinitions.Add(RowDefinition())
    for col, text in enumerate((u"Шаблон вида", u"Вид", u"Группа вида и назначение")):
        head = TextBlock()
        head.Text = text
        head.Foreground = Brushes.Gray
        head.Margin = Thickness(0, 0, 8, 4)
        _place(grid, head, 0, col)

    rows = []
    for i, template in enumerate(templates):
        grid.RowDefinitions.Add(RowDefinition())
        name = level_views.safe_name(template)
        check = CheckBox()
        check.Content = name
        check.IsChecked = name in checked
        check.VerticalAlignment = VerticalAlignment.Top
        check.Margin = Thickness(0, 6, 8, 3)
        _place(grid, check, i + 1, 0)
        kind = TextBlock()
        kind.Text = level_views.KIND_LABELS.get(template.ViewType, u"")
        kind.Foreground = Brushes.Gray
        kind.VerticalAlignment = VerticalAlignment.Top
        kind.Margin = Thickness(0, 6, 8, 3)
        _place(grid, kind, i + 1, 1)
        value_box = TextBox()
        value_box.Padding = Thickness(3)
        value_box.Margin = Thickness(0, 3, 0, 3)
        value_box.AcceptsReturn = True
        value_box.TextWrapping = TextWrapping.Wrap
        value_box.MinHeight = 24
        value_box.MaxHeight = 160
        value_box.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
        # Без предзаполнения: пусто, пока не вписано. Сохранённое значение,
        # равное имени шаблона, — прежнее предзаполнение, тоже не показывается.
        saved = saved_values.get(name, u"")
        value_box.Text = u"" if saved == name else saved
        _place(grid, value_box, i + 1, 2)
        rows.append(_Row(template, check, value_box))

    def chosen():
        return [r for r in rows if r.checked()]

    def pairs(picked):
        """[(строка, группа вида и назначение)] — по виду на уровень."""
        return [(r, v) for r in picked for v in r.values()]

    def update_preview(*_args):
        mask = mask_box.Text
        picked = chosen()
        error = core.validate_mask(mask)
        if error:
            preview_title.Text = u"Маска: " + error
            preview_title.Foreground = Brushes.Firebrick
            preview.Text = u""
            return
        preview_title.Foreground = Brushes.Black
        if not picked:
            preview_title.Text = u"Отметьте шаблоны, для которых создавать виды."
            preview.Text = u""
            return
        items = pairs(picked)
        preview_title.Text = u"Будет видов: {}{} ({} на уровень × {} ур.{}). Имена на уровне «{}»:".format(
            u"до " if pick_cb.IsChecked else u"", len(items) * len(levels), len(items),
            len(levels), u", уровни выберете дальше" if pick_cb.IsChecked else u"",
            first_values.get(core.TOKEN_LEVEL, u""))
        lines = [u"• " + core.build_view_name(mask, first_values, r.name, v)
                 for r, v in items[:_PREVIEW_MAX]]
        if len(items) > _PREVIEW_MAX:
            lines.append(u"… и ещё {}".format(len(items) - _PREVIEW_MAX))
        warning = core.mask_warning(mask, [(r.name, v) for r, v in items])
        if warning:
            lines.append(u"Внимание: " + warning)
        preview.Text = u"\n".join(lines)

    mask_box.TextChanged += update_preview
    pick_cb.Checked += update_preview
    pick_cb.Unchecked += update_preview
    for r in rows:
        r.check.Checked += update_preview
        r.check.Unchecked += update_preview
        r.value_box.TextChanged += update_preview

    def set_all(flag):
        def handler(sender, args):
            for r in rows:
                r.check.IsChecked = flag
        return handler

    _button(select_buttons, u"Отметить все", set_all(True))
    _button(select_buttons, u"Снять все", set_all(False))

    def form_state(action):
        """Значения окна или None (неверная маска — с сообщением)."""
        mask = mask_box.Text
        error = core.validate_mask(mask)
        if error:
            forms.alert(u"Маска имени вида: " + error, title=TITLE)
            return None
        picked = chosen()
        return {
            "action": action,
            "mask": mask,
            "items": [(r.template, v) for r, v in pairs(picked)],
            "values": dict((r.name, core.join_values(r.values())) for r in rows),
            "checked": [r.name for r in picked],
            "align": bool(align_cb.IsChecked),
            "pick_levels": bool(pick_cb.IsChecked),
        }

    def save_state(state):
        return store.save(state["mask"], state["values"], state["checked"], state["align"],
                          state["pick_levels"])

    def on_run(sender, args):
        state = form_state("run")
        if state is None:
            return
        if not state["items"]:
            forms.alert(u"Отметьте хотя бы один шаблон вида.", title=TITLE)
            return
        result["value"] = state
        win.Close()

    def on_save(sender, args):
        state = form_state("save")
        if state is None or not save_state(state):
            return
        result["value"] = state
        win.Close()

    def read_for_export():
        # Выгружается то, что сейчас в окне, — сначала сохранить.
        state = form_state("save")
        if state is not None:
            save_state(state)
        return store.read_all()

    def on_imported():
        result["value"] = settings_transfer.RELOAD
        win.Close()

    _button(buttons, u"Отмена", lambda s, a: win.Close())
    _button(buttons, u"Сохранить", on_save)
    _button(buttons, u"Создать виды", on_run, bold=True)
    settings_transfer.add_transfer_buttons(
        buttons, read_for_export, store.write_all, u"видов по уровням", on_imported)

    update_preview()
    win.Content = outer
    win.ShowDialog()
    return result["value"]


class _LevelOption(object):
    def __init__(self, level):
        self.level = level
        self.label = geometry.level_name(level)


def pick_levels(template_name, levels, remembered):
    """
    Список уровней модели для одного шаблона (SelectFromList, несколько).
    remembered — имена уровней, выбранных для него в прошлый раз (None —
    ещё не спрашивали: отмечены все). Возвращает [уровни], [] — ни одного,
    None — окно закрыли (отмена).
    """
    names = [geometry.level_name(l) for l in levels]
    checked = set(core.preselected_levels(names, remembered))
    items = [forms.TemplateListItem(_LevelOption(l), checked=(geometry.level_name(l) in checked),
                                    name_attr="label")
             for l in levels]
    chosen = forms.SelectFromList.show(
        items,
        title=u"Выберите уровни в модели, для которых создавать виды для шаблона «{}»".format(
            template_name),
        button_name=u"Далее", multiselect=True, width=600, height=600)
    if chosen is None:
        return None
    return [o.level for o in chosen]
