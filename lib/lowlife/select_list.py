# -*- coding: utf-8 -*-
"""
Списки выбора pyRevit с поиском LowLife.

`SelectFromList` — тот же `forms.SelectFromList`, но строка поиска ищет через
`text_search`: по части имени, слова в любом порядке, в любой раскладке (у
pyRevit — нечёткий поиск без смены раскладки). Режим регулярных выражений
pyRevit оставлен как есть. `CommandSwitchWindow` — то же для окна-переключателя.
`select_views` — `forms.select_views` на этом списке.

Подключение — вместо `forms.SelectFromList.show(...)`:
    from lowlife import select_list
    select_list.SelectFromList.show(...)
"""

from pyrevit import forms

from lowlife import text_search
from lowlife.i18n import N_, tr

_TEXT_KWARGS = ("title", "button_name", "message")


def _translated(kwargs):
    """Подписи окна (title=, button_name=, message=) на выбранном языке."""
    for key in _TEXT_KWARGS:
        if kwargs.get(key):
            kwargs[key] = tr(kwargs[key])
    return kwargs


class SelectFromList(forms.SelectFromList):
    def __init__(self, *args, **kwargs):
        super(SelectFromList, self).__init__(*args, **kwargs)
        from lowlife import ui_theme
        ui_theme.apply(self)

    @classmethod
    def show(cls, context, *args, **kwargs):
        return super(SelectFromList, cls).show(context, *args, **_translated(kwargs))

    def _list_options(self, option_filter=None):
        # базовый метод заодно переключает подписи кнопок «Отметить все»/«Отметить»
        forms.SelectFromList._list_options(self, option_filter)
        if not option_filter or self.use_regex:
            return
        from System.Collections.ObjectModel import ObservableCollection
        found = text_search.rank(list(self._get_active_ctx()), option_filter, key=lambda x: x.name)
        self.list_lb.ItemsSource = ObservableCollection[forms.TemplateListItem](found)


class CommandSwitchWindow(forms.CommandSwitchWindow):
    def __init__(self, *args, **kwargs):
        super(CommandSwitchWindow, self).__init__(*args, **kwargs)
        from lowlife import ui_theme
        ui_theme.apply(self)

    @classmethod
    def show(cls, context, *args, **kwargs):
        return super(CommandSwitchWindow, cls).show(context, *args, **_translated(kwargs))

    def _filter_options(self, option_filter=None):
        forms.CommandSwitchWindow._filter_options(self, option_filter)
        if not option_filter:
            return
        from System.Windows import Visibility
        for button in self.button_list.Children:
            visible = text_search.matches(button.Content, option_filter)
            button.Visibility = Visibility.Visible if visible else Visibility.Collapsed


def show_dropdown(options, title):
    """Одиночный выбор из выпадающего списка с текстовым фильтром."""
    from System.Windows import (
        HorizontalAlignment, SizeToContent, Thickness, Window, WindowStartupLocation
    )
    from System.Windows.Controls import Button, ComboBox, Label, Orientation, StackPanel, TextBox
    from System.Windows.Interop import WindowInteropHelper
    from pyrevit import HOST_APP
    from lowlife import ui_theme

    window = Window()
    window.Title = tr(title)
    window.Width = 460
    window.SizeToContent = SizeToContent.Height
    window.WindowStartupLocation = WindowStartupLocation.CenterOwner
    WindowInteropHelper(window).Owner = HOST_APP.uiapp.MainWindowHandle
    body = StackPanel()
    body.Margin = Thickness(16)
    window.Content = body

    search = TextBox()
    search.MinHeight = 26
    search_label = Label()
    search_label.Content = tr(u"Поиск")
    search_label.Target = search
    body.Children.Add(search_label)
    body.Children.Add(search)
    choices = ComboBox()
    choices.Margin = Thickness(0, 8, 0, 12)
    choices.MinHeight = 26
    choices.MaxDropDownHeight = 320
    body.Children.Add(choices)

    ok = Button()
    ok.Content = u"OK"
    ok.IsDefault = True
    ok.IsEnabled = False
    ok.MinWidth = 84
    ok.MinHeight = 26
    cancel = Button()
    cancel.Content = tr(u"Отмена")
    cancel.IsCancel = True
    cancel.MinWidth = 84
    cancel.MinHeight = 26
    cancel.Margin = Thickness(8, 0, 0, 0)
    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Children.Add(ok)
    buttons.Children.Add(cancel)
    body.Children.Add(buttons)

    def refresh(*args):
        selected = choices.SelectedItem
        matches = text_search.rank(options, search.Text) if search.Text.strip() else options
        choices.Items.Clear()
        for option in matches:
            choices.Items.Add(option)
        if selected in matches:
            choices.SelectedItem = selected
        elif len(matches) == 1:
            choices.SelectedIndex = 0

    def selection_changed(*args):
        ok.IsEnabled = choices.SelectedIndex >= 0

    def accept(*args):
        window.DialogResult = True

    search.TextChanged += refresh
    choices.SelectionChanged += selection_changed
    ok.Click += accept
    window.Loaded += lambda sender, args: search.Focus()
    refresh()
    ui_theme.apply(window)
    return choices.SelectedItem if window.ShowDialog() else None


def select_views(title=N_(u"Выбор видов"), button_name=N_(u"Выбрать"), multiple=True, filterfunc=None, doc=None):
    """Как forms.select_views (без use_selection): виды модели в списке с поиском LowLife."""
    from pyrevit import revit
    doc = doc or revit.doc
    views = revit.query.get_all_views(doc=doc)
    if filterfunc:
        views = [v for v in views if filterfunc(v)]
    return SelectFromList.show(
        sorted([forms.ViewOption(v) for v in views], key=lambda x: x.name),
        title=title, button_name=button_name, multiselect=multiple, checked_only=True)


def select_sheets(title=N_(u"Выбор листов"), button_name=N_(u"Выбрать"), multiple=True,
                  filterfunc=None, doc=None):
    """Как forms.select_sheets: листы в списке с поиском LowLife. Пустышки не показываются."""
    from pyrevit import revit
    doc = doc or revit.doc
    sheets = revit.query.get_sheets(doc=doc, include_placeholders=False)
    if filterfunc:
        sheets = [s for s in sheets if filterfunc(s)]
    return SelectFromList.show(
        sorted([forms.SheetOption(s) for s in sheets], key=lambda x: x.name),
        title=title, button_name=button_name, multiselect=multiple, checked_only=True)
