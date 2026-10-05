# -*- coding: utf-8 -*-
"""
Настройки кнопки «Задачи из почты» (Mail.panel) + окно их редактирования
(Shift+клик по кнопке).

Способ подключения ИИ — ключ "provider" (см. email_ai_core.PROVIDERS):
Claude Code / Anthropic API / Codex CLI / OpenAI API. У каждого способа
свои поля: путь к программе (claude_path, codex_path) или ключ API
(anthropic_api_key, openai_api_key) и модель (<provider>_model). Ключи
хранятся в файле настроек пользователя открытым текстом, как и всё
остальное в нём; пустое поле ключа — взять из переменной окружения
(ANTHROPIC_API_KEY / OPENAI_API_KEY).

Текст промпта тоже редактируется здесь (ключ "prompt"). Пустое значение
значит «стандартный промпт» — prompt.txt из папки кнопки; свой текст
хранится в файле настроек и не теряется при обновлении расширения.

Хранятся в папке конфигурации pyRevit — JSON-файл
%APPDATA%\\pyRevit\\LowLifeEmailTasks_settings.json, тот же подход, что
у остальных кнопок расширения (простой файл вместо
pyrevit.script.get_config(), см. докстринг scs_settings.py про причину).
"""

import os

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from pyrevit import forms

from System.Windows import (
    Window, WindowStartupLocation, Thickness, FontWeights, Visibility,
    HorizontalAlignment, TextWrapping, SizeToContent, SystemParameters
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, PasswordBox, Button, CheckBox, ComboBox,
    Orientation, ScrollViewer, ScrollBarVisibility
)
from System.Windows.Documents import Hyperlink, Run
from System.Windows.Media import Brushes
from System.Diagnostics import Process, ProcessStartInfo

from lowlife import email_ai_core as ai
from lowlife import email_claude, email_codex, settings_core

SETTINGS_FILE_NAME = "LowLifeEmailTasks_settings.json"

REPO_URL = u"https://github.com/avpersiyanov-afk/LowLife"
GUIDE_URL = REPO_URL + u"/blob/main/docs/email-tasks.md"
# Разделы инструкции docs/email-tasks.md (якоря GitHub по заголовкам «### …»)
GUIDE_URLS = {
    ai.CLAUDE_CLI: GUIDE_URL + u"#claude-code-подписка-claude",
    ai.ANTHROPIC_API: GUIDE_URL + u"#anthropic-api-ключ",
    ai.CODEX_CLI: GUIDE_URL + u"#codex-cli-подписка-chatgpt",
    ai.OPENAI_API: GUIDE_URL + u"#openai-api-ключ",
}

DEFAULTS = {
    "days": 3,
    "unread_only": False,
    "include_subfolders": True,
    "subfolder": u"",
    "provider": ai.DEFAULT_PROVIDER,
    "claude_path": u"",
    "codex_path": u"",
    "anthropic_api_key": u"",
    "openai_api_key": u"",
    "test_mode": False,
    "prompt": u"",
}
for _provider in ai.provider_keys():
    DEFAULTS[_provider + "_model"] = ai.DEFAULT_MODELS[_provider]


_STORE = settings_core.JsonStore(SETTINGS_FILE_NAME)


def load():
    values = dict(DEFAULTS)
    stored = _STORE.read()
    # До выбора способа подключения модель Claude Code хранилась под ключом "model"
    if stored.get("model") and not stored.get("claude_cli_model"):
        stored["claude_cli_model"] = stored["model"]
    stored.pop("model", None)
    values.update(stored)
    try:
        values["days"] = max(1, int(values.get("days") or DEFAULTS["days"]))
    except Exception:
        values["days"] = DEFAULTS["days"]
    values["unread_only"] = bool(values.get("unread_only"))
    values["include_subfolders"] = bool(values.get("include_subfolders"))
    values["test_mode"] = bool(values.get("test_mode"))
    values["provider"] = ai.normalize_provider(values.get("provider"))
    for provider in ai.provider_keys():
        key = provider + "_model"
        values[key] = (values.get(key) or u"").strip() or DEFAULTS[key]
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


def _open_url(url):
    # UseShellExecute нужен в Revit 2025+ (.NET 8), иначе ссылка не откроется
    info = ProcessStartInfo(url)
    info.UseShellExecute = True
    Process.Start(info)


