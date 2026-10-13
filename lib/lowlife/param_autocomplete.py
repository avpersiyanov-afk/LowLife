# -*- coding: utf-8 -*-
"""
Контекстный поиск имён параметров в полях окон настроек.

Под полем, куда вводится имя параметра, по мере набора открывается список
подходящих имён параметров модели (поиск по вхождению, без учёта регистра,
«ё» = «е», несколько слов — все должны встретиться). ↓/↑ — выбор, Enter или
Tab — подставить, Esc — закрыть, ↓ или Ctrl+Пробел в поле — весь список.
Список — только подсказка: в поле по-прежнему можно вписать любое имя.

Поля-списки («через запятую», «по одному на строке», «A=Этаж; B=Секция»)
дополняются по текущему элементу списка под кареткой — см. token_span.

Чистая логика (rank, token_span, replace_token, spec_for_key) — без Revit и
WPF, есть тесты. Сбор имён (collect_parameter_names) и окно-подсказка
(attach) — Revit API/WPF, вызываются только из окон настроек.

Подключение:
    names = param_autocomplete.NameSource(doc)   # одна на окно, имена — лениво
    param_autocomplete.attach_by_keys(boxes, names)   # {ключ: TextBox}
    param_autocomplete.attach(box, names)             # одиночное поле
"""

# --- чистая логика ------------------------------------------------------------

# Разбивка по ключу настройки: (разделители элементов списка, символ, после
# которого начинается имя внутри элемента или None). Разделители "" — всё
# поле — одно имя.
SINGLE = (u"", None)
LIST = (u",;\n", None)

_SINGLE_SUFFIXES = ("_param", "_param_name")
_LIST_SUFFIXES = ("_params", "_param_names", "param_names_text")


def spec_for_key(key):
    """
    Как дополнять поле с этим ключом настроек: SINGLE для ключей имени
    параметра (*_param, *_param_name), LIST для списков имён (*_params,
    *_param_names, *param_names_text), None — поле не про параметры.
    """
    key = (key or "").lower()
    if key.endswith(_LIST_SUFFIXES):
        return LIST
    if key.endswith(_SINGLE_SUFFIXES):
        return SINGLE
    return None


def normalize(text):
    """Для сравнения: нижний регистр, «ё» → «е»."""
    return (text or u"").lower().replace(u"ё", u"е")


_WORD_STARTS = u" _-.([«\"/"


def _score(name_norm, query_norm, words):
    if name_norm == query_norm:
        return 0
    if name_norm.startswith(query_norm):
        return 1
    index = name_norm.find(query_norm)
    if index > 0 and name_norm[index - 1] in _WORD_STARTS:
        return 2
    if index > 0:
        return 3
    if len(words) > 1 and all(w in name_norm for w in words):
        return 4
    return None


def rank(names, query, limit=300):
    """
    Имена, подходящие под query, лучшие первыми: точное совпадение, начало
    имени, начало слова, вхождение, все слова запроса в любом порядке.
    Внутри одной группы — по алфавиту. Пустой запрос — все имена по алфавиту.
    """
    query_norm = normalize(query).strip()
    words = query_norm.split()
    scored = []
    for name in names:
        name_norm = normalize(name)
        if not query_norm:
            scored.append((0, name_norm, name))
            continue
        score = _score(name_norm, query_norm, words)
        if score is not None:
            scored.append((score, name_norm, name))
    scored.sort()
    result = [item[2] for item in scored]
    return result[:limit] if limit else result


def token_span(text, caret, spec=SINGLE):
    """
    Границы имени, которое сейчас редактируется: (начало, конец) в text или
    None, если каретка не на имени (например, на букве до «=» в «A=Этаж»).
    Пробелы по краям имени в него не входят.
    """
    text = text or u""
    separators, after = spec
    caret = max(0, min(caret, len(text)))

    start = 0
    for index in range(caret - 1, -1, -1):
        if text[index] in separators:
            start = index + 1
            break
    end = len(text)
    for index in range(caret, len(text)):
        if text[index] in separators:
            end = index
            break

    if after:
        mark = text.find(after, start, end)
        if mark < 0 or mark >= caret:
            return None
        start = mark + 1

    while start < end and text[start] in u" \t\r":
        start += 1
    while end > start and text[end - 1] in u" \t\r":
        end -= 1
    return start, end


