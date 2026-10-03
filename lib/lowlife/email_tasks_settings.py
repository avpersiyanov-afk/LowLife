# -*- coding: utf-8 -*-
"""
Настройки кнопки «Задачи из почты» (Mail.panel) + окно их редактирования
(Shift+клик по кнопке).

Текст промпта тоже редактируется здесь (ключ "prompt"). Пустое значение
значит «стандартный промпт» — prompt.txt из папки кнопки; свой текст
хранится в файле настроек и не теряется при обновлении расширения.

Хранятся в папке конфигурации pyRevit — JSON-файл
%APPDATA%\\pyRevit\\LowLifeEmailTasks_settings.json, тот же подход, что
у остальных кнопок расширения (простой файл вместо
pyrevit.script.get_config(), см. докстринг scs_settings.py про причину).
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
    StackPanel, TextBlock, TextBox, Button, CheckBox, Orientation,
    ScrollViewer, ScrollBarVisibility
)
from System.Windows.Media import Brushes

from lowlife import email_claude, settings_core

SETTINGS_FILE_NAME = "LowLifeEmailTasks_settings.json"

DEFAULTS = {
    "days": 3,
    "unread_only": False,
    "include_subfolders": True,
    "subfolder": u"",
    "claude_path": u"",
    "model": email_claude.DEFAULT_MODEL,
    "test_mode": False,
    "prompt": u"",
}


_STORE = settings_core.JsonStore(SETTINGS_FILE_NAME)


def load():
    values = dict(DEFAULTS)
    values.update(_STORE.read())
    try:
        values["days"] = max(1, int(values.get("days") or DEFAULTS["days"]))
    except Exception:
        values["days"] = DEFAULTS["days"]
    values["unread_only"] = bool(values.get("unread_only"))
    values["include_subfolders"] = bool(values.get("include_subfolders"))
    values["test_mode"] = bool(values.get("test_mode"))
    values["model"] = (values.get("model") or u"").strip() or DEFAULTS["model"]
    values["prompt"] = values.get("prompt") or u""
    return values


def effective_prompt(values, default_prompt):
    """Промпт для запроса: свой из настроек, иначе стандартный (prompt.txt)."""
    custom = values.get("prompt") or u""
    return custom if custom.strip() else default_prompt


def save(values):
    return _STORE.write(values)


def _label(parent, text, bold=False, top=10):
    block = TextBlock()
    block.Text = text
    block.TextWrapping = TextWrapping.Wrap
    block.Margin = Thickness(0, top, 0, 2)
    if bold:
        block.FontWeight = FontWeights.Bold
    parent.Children.Add(block)
    return block


def _hint(parent, text):
    block = TextBlock()
    block.Text = text
    block.FontSize = 11
    block.Foreground = Brushes.Gray
    block.TextWrapping = TextWrapping.Wrap
    block.Margin = Thickness(0, 2, 0, 0)
    parent.Children.Add(block)
    return block


def _textbox(parent, value):
    box = TextBox()
    box.Text = unicode(value)
    box.Padding = Thickness(4)
    parent.Children.Add(box)
    return box


def _checkbox(parent, text, value):
    box = CheckBox()
    box.Content = text
    box.IsChecked = bool(value)
    box.Margin = Thickness(0, 12, 0, 0)
    parent.Children.Add(box)
    return box


def show_settings_form(values, default_prompt):
    """Модальное окно. Возвращает словарь новых значений или None (Отмена).
    default_prompt — текст prompt.txt (для кнопки «Вернуть стандартный»)."""
    result = {"values": None}

    win = Window()
    win.Title = u"Настройки: Задачи из почты"
    win.Width = 720
    win.SizeToContent = SizeToContent.Height
    win.MaxHeight = SystemParameters.WorkArea.Height - 40
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    root = StackPanel()
    root.Margin = Thickness(16)

    title = TextBlock()
    title.Text = u"Задачи из почты"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    root.Children.Add(title)
    _hint(root, u"Кнопка только читает почту: ничего не отправляет, не помечает "
                u"прочитанным и не перемещает.")

    _label(root, u"Период, дней", bold=True, top=14)
    days_box = _textbox(root, values.get("days"))
    _hint(root, u"Сколько последних дней «Входящих» разбирать (по дате получения).")

    unread_box = _checkbox(root, u"Только непрочитанные", values.get("unread_only"))

    _label(root, u"Подпапка «Входящих»", bold=True, top=14)
    subfolder_box = _textbox(root, values.get("subfolder"))
    _hint(root, u"Пусто — сами «Входящие». Вложенные папки — через «/», например "
                u"«Проекты/Объект 1».")

    subfolders_box = _checkbox(root, u"Включая подпапки — читать и все вложенные папки "
                                     u"(«Входящих» или папки, указанной выше)",
                               values.get("include_subfolders"))

    _label(root, u"Путь к claude.exe", bold=True, top=14)
    claude_box = _textbox(root, values.get("claude_path"))
    detected = email_claude.find_claude(u"")
    _hint(root, u"Пусто — искать автоматически (PATH, %USERPROFILE%\\.local\\bin, "
                u"%APPDATA%\\npm). Сейчас найден: {}".format(detected or u"— не найден —"))

    _label(root, u"Модель", bold=True, top=14)
    model_box = _textbox(root, values.get("model"))
    _hint(root, u"Псевдоним (sonnet, opus, haiku) или полное имя модели — как для "
                u"`claude --model`. По умолчанию sonnet.")

    test_box = _checkbox(root, u"Тестовый режим — вместо Outlook брать письма из "
                               u"test_emails.json (рядом со скриптом кнопки)",
                         values.get("test_mode"))

    _label(root, u"Промпт для Claude", bold=True, top=18)
    prompt_box = TextBox()
    prompt_box.Text = effective_prompt(values, default_prompt)
    prompt_box.AcceptsReturn = True
    prompt_box.AcceptsTab = True
    prompt_box.TextWrapping = TextWrapping.Wrap
    prompt_box.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    prompt_box.Height = 260
    prompt_box.Padding = Thickness(4)
    root.Children.Add(prompt_box)
    _hint(root, u"Сегодняшняя дата и сами письма добавляются к промпту автоматически. "
                u"Сохраните в тексте формат ответа {\"tasks\":[{\"email_id\":…,\"task\":…,"
                u"\"requester\":…,\"deadline\":…,\"priority\":…,\"comment\":…}]} — по нему "
                u"разбирается ответ. Свой текст хранится в настройках и не теряется при "
                u"обновлении расширения.")

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
        try:
            days = int(days_box.Text.strip())
            if days < 1:
                raise ValueError()
        except Exception:
            forms.alert(u"Период — целое число дней, не меньше 1.")
            return
        claude_path = claude_box.Text.strip().strip('"')
        if claude_path and email_claude.find_claude(claude_path) is None:
            forms.alert(u"По указанному пути claude не найден:\n{}\n\n"
                        u"Укажите полный путь к claude.exe или оставьте поле "
                        u"пустым для автопоиска.".format(claude_path))
            return
        result["values"] = {
            "days": days,
            "unread_only": bool(unread_box.IsChecked),
            "include_subfolders": bool(subfolders_box.IsChecked),
            "subfolder": subfolder_box.Text.strip(),
            "claude_path": claude_path,
            "model": model_box.Text.strip() or DEFAULTS["model"],
            "test_mode": bool(test_box.IsChecked),
            # Совпадает со стандартным — храним пусто, чтобы правки prompt.txt
            # в новых версиях расширения подхватывались сами
            "prompt": u"" if _same_text(prompt_box.Text, default_prompt) else prompt_box.Text,
        }
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


def _same_text(a, b):
    norm = lambda t: (t or u"").replace(u"\r\n", u"\n").strip()
    return norm(a) == norm(b)


def edit_interactive(default_prompt):
    """Shift+клик: окно настроек. True — сохранено, False — отменено."""
    edited = show_settings_form(load(), default_prompt)
    if edited is None:
        return False
    return save(edited)