def _link(parent, text, url):
    block = TextBlock()
    block.TextWrapping = TextWrapping.Wrap
    block.Margin = Thickness(0, 6, 0, 0)
    link = Hyperlink(Run(text))
    link.ToolTip = url

    def on_click(sender, args):
        try:
            _open_url(url)
        except Exception as ex:
            forms.alert(u"Не удалось открыть ссылку:\n{}\n\n{}".format(url, ex))

    link.Click += on_click
    block.Inlines.Add(link)
    parent.Children.Add(block)
    return block


def _textbox(parent, value):
    box = TextBox()
    box.Text = unicode(value)
    box.Padding = Thickness(4)
    parent.Children.Add(box)
    return box


def _password(parent, value):
    box = PasswordBox()
    box.Password = unicode(value or u"")
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


def _section(parent):
    panel = StackPanel()
    parent.Children.Add(panel)
    return panel


def _key_hint(provider):
    env_name = ai.KEY_ENV_VARS[provider]
    env_key = ai.resolve_key(u"", provider, os.environ)
    found = u"сейчас там {}".format(ai.mask_key(env_key)) if env_key else u"сейчас её нет"
    return (u"Хранится в файле настроек на этом компьютере. Пусто — взять из "
            u"переменной окружения {} ({}).".format(env_name, found))


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

    # --- Подключение ИИ
    _label(root, u"Подключение ИИ", bold=True, top=14)
    provider_combo = ComboBox()
    provider_combo.Padding = Thickness(4)
    for key in ai.provider_keys():
        provider_combo.Items.Add(ai.provider_label(key))
    provider_combo.SelectedIndex = ai.provider_keys().index(values.get("provider"))
    root.Children.Add(provider_combo)
    _hint(root, u"Приложение — работает под вашей подпиской (Claude Pro/Max или ChatGPT "
                u"Plus/Pro), его нужно один раз установить и войти в аккаунт. Ключ API — "
                u"ничего ставить не нужно, но запросы оплачиваются отдельно от подписки, "
                u"по объёму.")
    _link(root, u"Инструкция: все способы подключения", GUIDE_URL + u"#подключение-ии")

    sections = {}
    fields = {}

    # Claude Code
    panel = sections[ai.CLAUDE_CLI] = _section(root)
    _link(panel, u"Как установить Claude Code и войти в аккаунт", GUIDE_URLS[ai.CLAUDE_CLI])
    _label(panel, u"Путь к claude.exe", bold=True, top=10)
    fields["claude_path"] = _textbox(panel, values.get("claude_path"))
    detected = email_claude.find_claude(u"")
    _hint(panel, u"Пусто — искать автоматически (PATH, %USERPROFILE%\\.local\\bin, "
                 u"%APPDATA%\\npm). Сейчас найден: {}".format(detected or u"— не найден —"))
    _label(panel, u"Модель", bold=True, top=10)
    fields["claude_cli_model"] = _textbox(panel, values.get("claude_cli_model"))
    _hint(panel, u"Псевдоним (sonnet, opus, haiku) или полное имя модели — как для "
                 u"`claude --model`. По умолчанию sonnet.")

    # Anthropic API
    panel = sections[ai.ANTHROPIC_API] = _section(root)
    _link(panel, u"Как получить ключ Anthropic API", GUIDE_URLS[ai.ANTHROPIC_API])
    _label(panel, u"Ключ Anthropic API", bold=True, top=10)
    fields["anthropic_api_key"] = _password(panel, values.get("anthropic_api_key"))
    _hint(panel, _key_hint(ai.ANTHROPIC_API))
    _label(panel, u"Модель", bold=True, top=10)
    fields["anthropic_api_model"] = _textbox(panel, values.get("anthropic_api_model"))
    _hint(panel, u"Полное имя (claude-opus-5-5, claude-sonnet-5-5, claude-haiku-4-5) или "
                 u"псевдоним opus / sonnet / haiku. По умолчанию {}."
                 .format(ai.DEFAULT_MODELS[ai.ANTHROPIC_API]))

    # Codex CLI
    panel = sections[ai.CODEX_CLI] = _section(root)
    _link(panel, u"Как установить Codex CLI и войти в аккаунт ChatGPT", GUIDE_URLS[ai.CODEX_CLI])
    _label(panel, u"Путь к codex", bold=True, top=10)
    fields["codex_path"] = _textbox(panel, values.get("codex_path"))
    detected = email_codex.find_codex(u"")
    _hint(panel, u"Пусто — искать автоматически (PATH, %APPDATA%\\npm, "
                 u"%USERPROFILE%\\.local\\bin). Сейчас найден: {}".format(detected or u"— не найден —"))
    _label(panel, u"Модель", bold=True, top=10)
    fields["codex_cli_model"] = _textbox(panel, values.get("codex_cli_model"))
    _hint(panel, u"Как для `codex -m`. Пусто — модель по умолчанию из настроек Codex.")

    # OpenAI API
    panel = sections[ai.OPENAI_API] = _section(root)
    _link(panel, u"Как получить ключ OpenAI API", GUIDE_URLS[ai.OPENAI_API])
    _label(panel, u"Ключ OpenAI API", bold=True, top=10)
    fields["openai_api_key"] = _password(panel, values.get("openai_api_key"))
    _hint(panel, _key_hint(ai.OPENAI_API))
    _label(panel, u"Модель", bold=True, top=10)
    fields["openai_api_model"] = _textbox(panel, values.get("openai_api_model"))
    _hint(panel, u"Имя модели OpenAI, например gpt-5 или gpt-5-mini. По умолчанию {}."
                 .format(ai.DEFAULT_MODELS[ai.OPENAI_API]))

    def selected_provider():
        index = provider_combo.SelectedIndex
        keys = ai.provider_keys()
        return keys[index] if 0 <= index < len(keys) else ai.DEFAULT_PROVIDER

    def show_section(sender=None, args=None):
        current = selected_provider()
        for key, section in sections.items():
            section.Visibility = Visibility.Visible if key == current else Visibility.Collapsed

    provider_combo.SelectionChanged += show_section
    show_section()

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

        provider = selected_provider()
        claude_path = fields["claude_path"].Text.strip().strip('"')
        codex_path = fields["codex_path"].Text.strip().strip('"')
        keys = {
            ai.ANTHROPIC_API: fields["anthropic_api_key"].Password.strip(),
            ai.OPENAI_API: fields["openai_api_key"].Password.strip(),
        }
        # Проверяем только выбранный способ: остальные могут быть не настроены
        if provider == ai.CLAUDE_CLI and claude_path and email_claude.find_claude(claude_path) is None:
            forms.alert(u"По указанному пути claude не найден:\n{}\n\n"
                        u"Укажите полный путь к claude.exe или оставьте поле "
                        u"пустым для автопоиска.".format(claude_path))
            return
        if provider == ai.CODEX_CLI and codex_path and email_codex.find_codex(codex_path) is None:
            forms.alert(u"По указанному пути codex не найден:\n{}\n\n"
                        u"Укажите полный путь к codex или оставьте поле "
                        u"пустым для автопоиска.".format(codex_path))
            return
        if provider in keys and not ai.resolve_key(keys[provider], provider, os.environ):
            forms.alert(u"Вставьте ключ API — или выберите другой способ подключения.\n\n"
                        u"Где взять ключ — по ссылке «Как получить ключ» в окне настроек.")
            return

        new_values = {
            "days": days,
            "unread_only": bool(unread_box.IsChecked),
            "include_subfolders": bool(subfolders_box.IsChecked),
            "subfolder": subfolder_box.Text.strip(),
            "provider": provider,
            "claude_path": claude_path,
            "codex_path": codex_path,
            "anthropic_api_key": keys[ai.ANTHROPIC_API],
            "openai_api_key": keys[ai.OPENAI_API],
            "test_mode": bool(test_box.IsChecked),
            # Совпадает со стандартным — храним пусто, чтобы правки prompt.txt
            # в новых версиях расширения подхватывались сами
            "prompt": u"" if _same_text(prompt_box.Text, default_prompt) else prompt_box.Text,
        }
        for key in ai.provider_keys():
            name = key + "_model"
            new_values[name] = fields[name].Text.strip() or DEFAULTS[name]
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
