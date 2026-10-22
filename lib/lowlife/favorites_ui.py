# -*- coding: utf-8 -*-
"""Окно «Избранное» (Favorites.panel/Manage) и «В избранное» из окна «Поиск».

Слева — свои панели (новая, переименовать, удалить, порядок), посередине — кнопки выбранной панели
(убрать, порядок), справа — все кнопки LowLife с поиском (`ribbon_catalog.search`), «Добавить»
кладёт выбранную в конец панели. «Сохранить» пишет настройки и сразу строит панели на ленте
(`favorites.sync`). Логика — `favorites_core`, лента — `favorites`.
"""

try:
    unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3
    unicode = str

import copy
import traceback

from pyrevit import forms
from System.Windows import Thickness
from System.Windows.Controls import ListBoxItem, TextBlock
from System.Windows.Media import SolidColorBrush, Color

from lowlife import favorites, favorites_core, ribbon_catalog, ribbon_search, select_list

NEW_PANEL = u"＋ Новая панель…"

_XAML = u'''
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Избранное LowLife" Width="1100" Height="660" MinWidth="820" MinHeight="400"
        WindowStartupLocation="CenterScreen" ShowInTaskbar="False"
        FontFamily="Segoe UI" FontSize="13" Background="White">
    <DockPanel Margin="14">
        <TextBlock DockPanel.Dock="Top" TextWrapping="Wrap" Foreground="#555555" Margin="0,0,0,10"
                   Text="Соберите свои панели из кнопок LowLife: они появятся на вкладке LowLife сразу за панелью «Избранное» и видны при любой теме. Кнопка избранного запускает ту же команду, что и исходная (Shift+клик — тоже)."/>
        <Grid DockPanel.Dock="Bottom" Margin="0,10,0,0">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="Auto"/>
                <ColumnDefinition Width="Auto"/>
            </Grid.ColumnDefinitions>
            <TextBlock x:Name="txtStatus" Grid.Column="0" Foreground="#555555" TextWrapping="Wrap"
                       VerticalAlignment="Center" Margin="0,0,12,0"/>
            <Button x:Name="btnCancel" Grid.Column="1" Content="Отмена" Padding="16,6" MinWidth="100"/>
            <Button x:Name="btnSave" Grid.Column="2" Content="Сохранить" FontWeight="SemiBold"
                    Padding="16,6" MinWidth="100" Margin="8,0,0,0"/>
        </Grid>
        <Grid>
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="230"/>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="1.3*"/>
            </Grid.ColumnDefinitions>
            <DockPanel Grid.Column="0" Margin="0,0,10,0">
                <TextBlock DockPanel.Dock="Top" Text="Мои панели" FontWeight="SemiBold" Margin="0,0,0,4"/>
                <WrapPanel DockPanel.Dock="Bottom" Margin="0,6,0,0">
                    <Button x:Name="btnNewPanel" Content="Новая…" Padding="8,3" Margin="0,0,4,4"/>
                    <Button x:Name="btnRenamePanel" Content="Переименовать…" Padding="8,3" Margin="0,0,4,4"/>
                    <Button x:Name="btnDeletePanel" Content="Удалить" Padding="8,3" Margin="0,0,4,4"/>
                    <Button x:Name="btnPanelUp" Content="▲" ToolTip="Левее на ленте" Padding="8,3" Margin="0,0,4,4"/>
                    <Button x:Name="btnPanelDown" Content="▼" ToolTip="Правее на ленте" Padding="8,3" Margin="0,0,4,4"/>
                </WrapPanel>
                <ListBox x:Name="lstPanels"/>
            </DockPanel>
            <DockPanel Grid.Column="1" Margin="0,0,10,0">
                <TextBlock x:Name="txtButtonsHeader" DockPanel.Dock="Top" Text="Кнопки панели"
                           FontWeight="SemiBold" Margin="0,0,0,4" TextTrimming="CharacterEllipsis"/>
                <WrapPanel DockPanel.Dock="Bottom" Margin="0,6,0,0">
                    <Button x:Name="btnRemove" Content="Убрать" Padding="8,3" Margin="0,0,4,4"/>
                    <Button x:Name="btnUp" Content="▲" ToolTip="Раньше на панели" Padding="8,3" Margin="0,0,4,4"/>
                    <Button x:Name="btnDown" Content="▼" ToolTip="Позже на панели" Padding="8,3" Margin="0,0,4,4"/>
                </WrapPanel>
                <ListBox x:Name="lstButtons" HorizontalContentAlignment="Stretch"
                         ScrollViewer.HorizontalScrollBarVisibility="Disabled"/>
            </DockPanel>
            <DockPanel Grid.Column="2">
                <TextBlock DockPanel.Dock="Top" Text="Кнопки LowLife — поиск" FontWeight="SemiBold" Margin="0,0,0,4"/>
                <TextBox x:Name="txtQuery" DockPanel.Dock="Top" Padding="5,4"/>
                <StackPanel DockPanel.Dock="Bottom" Orientation="Horizontal" Margin="0,6,0,0">
                    <Button x:Name="btnAdd" Content="← Добавить на панель" FontWeight="SemiBold" Padding="10,3"/>
                    <TextBlock Text="или двойной щелчок" Foreground="#888888" VerticalAlignment="Center" Margin="8,0,0,0"/>
                </StackPanel>
                <ListBox x:Name="lstAll" Margin="0,6,0,0" HorizontalContentAlignment="Stretch"
                         ScrollViewer.HorizontalScrollBarVisibility="Disabled"/>
            </DockPanel>
        </Grid>
    </DockPanel>
</Window>
'''

