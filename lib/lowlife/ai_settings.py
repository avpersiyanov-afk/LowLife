# -*- coding: utf-8 -*-
"""
Общее подключение ИИ для кнопок «Задачи из почты» (Mail.panel/EmailTasks)
и «Проверка орфографии» (Tools.panel/SpellCheck): хранение и блок окна
настроек «Подключение ИИ».

Способ подключения — ключ "provider" (см. email_ai_core.PROVIDERS):
Claude Code / Anthropic API / Codex CLI / OpenAI API. У каждого способа
свои поля: путь к программе (claude_path, codex_path) или ключ API
(anthropic_api_key, openai_api_key) и модель (<provider>_model). Ключи
хранятся в файле настроек пользователя открытым текстом; пустое поле
ключа — взять из переменной окружения (ANTHROPIC_API_KEY / OPENAI_API_KEY).

Подключение одно на все кнопки: эти ключи лежат в файле настроек «Задач
из почты» (%APPDATA%\\pyRevit\\LowLifeEmailTasks_settings.json — там они
были с самого начала), поэтому настроенный один раз ИИ сразу работает и в
проверке орфографии, и наоборот.
"""

try:
    unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3
    unicode = str


import clr
from lowlife.i18n import tr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from pyrevit import forms

from System.Windows import Thickness, FontWeights, Visibility, TextWrapping
from System.Windows.Controls import StackPanel, TextBlock, TextBox, PasswordBox, CheckBox, ComboBox
from System.Windows.Documents import Hyperlink, Run
from System.Windows.Media import Brushes
from System.Diagnostics import Process, ProcessStartInfo

from lowlife import email_ai_core as ai
from lowlife import email_claude, email_codex

# Хранение подключения — без окон, его читает и отдельное приложение (apps/mail)
from lowlife.ai_settings_core import (  # noqa: F401 — прежние имена
    SETTINGS_FILE_NAME, REPO_URL, GUIDE_URL, GUIDE_URLS, DEFAULTS, KEYS, normalize, load, save, validate, key_hint
)


# ------------------------------------------------------------ элементы окна

def label(parent, text, bold=False, top=10):
    block = TextBlock()
    block.Text = text
    block.TextWrapping = TextWrapping.Wrap
    block.Margin = Thickness(0, top, 0, 2)
    if bold:
        block.FontWeight = FontWeights.Bold
    parent.Children.Add(block)
    return block


def hint(parent, text):
    block = TextBlock()
    block.Text = text
    block.FontSize = 11
    block.Foreground = Brushes.Gray
    block.TextWrapping = TextWrapping.Wrap
    block.Margin = Thickness(0, 2, 0, 0)
    parent.Children.Add(block)
    return block


def open_url(url):
    # UseShellExecute нужен в Revit 2025+ (.NET 8), иначе ссылка не откроется
    info = ProcessStartInfo(url)
    info.UseShellExecute = True
    Process.Start(info)


def link(parent, text, url):
    block = TextBlock()
    block.TextWrapping = TextWrapping.Wrap
    block.Margin = Thickness(0, 6, 0, 0)
    hyperlink = Hyperlink(Run(text))
    hyperlink.ToolTip = url

    def on_click(sender, args):
        try:
            open_url(url)
        except Exception as ex:
            forms.alert(tr(u"Не удалось открыть ссылку:\n{}\n\n{}").format(url, ex))

    hyperlink.Click += on_click
    block.Inlines.Add(hyperlink)
    parent.Children.Add(block)
    return block


def textbox(parent, value):
    box = TextBox()
    box.Text = unicode(value)
    box.Padding = Thickness(4)
    parent.Children.Add(box)
    return box


def password(parent, value):
    box = PasswordBox()
    box.Password = unicode(value or u"")
    box.Padding = Thickness(4)
    parent.Children.Add(box)
    return box


def checkbox(parent, text, value):
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


# -------------------------------------------------- блок «Подключение ИИ»