def current_token(text, caret, spec=SINGLE):
    span = token_span(text, caret, spec)
    if span is None:
        return None
    return (text or u"")[span[0]:span[1]]


def replace_token(text, caret, name, spec=SINGLE):
    """
    Подставляет name вместо имени под кареткой. Возвращает (новый текст,
    новая позиция каретки — сразу после имени) или None, если подставлять
    некуда.
    """
    text = text or u""
    span = token_span(text, caret, spec)
    if span is None:
        return None
    start, end = span
    if start > 0 and text[start - 1] in u",;":
        # «A,|» → «A, Имя»: после запятой/«;» — пробел, как пишут руками
        name = u" " + name
    return text[:start] + name + text[end:], start + len(name)


# --- имена параметров модели (Revit API) -------------------------------------

def _definition_name(param):
    try:
        definition = param.Definition
        return definition.Name if definition is not None else None
    except Exception:
        return None


class _Collector(object):
    """Собирает имена, пока не кончится отведённое время."""

    def __init__(self, budget_ms):
        from System.Diagnostics import Stopwatch
        self.watch = Stopwatch.StartNew()
        self.budget_ms = budget_ms
        self.names = set()
        self.seen_param_ids = set()

    def out_of_time(self):
        return self.watch.ElapsedMilliseconds > self.budget_ms

    def add(self, name):
        if name:
            name = name.strip()
            if name:
                self.names.add(name)

    def add_parameters(self, element):
        try:
            params = element.Parameters
        except Exception:
            return
        for param in params:
            try:
                pid = param.Id.IntegerValue
            except Exception:
                pid = None
            if pid is not None:
                if pid in self.seen_param_ids:
                    continue
                self.seen_param_ids.add(pid)
            self.add(_definition_name(param))

    def collect(self, doc):
        from Autodesk.Revit.DB import FilteredElementCollector, ParameterElement

        # параметры проекта, общие (в том числе пришедшие с семействами), глобальные
        try:
            for element in FilteredElementCollector(doc).OfClass(ParameterElement):
                try:
                    self.add(element.GetDefinition().Name)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            iterator = doc.ParameterBindings.ForwardIterator()
            while iterator.MoveNext():
                try:
                    self.add(iterator.Key.Name)
                except Exception:
                    pass
        except Exception:
            pass

        # параметры семейств и штатные — по одному экземпляру на категорию+тип
        seen_types = set()
        try:
            instances = FilteredElementCollector(doc).WhereElementIsNotElementType()
            for element in instances:
                if self.out_of_time():
                    return
                try:
                    category = element.Category
                    if category is None:
                        continue
                    type_key = (category.Id.IntegerValue, element.GetTypeId().IntegerValue)
                except Exception:
                    continue
                if type_key in seen_types:
                    continue
                seen_types.add(type_key)
                self.add_parameters(element)
                type_id = element.GetTypeId()
                if type_id is not None and type_id.IntegerValue > 0:
                    element_type = doc.GetElement(type_id)
                    if element_type is not None:
                        self.add_parameters(element_type)
        except Exception:
            pass

    def linked_docs(self, doc):
        from Autodesk.Revit.DB import FilteredElementCollector, RevitLinkInstance
        result = []
        seen = set()
        try:
            for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
                try:
                    link_doc = link.GetLinkDocument()
                except Exception:
                    link_doc = None
                if link_doc is None:
                    continue
                key = link_doc.PathName or link_doc.Title
                if key in seen:
                    continue
                seen.add(key)
                result.append(link_doc)
        except Exception:
            pass
        return result


