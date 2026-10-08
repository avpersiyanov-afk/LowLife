# -*- coding: utf-8 -*-
"""Кнопка «Поиск» (_Themes.panel): найти кнопку LowLife по названию и запустить её или показать на ленте.

Список кнопок — `ribbon_catalog.list_buttons()` (по папкам расширения, без Revit API), поиск —
`ribbon_catalog.search()`. Здесь только окно и работа с лентой:
- «Запустить» — `UIApplication.PostCommand` с id кнопки на ленте (Autodesk.Windows `RibbonItem.Id`,
  вида `CustomCtrl_%CustomCtrl_%LowLife%Панель%Кнопка`); Revit выполнит её сразу после этого скрипта,
  как обычный клик.
- «Показать на ленте» — открывает вкладку LowLife, делает кнопку и её панель видимыми (даже если
  текущая тема их скрывает — до следующего переключения темы) и на несколько секунд подсвечивает её.
"""
import traceback

from pyrevit import forms
from System import TimeSpan
from System.Windows import Thickness, FontWeights, TextTrimming, TextWrapping
from System.Windows.Controls import ListBoxItem, StackPanel, TextBlock, DockPanel, Dock
from System.Windows.Input import Key, Keyboard, ModifierKeys
from System.Windows.Media import SolidColorBrush, Color
from System.Windows.Threading import DispatcherTimer

from lowlife import ribbon_catalog

TAB_NAME = u"LowLife"
SELF = (u"_Themes", u"Search")  # саму кнопку «Поиск» в результатах не показываем
HIGHLIGHT_SECONDS = 8
MAX_TOOLTIP = 160

_XAML = u'''
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Поиск кнопки LowLife" Width="640" Height="520" MinWidth="420" MinHeight="300"
        WindowStartupLocation="CenterScreen" ShowInTaskbar="False"
        FontFamily="Segoe UI" FontSize="13" Background="White">
    <DockPanel Margin="14">
        <TextBox x:Name="txtQuery" DockPanel.Dock="Top" Padding="6,5" FontSize="14"/>
        <DockPanel DockPanel.Dock="Bottom" Margin="0,10,0,0" LastChildFill="False">
            <TextBlock x:Name="txtStatus" DockPanel.Dock="Left" VerticalAlignment="Center"
                       Foreground="#888888" FontSize="11"/>
            <Button x:Name="btnRun" DockPanel.Dock="Right" Content="Запустить" FontWeight="SemiBold"
                    Padding="16,6" MinWidth="100" Margin="8,0,0,0"/>
            <Button x:Name="btnShow" DockPanel.Dock="Right" Content="Показать на ленте"
                    Padding="16,6" MinWidth="100"/>
        </DockPanel>
        <ListBox x:Name="lstResults" Margin="0,8,0,0" HorizontalContentAlignment="Stretch"
                 ScrollViewer.HorizontalScrollBarVisibility="Disabled"/>
    </DockPanel>
</Window>
'''

_GREY = SolidColorBrush(Color.FromRgb(0x77, 0x77, 0x77))
_ACCENT = SolidColorBrush(Color.FromRgb(0xC0, 0x66, 0x10))  # тёмный вариант оранжевого логотипа — читается на белом


def _short(text, limit=MAX_TOOLTIP):
    return text if len(text) <= limit else text[:limit - 1].rstrip() + u"…"


def _row(entry):
    title = TextBlock()
    title.Text = entry[u"title"]
    title.FontWeight = FontWeights.SemiBold
    title.TextTrimming = TextTrimming.CharacterEllipsis
    panel = TextBlock()
    panel.Text = entry[u"panel_title"]
    panel.Foreground = _ACCENT
    panel.Margin = Thickness(12, 0, 0, 0)
    head = DockPanel()
    DockPanel.SetDock(panel, Dock.Right)
    head.Children.Add(panel)
    head.Children.Add(title)

    box = StackPanel()
    box.Margin = Thickness(2, 3, 2, 3)
    box.Children.Add(head)
    if entry[u"tooltip"]:
        hint = TextBlock()
        hint.Text = _short(entry[u"tooltip"])
        hint.Foreground = _GREY
        hint.FontSize = 11
        hint.TextWrapping = TextWrapping.Wrap
        box.Children.Add(hint)

    item = ListBoxItem()
    item.Content = box
    item.Tag = entry
    item.ToolTip = entry[u"tooltip"] or None
    return item