_GREY = SolidColorBrush(Color.FromRgb(0x99, 0x99, 0x99))


def _missing_row(ref):
    text = TextBlock()
    text.Text = u"{} — кнопки больше нет".format(favorites_core.button_key(ref))
    text.Foreground = _GREY
    text.Margin = Thickness(2, 3, 2, 3)
    item = ListBoxItem()
    item.Content = text
    return item


def ask_title(default=u"", others=(), reserved=()):
    """Название панели у пользователя (с проверкой) или None — отменил."""
    title = default
    while True:
        title = forms.ask_for_string(default=title, prompt=u"Название панели на ленте:",
                                     title=u"Панель избранного")
        if title is None:
            return None
        problem = favorites_core.title_problem(title, others, reserved)
        if problem is None:
            return u" ".join(title.split())
        forms.alert(problem, title=u"Избранное")


class FavoritesWindow(forms.WPFWindow):
    def __init__(self, data, entries, reserved):
        forms.WPFWindow.__init__(self, _XAML, literal_string=True)
        self.data = copy.deepcopy(favorites_core.normalize(data))
        self.entries = entries
        self.reserved = reserved
        self.saved = False

        self.lstPanels.SelectionChanged += lambda s, e: self.show_buttons()
        self.lstButtons.SelectionChanged += lambda s, e: self.update_buttons()
        self.lstAll.SelectionChanged += lambda s, e: self.update_buttons()
        self.lstAll.MouseDoubleClick += lambda s, e: self.add()
        self.txtQuery.TextChanged += lambda s, e: self.show_all()
        self.btnNewPanel.Click += lambda s, e: self.new_panel()
        self.btnRenamePanel.Click += lambda s, e: self.rename_panel()
        self.btnDeletePanel.Click += lambda s, e: self.delete_panel()
        self.btnPanelUp.Click += lambda s, e: self.move_panel(-1)
        self.btnPanelDown.Click += lambda s, e: self.move_panel(1)
        self.btnRemove.Click += lambda s, e: self.remove()
        self.btnUp.Click += lambda s, e: self.move_button(-1)
        self.btnDown.Click += lambda s, e: self.move_button(1)
        self.btnAdd.Click += lambda s, e: self.add()
        self.btnSave.Click += lambda s, e: self.save()
        self.btnCancel.Click += lambda s, e: self.Close()
        self.Loaded += lambda s, e: self.txtQuery.Focus()

        self.show_panels(0)
        self.show_all()

    # ------------------------------------------------------------ списки

    def panels(self):
        return self.data[u"panels"]

    def current_panel(self):
        index = self.lstPanels.SelectedIndex
        return self.panels()[index] if 0 <= index < len(self.panels()) else None

    def show_panels(self, select=None):
        self.lstPanels.Items.Clear()
        for panel in self.panels():
            self.lstPanels.Items.Add(u"{}  ({})".format(panel[u"title"], len(panel[u"buttons"])))
        if self.panels():
            index = select if select is not None else 0
            self.lstPanels.SelectedIndex = min(max(index, 0), len(self.panels()) - 1)
        self.show_buttons()

    def show_buttons(self, select=None):
        panel = self.current_panel()
        self.lstButtons.Items.Clear()
        if panel is None:
            self.txtButtonsHeader.Text = u"Кнопки панели — создайте панель слева"
        else:
            self.txtButtonsHeader.Text = u"Кнопки панели «{}»".format(panel[u"title"])
            for ref in panel[u"buttons"]:
                entry = favorites_core.find_entry(self.entries, ref)
                self.lstButtons.Items.Add(ribbon_search.button_row(entry) if entry else _missing_row(ref))
            if select is not None and panel[u"buttons"]:
                self.lstButtons.SelectedIndex = min(max(select, 0), len(panel[u"buttons"]) - 1)
        self.update_buttons()

    def show_all(self):
        self.lstAll.Items.Clear()
        for entry in ribbon_catalog.search(self.entries, self.txtQuery.Text):
            self.lstAll.Items.Add(ribbon_search.button_row(entry))
        if self.lstAll.Items.Count:
            self.lstAll.SelectedIndex = 0
        self.update_buttons()

    def update_buttons(self):
        has_panel = self.current_panel() is not None
        has_button = has_panel and self.lstButtons.SelectedIndex >= 0
        for button in (self.btnRenamePanel, self.btnDeletePanel, self.btnPanelUp, self.btnPanelDown):
            button.IsEnabled = has_panel
        for button in (self.btnRemove, self.btnUp, self.btnDown):
            button.IsEnabled = has_button
        self.btnAdd.IsEnabled = self.lstAll.SelectedItem is not None
        count = sum(len(p[u"buttons"]) for p in self.panels())
        self.txtStatus.Text = u"Панелей: {}, кнопок: {}".format(len(self.panels()), count)

    # ------------------------------------------------------------ действия

    def _titles_except(self, panel=None):
        return [p[u"title"] for p in self.panels() if p is not panel]

    def new_panel(self):
        title = ask_title(u"", self._titles_except(), self.reserved)
        if title is None:
            return None
        self.panels().append({u"title": title, u"buttons": []})
        self.show_panels(len(self.panels()) - 1)
        return title

    def rename_panel(self):
        panel = self.current_panel()
        if panel is None:
            return
        title = ask_title(panel[u"title"], self._titles_except(panel), self.reserved)
        if title is not None:
            panel[u"title"] = title
            self.show_panels(self.lstPanels.SelectedIndex)

    def delete_panel(self):
        panel = self.current_panel()
        if panel is None:
            return
        if panel[u"buttons"] and not forms.alert(
                u"Удалить панель «{}» вместе с её кнопками ({})?\nСами кнопки LowLife останутся на своих панелях."
                .format(panel[u"title"], len(panel[u"buttons"])), title=u"Избранное", yes=True, no=True):
            return
        index = self.lstPanels.SelectedIndex
        self.panels().remove(panel)
        self.show_panels(index)

    def move_panel(self, step):
        index = favorites_core.move(self.panels(), self.lstPanels.SelectedIndex, step)
        self.show_panels(index)

    def remove(self):
        panel = self.current_panel()
        index = self.lstButtons.SelectedIndex
        if panel is None or index < 0:
            return
        del panel[u"buttons"][index]
        self.show_panels(self.lstPanels.SelectedIndex)
        self.show_buttons(index)

    def move_button(self, step):
        panel = self.current_panel()
        if panel is None:
            return
        index = favorites_core.move(panel[u"buttons"], self.lstButtons.SelectedIndex, step)
        self.show_buttons(index)

    def add(self):
        item = self.lstAll.SelectedItem
        if item is None:
            return
        if self.current_panel() is None and self.new_panel() is None:
            return
        panel = self.current_panel()
        ref = favorites_core.button_ref(item.Tag)
        if any(favorites_core.button_key(r) == favorites_core.button_key(ref) for r in panel[u"buttons"]):
            self.txtStatus.Text = u"«{}» уже есть на панели «{}».".format(item.Tag[u"title"], panel[u"title"])
            return
        panel[u"buttons"].append(ref)
        self.show_panels(self.lstPanels.SelectedIndex)
        self.show_buttons(len(panel[u"buttons"]) - 1)

    def save(self):
        self.saved = True
        self.Close()