def collect_parameter_names(doc, budget_ms=4000, include_links=True):
    """
    Имена параметров модели (и загруженных связей — там часто параметры
    помещений), отсортированные. Параметры проекта и общие — все; параметры
    семейств и штатные — с одного экземпляра (и его типа) каждой пары
    категория+тип, пока не истечёт budget_ms (на больших моделях список
    может быть неполным, но окно не подвиснет).
    """
    if doc is None:
        return []
    collector = _Collector(budget_ms)
    collector.collect(doc)
    if include_links:
        for link_doc in collector.linked_docs(doc):
            if collector.out_of_time():
                break
            collector.seen_param_ids = set()
            collector.collect(link_doc)
    return sorted(collector.names, key=normalize)


def active_doc():
    """Активный документ Revit (для окон, которым doc не передают)."""
    try:
        from pyrevit import revit
        return revit.doc
    except Exception:
        return None


class NameSource(object):
    """
    Имена параметров для одного окна: собираются один раз, при первой
    подсказке (не задерживают открытие окна). doc=None — активный документ.
    """

    def __init__(self, doc=None, names=None):
        self.doc = doc
        self._names = list(names) if names is not None else None

    def names(self):
        if self._names is None:
            doc = self.doc if self.doc is not None else active_doc()
            cursor_set = False
            try:
                from System.Windows.Input import Mouse, Cursors
                Mouse.OverrideCursor = Cursors.Wait
                cursor_set = True
            except Exception:
                pass
            try:
                self._names = collect_parameter_names(doc)
            except Exception:
                self._names = []
            finally:
                if cursor_set:
                    Mouse.OverrideCursor = None
        return self._names


# --- окно-подсказка под полем (WPF) ------------------------------------------

HINT = (u"Начните вводить — появятся подходящие параметры модели "
        u"(↓ или Ctrl+Пробел — весь список, Enter — подставить).")


def attach_by_keys(boxes, source, overrides=None):
    """
    Подключает подсказки ко всем полям {ключ: TextBox}, чьи ключи — имена
    параметров (spec_for_key). overrides — {ключ: spec или None}, если
    правило по имени ключа не подходит.
    """
    overrides = overrides or {}
    for key, box in boxes.items():
        spec = overrides[key] if key in overrides else spec_for_key(key)
        if spec is not None:
            attach(box, source, spec)


def attach(box, source, spec=SINGLE):
    """Подключает подсказку имён параметров к TextBox. Возвращает box."""
    try:
        _Completion(box, source, spec)
    except Exception:
        # подсказка — удобство; окно настроек без неё должно работать
        pass
    return box