class SearchWindow(forms.WPFWindow):
    def __init__(self, entries):
        forms.WPFWindow.__init__(self, _XAML, literal_string=True)
        self.entries = entries
        self.result = None  # (u"run" | u"show", entry)
        self.txtQuery.TextChanged += lambda s, e: self.refresh()
        self.txtQuery.PreviewKeyDown += self.on_query_key
        self.lstResults.MouseDoubleClick += lambda s, e: self.finish(u"run")
        self.lstResults.SelectionChanged += lambda s, e: self.update_buttons()
        self.lstResults.KeyDown += self.on_list_key
        self.btnRun.Click += lambda s, e: self.finish(u"run")
        self.btnShow.Click += lambda s, e: self.finish(u"show")
        self.Loaded += lambda s, e: self.txtQuery.Focus()
        self.refresh()

    def refresh(self):
        found = ribbon_catalog.search(self.entries, self.txtQuery.Text)
        self.lstResults.Items.Clear()
        for entry in found:
            self.lstResults.Items.Add(_row(entry))
        if found:
            self.lstResults.SelectedIndex = 0
            self.lstResults.ScrollIntoView(self.lstResults.Items[0])
        self.txtStatus.Text = (u"Найдено: {}   ·   Enter — запустить, Ctrl+Enter — показать на ленте, Esc — закрыть"
                               .format(len(found)) if found else u"Ничего не нашлось")
        self.update_buttons()

    def update_buttons(self):
        selected = self.lstResults.SelectedItem is not None
        self.btnRun.IsEnabled = selected
        self.btnShow.IsEnabled = selected

    def move(self, step):
        count = self.lstResults.Items.Count
        if not count:
            return
        index = min(max(self.lstResults.SelectedIndex + step, 0), count - 1)
        self.lstResults.SelectedIndex = index
        self.lstResults.ScrollIntoView(self.lstResults.Items[index])

    def on_query_key(self, sender, e):
        # стрелки в строке поиска листают результаты — руку с клавиатуры убирать не нужно
        if e.Key == Key.Down:
            self.move(1)
        elif e.Key == Key.Up:
            self.move(-1)
        elif e.Key == Key.PageDown:
            self.move(10)
        elif e.Key == Key.PageUp:
            self.move(-10)
        elif e.Key == Key.Enter:
            self.finish(u"show" if Keyboard.Modifiers == ModifierKeys.Control else u"run")
        else:
            return
        e.Handled = True

    def on_list_key(self, sender, e):
        if e.Key == Key.Enter:
            e.Handled = True
            self.finish(u"show" if Keyboard.Modifiers == ModifierKeys.Control else u"run")

    def finish(self, action):
        item = self.lstResults.SelectedItem
        if item is None:
            return
        self.result = (action, item.Tag)
        self.Close()


# ---------------------------------------------------------------- лента

def _find_ribbon_item(entry):
    """(pyRevit-панель, [элементы pyRevit от панели до кнопки]) или (None, None)."""
    from pyrevit.coreutils.ribbon import get_current_ui
    tabs = get_current_ui().get_pyrevit_tabs()
    # у RibbonPanel имя — подпись панели (title из bundle.yaml), см. panel_themes.PANEL_RIBBON_NAMES
    for panel_name in (entry[u"panel_title"], entry[u"panel"]):
        for tab in tabs:
            panel = tab.find_child(panel_name)
            if panel is None:
                continue
            chain, parent = [], panel
            for name in entry[u"path"]:
                parent = parent.find_child(name)
                if parent is None:
                    break
                chain.append(parent)
            else:
                return panel, chain
    return None, None