class ConnectionSection(object):
    """Блок «Подключение ИИ» в окне настроек: выбор способа и поля только
    выбранного способа. validate() — текст ошибки или None, read() —
    словарь ключей подключения (KEYS)."""

    def __init__(self, root, values, shared_note=None):
        label(root, tr(u"Подключение ИИ"), bold=True, top=14)
        self._combo = ComboBox()
        self._combo.Padding = Thickness(4)
        for key in ai.provider_keys():
            self._combo.Items.Add(ai.provider_label(key))
        self._combo.SelectedIndex = ai.provider_keys().index(
            ai.normalize_provider(values.get("provider")))
        root.Children.Add(self._combo)
        hint(root, tr(u"Приложение — работает под вашей подпиской (Claude Pro/Max или ChatGPT "
                   u"Plus/Pro), его нужно один раз установить и войти в аккаунт. Ключ API — "
                   u"ничего ставить не нужно, но запросы оплачиваются отдельно от подписки, "
                   u"по объёму."))
        if shared_note:
            hint(root, shared_note)
        link(root, tr(u"Инструкция: все способы подключения"), GUIDE_URL + u"#подключение-ии")

        self._sections = {}
        fields = self._fields = {}

        # Claude Code
        panel = self._sections[ai.CLAUDE_CLI] = _section(root)
        link(panel, tr(u"Как установить Claude Code и войти в аккаунт"), GUIDE_URLS[ai.CLAUDE_CLI])
        label(panel, tr(u"Путь к claude.exe"), bold=True, top=10)
        fields["claude_path"] = textbox(panel, values.get("claude_path"))
        detected = email_claude.find_claude(u"")
        hint(panel, tr(u"Пусто — искать автоматически (PATH, %USERPROFILE%\\.local\\bin, "
                    u"%APPDATA%\\npm). Сейчас найден: {}").format(detected or tr(u"— не найден —")))
        label(panel, tr(u"Модель"), bold=True, top=10)
        fields["claude_cli_model"] = textbox(panel, values.get("claude_cli_model"))
        hint(panel, tr(u"Псевдоним (sonnet, opus, haiku) или полное имя модели — как для "
                    u"`claude --model`. По умолчанию sonnet."))

        # Anthropic API
        panel = self._sections[ai.ANTHROPIC_API] = _section(root)
        link(panel, tr(u"Как получить ключ Anthropic API"), GUIDE_URLS[ai.ANTHROPIC_API])
        label(panel, tr(u"Ключ Anthropic API"), bold=True, top=10)
        fields["anthropic_api_key"] = password(panel, values.get("anthropic_api_key"))
        hint(panel, key_hint(ai.ANTHROPIC_API))
        label(panel, tr(u"Модель"), bold=True, top=10)
        fields["anthropic_api_model"] = textbox(panel, values.get("anthropic_api_model"))
        hint(panel, tr(u"Полное имя (claude-opus-5-5, claude-sonnet-5-5, claude-haiku-4-5) или "
                    u"псевдоним opus / sonnet / haiku. По умолчанию {}.")
                    .format(ai.DEFAULT_MODELS[ai.ANTHROPIC_API]))

        # Codex CLI
        panel = self._sections[ai.CODEX_CLI] = _section(root)
        link(panel, tr(u"Как установить Codex CLI и войти в аккаунт ChatGPT"), GUIDE_URLS[ai.CODEX_CLI])
        label(panel, tr(u"Путь к codex"), bold=True, top=10)
        fields["codex_path"] = textbox(panel, values.get("codex_path"))
        detected = email_codex.find_codex(u"")
        hint(panel, tr(u"Пусто — искать автоматически (PATH, %APPDATA%\\npm, "
                    u"%USERPROFILE%\\.local\\bin). Сейчас найден: {}").format(detected or tr(u"— не найден —")))
        label(panel, tr(u"Модель"), bold=True, top=10)
        fields["codex_cli_model"] = textbox(panel, values.get("codex_cli_model"))
        hint(panel, tr(u"Как для `codex -m`. Пусто — модель по умолчанию из настроек Codex."))

        # OpenAI API
        panel = self._sections[ai.OPENAI_API] = _section(root)
        link(panel, tr(u"Как получить ключ OpenAI API"), GUIDE_URLS[ai.OPENAI_API])
        label(panel, tr(u"Ключ OpenAI API"), bold=True, top=10)
        fields["openai_api_key"] = password(panel, values.get("openai_api_key"))
        hint(panel, key_hint(ai.OPENAI_API))
        label(panel, tr(u"Модель"), bold=True, top=10)
        fields["openai_api_model"] = textbox(panel, values.get("openai_api_model"))
        hint(panel, tr(u"Имя модели OpenAI, например gpt-5 или gpt-5-mini. По умолчанию {}.")
                    .format(ai.DEFAULT_MODELS[ai.OPENAI_API]))

        self._combo.SelectionChanged += self._show_section
        self._show_section()

    def selected_provider(self):
        index = self._combo.SelectedIndex
        keys = ai.provider_keys()
        return keys[index] if 0 <= index < len(keys) else ai.DEFAULT_PROVIDER

    def _show_section(self, sender=None, args=None):
        current = self.selected_provider()
        for key, section in self._sections.items():
            section.Visibility = Visibility.Visible if key == current else Visibility.Collapsed

    def read(self):
        fields = self._fields
        values = {
            "provider": self.selected_provider(),
            "claude_path": fields["claude_path"].Text.strip().strip('"'),
            "codex_path": fields["codex_path"].Text.strip().strip('"'),
            "anthropic_api_key": fields["anthropic_api_key"].Password.strip(),
            "openai_api_key": fields["openai_api_key"].Password.strip(),
        }
        for key in ai.provider_keys():
            name = key + "_model"
            values[name] = fields[name].Text.strip() or DEFAULTS[name]
        return values

    def validate(self):
        """Проверяет только выбранный способ: остальные могут быть не настроены."""
        return validate(self.read())
