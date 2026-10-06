# -*- coding: utf-8 -*-
"""
Настройки кнопки «Задачи из почты» (Mail.panel) + окно их редактирования
(Shift+клик по кнопке).

Подключение ИИ (способ, путь к программе или ключ API, модель) — общее с
«Проверкой орфографии», блок окна и ключи — в ai_settings.py; лежат они
в этом же файле настроек.

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
    StackPanel, TextBlock, TextBox, Button, Orientation, ScrollViewer, ScrollBarVisibility
)

from lowlife import ai_settings, settings_core
from lowlife.ai_settings import label as _label, hint as _hint, textbox as _textbox, checkbox as _checkbox

SETTINGS_FILE_NAME = ai_settings.SETTINGS_FILE_NAME

# Прежние имена — ссылки на инструкцию теперь в ai_settings
REPO_URL = ai_settings.REPO_URL
GUIDE_URL = ai_settings.GUIDE_URL
GUIDE_URLS = ai_settings.GUIDE_URLS

DEFAULTS = {
    "days": 3,
    "unread_only": False,
    "include_subfolders": True,
    "subfolder": u"",
    "test_mode": False,
    "prompt": u"",
}
DEFAULTS.update(ai_settings.DEFAULTS)


_STORE = settings_core.JsonStore(SETTINGS_FILE_NAME)


def load():
    values = dict(DEFAULTS)
    values.update(_STORE.read())
    ai_settings.normalize(values)
    try:
        values["days"] = max(1, int(values.get("days") or DEFAULTS["days"]))
    except Exception:
        values["days"] = DEFAULTS["days"]
    values["unread_only"] = bool(values.get("unread_only"))
    values["include_subfolders"] = bool(values.get("include_subfolders"))
    values["test_mode"] = bool(values.get("test_mode"))
    values["prompt"] = values.get("prompt") or u""
    return values


def effective_prompt(values, default_prompt):
    """Промпт для запроса: свой из настроек, иначе стандартный (prompt.txt)."""
    custom = values.get("prompt") or u""
    return custom if custom.strip() else default_prompt


def save(values):
    return _STORE.write(values)

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

    # --- Подключение ИИ (общее с «Проверкой орфографии»)
    connection = ai_settings.ConnectionSection(
        root, values, shared_note=u"Подключение общее с кнопкой «Проверка орфографии».")

    # --- Почта
    _label(root, u"Период, дней", bold=True, top=18)
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

    test_box = _checkbox(root, u"Тестовый режим — вместо Outlook брать письма из "
                               u"test_emails.json (рядом со скриптом кнопки)",
                         values.get("test_mode"))

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
    _hint(root, u"Общий для всех способов подключения. Сегодняшняя дата и сами письма "
                u"добавляются к промпту автоматически. "
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

        error = connection.validate()
        if error:
            forms.alert(error)
            return

        new_values = {
            "days": days,
            "unread_only": bool(unread_box.IsChecked),
            "include_subfolders": bool(subfolders_box.IsChecked),
            "subfolder": subfolder_box.Text.strip(),
            "test_mode": bool(test_box.IsChecked),
            # Совпадает со стандартным — храним пусто, чтобы правки prompt.txt
            # в новых версиях расширения подхватывались сами
            "prompt": u"" if _same_text(prompt_box.Text, default_prompt) else prompt_box.Text,
        }
        new_values.update(connection.read())
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


def _same_text(a, b):
    norm = lambda t: (t or u"").replace(u"\r\n", u"\n").strip()
    return norm(a) == norm(b)


def edit_interactive(default_prompt):
    """Shift+клик: окно настроек. True — сохранено, False — отменено."""
    edited = show_settings_form(load(), default_prompt)
    if edited is None:
        return False
    return save(edited)