def _command_id(entry, chain):
    adwin = None
    try:
        adwin = chain[-1].get_adwindows_object()
    except Exception:
        pass
    ids = []
    if adwin is not None and adwin.Id:
        ids.append(adwin.Id)
    # запасной вариант — так Revit называет команды кнопок надстроек
    ids.append(u"%".join([u"CustomCtrl_", u"CustomCtrl_", TAB_NAME, entry[u"panel_title"]] + entry[u"path"]))
    return ids


def run_button(uiapp, entry):
    """Запускает кнопку как клик по ленте (после завершения этого скрипта). Возвращает текст ошибки или None."""
    from Autodesk.Revit.UI import RevitCommandId
    panel, chain = _find_ribbon_item(entry)
    if not chain:
        return u"Кнопка «{}» не найдена на ленте — перезагрузите pyRevit.".format(entry[u"title"])
    for cmd_id in _command_id(entry, chain):
        cmd = RevitCommandId.LookupCommandId(cmd_id)
        if cmd is not None and uiapp.CanPostCommand(cmd):
            uiapp.PostCommand(cmd)
            return None
    return (u"Revit не даёт запустить «{}» отсюда (возможно, кнопка недоступна без открытой модели) — "
            u"она подсвечена на ленте.".format(entry[u"title"]))


def _activate_tab():
    import clr
    clr.AddReference("AdWindows")
    from Autodesk.Windows import ComponentManager
    for tab in ComponentManager.Ribbon.Tabs:
        if tab.Title == TAB_NAME or tab.Id == TAB_NAME:
            tab.IsVisible = True
            ComponentManager.Ribbon.ActiveTab = tab
            return


def _set_highlight(adwin, on):
    import clr
    clr.AddReference("AdWindows")
    from Autodesk.Internal.Windows import HighlightMode
    # HighlightMode.None нельзя написать в Python 2 — None там ключевое слово
    adwin.Highlight = HighlightMode.New if on else getattr(HighlightMode, "None")


def show_button(entry):
    """Открывает вкладку LowLife, делает кнопку видимой и подсвечивает её. Возвращает текст ошибки или None."""
    panel, chain = _find_ribbon_item(entry)
    if not chain:
        return u"Кнопка «{}» не найдена на ленте — перезагрузите pyRevit.".format(entry[u"title"])
    # тема могла скрыть кнопку/панель — открываем их до следующего переключения темы
    for item in chain:
        item.visible = True
    panel.visible = True
    adwin_panel = panel.get_adwindows_object()
    if adwin_panel is not None:
        adwin_panel.IsVisible = True
    try:
        _activate_tab()
    except Exception:
        pass
    try:
        adwin = chain[0].get_adwindows_object()  # кнопка в выпадающем списке — подсвечиваем сам список
        _set_highlight(adwin, True)
        timer = DispatcherTimer()
        timer.Interval = TimeSpan.FromSeconds(HIGHLIGHT_SECONDS)

        def _off(sender, e):
            timer.Stop()
            try:
                _set_highlight(adwin, False)
            except Exception:
                pass
        timer.Tick += _off
        timer.Start()
    except Exception:
        pass  # без подсветки кнопка всё равно на виду
    return None


def run(uiapp):
    try:
        _run(uiapp)
    except Exception as ex:
        forms.alert(unicode(ex), title=u"Поиск: ошибка", expanded=traceback.format_exc())


def _run(uiapp):
    entries = [e for e in ribbon_catalog.list_buttons() if (e[u"panel"], e[u"button"]) != SELF]
    win = SearchWindow(entries)
    win.ShowDialog()
    if not win.result:
        return
    action, entry = win.result
    if action == u"run":
        error = run_button(uiapp, entry)
        if error:
            show_button(entry)
            forms.alert(error, title=u"Поиск")
    else:
        error = show_button(entry)
        if error:
            forms.alert(error, title=u"Поиск")