class _Completion(object):

    MAX_HEIGHT = 260

    def __init__(self, box, source, spec):
        import clr
        clr.AddReference('PresentationFramework')
        clr.AddReference('PresentationCore')
        from System.Windows import Thickness, Setter, Style, UIElement
        from System.Windows.Controls import (
            Border, Control, ListBox, ListBoxItem, ScrollViewer, ScrollBarVisibility
        )
        from System.Windows.Controls.Primitives import Popup, PlacementMode
        from System.Windows.Media import Brushes

        self.box = box
        self.source = source
        self.spec = spec
        self.updating = False
        self.window_hooked = False

        self.list = ListBox()
        # Ничто в подсказке не забирает фокус у поля — иначе поле теряет
        # фокус и подсказка закрывается посреди клика.
        self.list.Focusable = False
        item_style = Style(clr.GetClrType(ListBoxItem))
        item_style.Setters.Add(Setter(UIElement.FocusableProperty, False))
        item_style.Setters.Add(Setter(Control.PaddingProperty, Thickness(4, 1, 4, 1)))
        self.list.ItemContainerStyle = item_style
        self.list.MaxHeight = self.MAX_HEIGHT
        self.list.BorderThickness = Thickness(0)
        ScrollViewer.SetHorizontalScrollBarVisibility(self.list, ScrollBarVisibility.Disabled)
        self.list.PreviewMouseLeftButtonDown += self.on_list_click

        border = Border()
        border.BorderBrush = Brushes.Gray
        border.BorderThickness = Thickness(1)
        border.Background = Brushes.White
        border.Child = self.list

        self.popup = Popup()
        self.popup.PlacementTarget = box
        self.popup.Placement = PlacementMode.Bottom
        self.popup.StaysOpen = True
        self.popup.Child = border

        box.TextChanged += self.on_text_changed
        box.PreviewKeyDown += self.on_key
        box.LostKeyboardFocus += self.on_lost_focus
        if box.ToolTip is None:
            box.ToolTip = HINT

    # --- показ ---

    def close(self, *args):
        if self.popup.IsOpen:
            self.popup.IsOpen = False

    def hook_window(self):
        if self.window_hooked:
            return
        self.window_hooked = True
        try:
            from System.Windows import Window
            window = Window.GetWindow(self.box)
            if window is not None:
                # поле уезжает при прокрутке/перемещении окна — подсказку закрываем
                window.LocationChanged += self.close
                window.Deactivated += self.close
                window.PreviewMouseWheel += self.close
                window.SizeChanged += self.close
        except Exception:
            pass

    def refresh(self, show_all=False):
        token = current_token(self.box.Text, self.box.CaretIndex, self.spec)
        if token is None:
            self.close()
            return
        query = u"" if show_all else token
        if not query and not show_all:
            self.close()
            return
        matches = rank(self.source.names(), query)
        if not matches or (not show_all and len(matches) == 1 and matches[0] == token):
            self.close()
            return
        self.list.Items.Clear()
        for name in matches:
            self.list.Items.Add(name)
        self.list.SelectedIndex = 0
        if token in matches:
            self.list.SelectedIndex = matches.index(token)
        self.list.ScrollIntoView(self.list.SelectedItem)
        self.popup.MinWidth = max(self.box.ActualWidth, 200)
        self.hook_window()
        self.popup.IsOpen = True

    def choose(self, name):
        replaced = replace_token(self.box.Text, self.box.CaretIndex, name, self.spec)
        self.close()
        if replaced is None:
            return
        text, caret = replaced
        self.updating = True
        try:
            self.box.Text = text
            self.box.CaretIndex = caret
        finally:
            self.updating = False

    def move(self, delta):
        count = self.list.Items.Count
        if not count:
            return
        index = self.list.SelectedIndex + delta
        index = max(0, min(count - 1, index))
        self.list.SelectedIndex = index
        self.list.ScrollIntoView(self.list.SelectedItem)

    # --- события ---

    def on_text_changed(self, sender, args):
        if self.updating or not self.box.IsKeyboardFocusWithin:
            return
        self.refresh()

    def on_lost_focus(self, sender, args):
        self.close()

    def on_key(self, sender, args):
        from System.Windows.Input import Key, Keyboard, ModifierKeys

        key = args.Key
        is_open = self.popup.IsOpen

        if key == Key.Space and Keyboard.Modifiers == ModifierKeys.Control:
            self.refresh(show_all=True)
            args.Handled = True
        elif key == Key.Down:
            if is_open:
                self.move(1)
                args.Handled = True
            elif not self.box.AcceptsReturn or Keyboard.Modifiers == ModifierKeys.Alt:
                # в многострочном поле ↓ — переход по строкам; список — Alt+↓
                self.refresh(show_all=True)
                args.Handled = True
        elif key == Key.Up and is_open:
            self.move(-1)
            args.Handled = True
        elif key == Key.PageDown and is_open:
            self.move(10)
            args.Handled = True
        elif key == Key.PageUp and is_open:
            self.move(-10)
            args.Handled = True
        elif key == Key.Escape and is_open:
            self.close()
            args.Handled = True
        elif key in (Key.Enter, Key.Return) and is_open:
            if self.list.SelectedItem is not None:
                self.choose(self.list.SelectedItem)
                args.Handled = True
            else:
                self.close()
        elif key == Key.Tab and is_open:
            if self.list.SelectedItem is not None:
                self.choose(self.list.SelectedItem)
            self.close()

    def on_list_click(self, sender, args):
        from System.Windows.Controls import ListBoxItem
        from System.Windows.Media import VisualTreeHelper, Visual

        node = args.OriginalSource
        while node is not None and not isinstance(node, ListBoxItem):
            if not isinstance(node, Visual):
                node = getattr(node, "Parent", None)
                continue
            node = VisualTreeHelper.GetParent(node)
        if node is not None:
            self.choose(node.Content)
            args.Handled = True
