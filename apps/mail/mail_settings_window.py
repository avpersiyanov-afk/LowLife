# -*- coding: utf-8 -*-
"""Окно настроек приложения «Задачи из почты» — те же поля, что у кнопки в
Revit (Shift+клик): подключение ИИ, период, папка, тестовый режим, промпт.
Хранение и проверка — lowlife.email_tasks_settings_core / ai_settings_core."""

import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from lowlife import ai_settings_core, email_claude, email_codex
from lowlife import email_ai_core as ai
from lowlife import email_tasks_settings_core as settings_core
from lowlife.email_app_core import app_text

TITLE = u"Настройки: Задачи из почты"
WRAP = 620


class _Form(object):
    def __init__(self, parent):
        self.parent = parent

    def label(self, text, bold=False, top=10):
        font = (u"Segoe UI", 9, u"bold") if bold else None
        ttk.Label(self.parent, text=text, font=font, wraplength=WRAP).pack(anchor=tk.W, pady=(top, 2))

    def hint(self, text):
        ttk.Label(self.parent, text=text, foreground=u"gray", wraplength=WRAP,
                  font=(u"Segoe UI", 8)).pack(anchor=tk.W, pady=(2, 0))

    def link(self, text, url):
        widget = ttk.Label(self.parent, text=text, foreground=u"#1a5fb4", cursor=u"hand2", wraplength=WRAP)
        widget.pack(anchor=tk.W, pady=(6, 0))
        widget.bind(u"<Button-1>", lambda _e: webbrowser.open(url))

    def entry(self, value, secret=False):
        var = tk.StringVar(value=u"{}".format(value or u""))
        ttk.Entry(self.parent, textvariable=var, show=u"•" if secret else u"").pack(fill=tk.X)
        return var

    def check(self, text, value):
        var = tk.BooleanVar(value=bool(value))
        ttk.Checkbutton(self.parent, text=text, variable=var).pack(anchor=tk.W, pady=(10, 0))
        return var