def _apply(uiapp, data):
    """Сохранить настройки и построить избранное на ленте; проблемы — одним сообщением."""
    if not favorites.save(data):
        return False
    problems = favorites.sync(uiapp, data)
    if problems:
        forms.alert(u"\n".join(problems), title=u"Избранное: не всё получилось")
    return True


def run(uiapp):
    try:
        entries = ribbon_catalog.list_buttons()
        win = FavoritesWindow(favorites.load(), entries, favorites.reserved_titles())
        win.ShowDialog()
        if win.saved:
            _apply(uiapp, win.data)
    except Exception as ex:
        forms.alert(unicode(ex), title=u"Избранное: ошибка", expanded=traceback.format_exc())


def add_to_favorites(uiapp, entry):
    """«В избранное» из окна «Поиск»: выбрать панель (или создать новую) и добавить в неё кнопку."""
    data = favorites.load()
    titles = [p[u"title"] for p in data[u"panels"]]
    choice = select_list.CommandSwitchWindow.show(
        titles + [NEW_PANEL], message=u"В какую панель избранного добавить «{}»?".format(entry[u"title"]))
    if not choice:
        return
    if choice == NEW_PANEL:
        choice = ask_title(u"", titles, favorites.reserved_titles())
        if choice is None:
            return
    data, added = favorites_core.add_button(data, choice, favorites_core.button_ref(entry))
    if not added:
        forms.alert(u"«{}» уже есть на панели «{}».".format(entry[u"title"], choice), title=u"Избранное")
        return
    _apply(uiapp, data)
