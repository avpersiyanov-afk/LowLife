# -*- coding: utf-8 -*-
"""
Настройки кнопки «Проверка орфографии» (Tools.panel/SpellCheck) + окно их
редактирования (Shift+клик по кнопке).

Подключение ИИ — общее с «Задачами из почты» (ai_settings.py, файл
%APPDATA%\\pyRevit\\LowLifeEmailTasks_settings.json). Своё у кнопки — только
промпт (ключ "prompt" в %APPDATA%\\pyRevit\\LowLifeSpellCheck_settings.json):
пусто — стандартный prompt.txt из папки кнопки, свой текст не теряется
при обновлении расширения.
"""

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from pyrevit import forms

from System.Windows import (
    Window, WindowStartupLocation, Thickness, FontWeights,
    HorizontalAlignment, TextWrapping, SizeToContent, SystemParameters
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, Orientation, ScrollViewer, ScrollBarVisibility
)

from lowlife import ai_settings, settings_core
from lowlife.ai_settings import label as _label, hint as _hint

SETTINGS_FILE_NAME = "LowLifeSpellCheck_settings.json"

_STORE = settings_core.JsonStore(SETTINGS_FILE_NAME, label=u"проверки орфографии")


def load():
    """Подключение ИИ (общее) + свой промпт."""
    values = ai_settings.load()
    values["prompt"] = _STORE.read().get("prompt") or u""
    return values


def effective_prompt(values, default_prompt):
    custom = values.get("prompt") or u""
    return custom if custom.strip() else default_prompt


def save(values):
    return ai_settings.save(values) and _STORE.update({"prompt": values.get("prompt") or u""})


def _same_text(a, b):
    norm = lambda t: (t or u"").replace(u"\r\n", u"\n").strip()
    return norm(a) == norm(b)


def show_settings_form(values, default_prompt):
    """Модальное окно. Словарь новых значений или None (Отмена)."""
    result = {"values": None}

    win = Window()
    win.Title = u"Настройки: Проверка орфографии"
    win.Width = 720
    win.SizeToContent = SizeToContent.Height
    win.MaxHeight = SystemParameters.WorkArea.Height - 40
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    root = StackPanel()
    root.Margin = Thickness(16)

    title = TextBlock()
    title.Text = u"Проверка орфографии"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    root.Children.Add(title)
    _hint(root, u"Тексты заметок модели уходят выбранному ИИ; исправления показываются "
                u"списком и записываются только отмеченные.")

    connection = ai_settings.ConnectionSection(
        root, values, shared_note=u"Подключение общее с кнопкой «Задачи из почты».")

    _label(root, u"Промпт", bold=True, top=18)
    prompt_box = TextBox()
    prompt_box.Text = effective_prompt(values, default_prompt)
    prompt_box.AcceptsReturn = True
    prompt_box.AcceptsTab = True
    prompt_box.TextWrapping = TextWrapping.Wrap
    prompt_box.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    prompt_box.Height = 260
    prompt_box.Padding = Thickness(4)
    root.Children.Add(prompt_box)
    _hint(root, u"Тексты добавляются к промпту автоматически в виде "
                u"{\"items\":[{\"id\":…,\"text\":…}]}. Сохраните в тексте формат ответа "
                u"{\"fixes\":[{\"id\":…,\"text\":…}]} — по нему разбирается ответ. Свой "
                u"текст хранится в настройках и не теряется при обновлении расширения.")

    reset_btn = Button()
    reset_btn.Content = u"Вернуть стандартный промпт"
    reset_btn.Padding = Thickness(10, 3, 10, 3)
    reset_btn.Margin = Thickness(0, 6, 0, 0)
    reset_btn.HorizontalAlignment = HorizontalAlignment.Left

    def on_reset(sender, args):
        prompt_box.Text = default_prompt

    reset_btn.Click += on_reset
    root.Children.Add(reset_btn)

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(0, 18, 0, 0)

    cancel_btn = Button()
    cancel_btn.Content = u"Отмена"
    cancel_btn.Padding = Thickness(10, 4, 10, 4)
    cancel_btn.Margin = Thickness(0, 0, 8, 0)

    ok_btn = Button()
    ok_btn.Content = u"Сохранить"
    ok_btn.Padding = Thickness(10, 4, 10, 4)
    ok_btn.FontWeight = FontWeights.Bold
    ok_btn.IsDefault = True

    def on_ok(sender, args):
        error = connection.validate()
        if error:
            forms.alert(error)
            return
        new_values = connection.read()
        # Совпадает со стандартным — храним пусто, чтобы правки prompt.txt
        # в новых версиях расширения подхватывались сами
        new_values["prompt"] = (u"" if _same_text(prompt_box.Text, default_prompt)
                                else prompt_box.Text)
        result["values"] = new_values
        win.Close()

    def on_cancel(sender, args):
        win.Close()

    ok_btn.Click += on_ok
    cancel_btn.Click += on_cancel
    buttons.Children.Add(cancel_btn)
    buttons.Children.Add(ok_btn)
    root.Children.Add(buttons)

    scroller = ScrollViewer()
    scroller.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scroller.Content = root
    win.Content = scroller
    win.ShowDialog()
    return result["values"]


def edit_interactive(default_prompt):
    """Shift+клик: окно настроек. True — сохранено, False — отменено."""
    edited = show_settings_form(load(), default_prompt)
    if edited is None:
        return False
    return save(edited)