class SettingsWindow(object):
    def __init__(self, master, values, default_prompt):
        self.default_prompt = default_prompt
        self.result = None

        win = self.win = tk.Toplevel(master)
        win.title(TITLE)
        win.geometry(u"700x720")
        win.transient(master)

        # Прокручиваемая область — окно длиннее экрана ноутбука
        canvas = tk.Canvas(win, highlightthickness=0)
        scroll = ttk.Scrollbar(win, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        bottom = ttk.Frame(win, padding=(16, 8))
        bottom.pack(side=tk.BOTTOM, fill=tk.X)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        body = ttk.Frame(canvas, padding=16)
        body_id = canvas.create_window((0, 0), window=body, anchor=u"nw")
        body.bind(u"<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox(u"all")))
        canvas.bind(u"<Configure>", lambda e: canvas.itemconfigure(body_id, width=e.width))
        win.bind_all(u"<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), u"units"))

        form = _Form(body)
        ttk.Label(body, text=u"Задачи из почты", font=(u"Segoe UI", 12, u"bold")).pack(anchor=tk.W)
        form.hint(u"Программа только читает почту: ничего не отправляет, не помечает прочитанным "
                  u"и не перемещает.")

        self._build_connection(body, form, values)

        form.label(u"Период, дней", bold=True, top=18)
        self.days = form.entry(values.get("days"))
        form.hint(u"Сколько последних дней «Входящих» разбирать (по дате получения).")
        self.unread = form.check(u"Только непрочитанные", values.get("unread_only"))

        form.label(u"Подпапка «Входящих»", bold=True, top=14)
        self.subfolder = form.entry(values.get("subfolder"))
        form.hint(u"Пусто — сами «Входящие». Вложенные папки — через «/», например «Проекты/Объект 1».")
        self.subfolders = form.check(u"Включая подпапки", values.get("include_subfolders"))
        form.hint(u"Читать и все вложенные папки — «Входящих» или папки, указанной выше.")
        self.test_mode = form.check(u"Тестовый режим", values.get("test_mode"))
        form.hint(u"Вместо Outlook взять встроенные тестовые письма — проверить подключение ИИ.")

        form.label(u"Промпт", bold=True, top=18)
        prompt_frame = ttk.Frame(body)
        prompt_frame.pack(fill=tk.X)
        self.prompt = tk.Text(prompt_frame, height=14, wrap=tk.WORD, undo=True)
        prompt_scroll = ttk.Scrollbar(prompt_frame, orient=tk.VERTICAL, command=self.prompt.yview)
        self.prompt.configure(yscrollcommand=prompt_scroll.set)
        self.prompt.pack(side=tk.LEFT, fill=tk.X, expand=True)
        prompt_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.prompt.insert(u"1.0", settings_core.effective_prompt(values, default_prompt))
        form.hint(u"Общий для всех способов подключения. Сегодняшняя дата и сами письма добавляются "
                  u"к промпту автоматически. Сохраните в тексте формат ответа {\"tasks\":[{\"email_id\":…,"
                  u"\"task\":…,\"requester\":…,\"deadline\":…,\"priority\":…,\"comment\":…}]} — по нему "
                  u"разбирается ответ.")
        ttk.Button(body, text=u"Вернуть стандартный промпт", command=self.on_reset).pack(
            anchor=tk.W, pady=(6, 0))

        ttk.Button(bottom, text=u"Сохранить", command=self.on_ok).pack(side=tk.RIGHT)
        ttk.Button(bottom, text=u"Отмена", command=self.win.destroy).pack(side=tk.RIGHT, padx=(0, 8))
        win.bind(u"<Escape>", lambda _e: win.destroy())

    def _build_connection(self, body, form, values):
        form.label(u"Подключение ИИ", bold=True, top=14)
        keys = ai.provider_keys()
        self.provider = ttk.Combobox(body, state=u"readonly", values=[ai.provider_label(k) for k in keys])
        self.provider.current(keys.index(ai.normalize_provider(values.get("provider"))))
        self.provider.pack(fill=tk.X)
        form.hint(u"Приложение — работает под вашей подпиской (Claude Pro/Max или ChatGPT Plus/Pro), "
                  u"его нужно один раз установить и войти в аккаунт. Ключ API — ничего ставить не "
                  u"нужно, но запросы оплачиваются отдельно от подписки, по объёму.")
        form.link(u"Инструкция: все способы подключения", ai_settings_core.GUIDE_URL + u"#подключение-ии")

        self.sections_host = ttk.Frame(body)
        self.sections_host.pack(fill=tk.X)
        self.sections = {}
        self.fields = {}
        urls = ai_settings_core.GUIDE_URLS

        sub = self._section(ai.CLAUDE_CLI)
        sub.link(u"Как установить Claude Code и войти в аккаунт", urls[ai.CLAUDE_CLI])
        sub.label(u"Путь к claude.exe", bold=True)
        self.fields["claude_path"] = sub.entry(values.get("claude_path"))
        sub.hint(u"Пусто — искать автоматически (PATH, %USERPROFILE%\\.local\\bin, %APPDATA%\\npm). "
                 u"Сейчас найден: {}".format(email_claude.find_claude(u"") or u"— не найден —"))
        sub.label(u"Модель", bold=True)
        self.fields["claude_cli_model"] = sub.entry(values.get("claude_cli_model"))
        sub.hint(u"Псевдоним (sonnet, opus, haiku) или полное имя модели — как для `claude --model`. "
                 u"По умолчанию sonnet.")

        sub = self._section(ai.ANTHROPIC_API)
        sub.link(u"Как получить ключ Anthropic API", urls[ai.ANTHROPIC_API])
        sub.label(u"Ключ Anthropic API", bold=True)
        self.fields["anthropic_api_key"] = sub.entry(values.get("anthropic_api_key"), secret=True)
        sub.hint(ai_settings_core.key_hint(ai.ANTHROPIC_API))
        sub.label(u"Модель", bold=True)
        self.fields["anthropic_api_model"] = sub.entry(values.get("anthropic_api_model"))
        sub.hint(u"Полное имя (claude-opus-5-5, claude-sonnet-5-5, claude-haiku-4-5) или псевдоним "
                 u"opus / sonnet / haiku. По умолчанию {}.".format(ai.DEFAULT_MODELS[ai.ANTHROPIC_API]))

        sub = self._section(ai.CODEX_CLI)
        sub.link(u"Как установить Codex CLI и войти в аккаунт ChatGPT", urls[ai.CODEX_CLI])
        sub.label(u"Путь к codex", bold=True)
        self.fields["codex_path"] = sub.entry(values.get("codex_path"))
        sub.hint(u"Пусто — искать автоматически (PATH, %APPDATA%\\npm, %USERPROFILE%\\.local\\bin). "
                 u"Сейчас найден: {}".format(email_codex.find_codex(u"") or u"— не найден —"))
        sub.label(u"Модель", bold=True)
        self.fields["codex_cli_model"] = sub.entry(values.get("codex_cli_model"))
        sub.hint(u"Как для `codex -m`. Пусто — модель по умолчанию из настроек Codex.")

        sub = self._section(ai.OPENAI_API)
        sub.link(u"Как получить ключ OpenAI API", urls[ai.OPENAI_API])
        sub.label(u"Ключ OpenAI API", bold=True)
        self.fields["openai_api_key"] = sub.entry(values.get("openai_api_key"), secret=True)
        sub.hint(ai_settings_core.key_hint(ai.OPENAI_API))
        sub.label(u"Модель", bold=True)
        self.fields["openai_api_model"] = sub.entry(values.get("openai_api_model"))
        sub.hint(u"Имя модели OpenAI, например gpt-5 или gpt-5-mini. По умолчанию {}.".format(
            ai.DEFAULT_MODELS[ai.OPENAI_API]))

        self.provider.bind(u"<<ComboboxSelected>>", lambda _e: self._show_section())
        self._show_section()

    def _section(self, provider):
        frame = ttk.Frame(self.sections_host)
        self.sections[provider] = frame
        return _Form(frame)

    def selected_provider(self):
        index = self.provider.current()
        keys = ai.provider_keys()
        return keys[index] if 0 <= index < len(keys) else ai.DEFAULT_PROVIDER

    def _show_section(self):
        current = self.selected_provider()
        for key, frame in self.sections.items():
            if key == current:
                frame.pack(fill=tk.X)
            else:
                frame.pack_forget()

    def _connection(self):
        f = self.fields
        values = {
            "provider": self.selected_provider(),
            "claude_path": f["claude_path"].get().strip().strip('"'),
            "codex_path": f["codex_path"].get().strip().strip('"'),
            "anthropic_api_key": f["anthropic_api_key"].get().strip(),
            "openai_api_key": f["openai_api_key"].get().strip(),
        }
        for key in ai.provider_keys():
            name = key + "_model"
            values[name] = f[name].get().strip() or ai_settings_core.DEFAULTS[name]
        return values

    def on_reset(self):
        self.prompt.delete(u"1.0", tk.END)
        self.prompt.insert(u"1.0", self.default_prompt)

    def on_ok(self):
        days = settings_core.parse_days(self.days.get())
        if days is None:
            messagebox.showerror(TITLE, u"Период — целое число дней, не меньше 1.", parent=self.win)
            return
        connection = self._connection()
        error = ai_settings_core.validate(connection)
        if error:
            messagebox.showerror(TITLE, app_text(error), parent=self.win)
            return
        values = {
            "days": days,
            "unread_only": bool(self.unread.get()),
            "include_subfolders": bool(self.subfolders.get()),
            "subfolder": self.subfolder.get().strip(),
            "test_mode": bool(self.test_mode.get()),
            "prompt": settings_core.stored_prompt(self.prompt.get(u"1.0", u"end-1c"), self.default_prompt),
        }
        values.update(connection)
        self.result = values
        self.win.destroy()


def edit(master, default_prompt):
    """Модальное окно настроек. True — сохранено."""
    stored = settings_core.load()
    window = SettingsWindow(master, stored, default_prompt)
    window.win.grab_set()
    master.wait_window(window.win)
    master.unbind_all(u"<MouseWheel>")
    if window.result is None:
        return False
    # Ключи, которых нет в окне (их могла записать кнопка в Revit), не теряем
    merged = dict(stored)
    merged.update(window.result)
    if not settings_core.save(merged):
        messagebox.showerror(TITLE, u"Не удалось сохранить настройки в файл:\n{}".format(
            settings_core.settings_path()), parent=master)
        return False
    return True
