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


class SelectFromList(forms.SelectFromList):
    def _list_options(self, option_filter=None):
        # базовый метод заодно переключает подписи кнопок «Отметить все»/«Отметить»
        forms.SelectFromList._list_options(self, option_filter)
        if not option_filter or self.use_regex:
            return
        from System.Collections.ObjectModel import ObservableCollection
        found = text_search.rank(list(self._get_active_ctx()), option_filter, key=lambda x: x.name)
        self.list_lb.ItemsSource = ObservableCollection[forms.TemplateListItem](found)


class CommandSwitchWindow(forms.CommandSwitchWindow):
    def _filter_options(self, option_filter=None):
        forms.CommandSwitchWindow._filter_options(self, option_filter)
        if not option_filter:
            return
        from System.Windows import Visibility
        for button in self.button_list.Children:
            visible = text_search.matches(button.Content, option_filter)
            button.Visibility = Visibility.Visible if visible else Visibility.Collapsed


def select_views(title=u"Выбор видов", button_name=u"Выбрать", multiple=True, filterfunc=None, doc=None):
    """Как forms.select_views (без use_selection): виды модели в списке с поиском LowLife."""
    from pyrevit import revit
    doc = doc or revit.doc
    views = revit.query.get_all_views(doc=doc)
    if filterfunc:
        views = [v for v in views if filterfunc(v)]
    return SelectFromList.show(
        sorted([forms.ViewOption(v) for v in views], key=lambda x: x.name),
        title=title, button_name=button_name, multiselect=multiple, checked_only=True)
