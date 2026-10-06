# -*- coding: utf-8 -*-
"""
Выбор способа подключения ИИ для кнопки «Задачи из почты» (ключ "provider"
в настройках) и единый вызов для script.py:

    engine = email_ai.prepare(settings)   # AIError — не найдено / нет ключа
    engine = email_ai.prepare(settings, system_prompt=...)  # свой системный промпт
    answer = engine.run(request_text, tick)

Способы: Claude Code (email_claude.py), Codex CLI (email_codex.py),
Anthropic API и OpenAI API (POST через email_ai_net.post_json, тела
запросов и разбор ответов — email_ai_core.py).
"""

import os

from lowlife import email_ai_core as core
from lowlife import email_ai_net, email_claude, email_codex
from lowlife.email_ai_core import AIError, Cancelled  # noqa: F401 — для script.py


class Engine(object):
    def __init__(self, provider, model, runner):
        self.provider = provider
        self.model = model
        self._runner = runner
        self.name = core.provider_short_name(provider)

    @property
    def description(self):
        """Для отчёта: «Claude Code, модель sonnet»."""
        kind = {
            core.CLAUDE_CLI: u"Claude Code",
            core.ANTHROPIC_API: u"Anthropic API",
            core.CODEX_CLI: u"Codex CLI",
            core.OPENAI_API: u"OpenAI API",
        }.get(self.provider, self.provider)
        return u"{}, модель {}".format(kind, self.model or u"по умолчанию")

    def run(self, request_text, tick=None):
        return self._runner(request_text, tick)


def model_for(settings, provider):
    return (settings.get(provider + "_model") or u"").strip() or core.DEFAULT_MODELS[provider]


def prepare(settings, system_prompt=None):
    """Engine для выбранного в настройках способа или AIError с подсказкой.
    system_prompt — системный промпт; None — промпт разбора писем."""
    system = system_prompt or core.SYSTEM_PROMPT
    provider = core.normalize_provider(settings.get("provider"))
    model = model_for(settings, provider)

    if provider == core.CLAUDE_CLI:
        configured = settings.get("claude_path") or u""
        path = email_claude.find_claude(configured)
        if path is None:
            raise AIError(_not_found_message(
                u"Claude Code (claude.exe)", configured,
                u"%USERPROFILE%\\.local\\bin, %APPDATA%\\npm", u"claude"), fatal=True)
        return Engine(provider, model,
                      lambda text, tick: email_claude.run_claude(path, model, text, tick=tick, system=system))

    if provider == core.CODEX_CLI:
        configured = settings.get("codex_path") or u""
        path = email_codex.find_codex(configured)
        if path is None:
            raise AIError(_not_found_message(
                u"Codex CLI (codex)", configured,
                u"%APPDATA%\\npm, %USERPROFILE%\\.local\\bin", u"codex"), fatal=True)
        return Engine(provider, model,
                      lambda text, tick: email_codex.run_codex(path, model, text, tick=tick, system=system))

    key = core.resolve_key(settings.get(provider + "_key"), provider, os.environ)
    if not key:
        raise AIError(u"Не указан ключ {}.\n\nВставьте ключ в настройках кнопки "
                      u"(Shift+клик) — там же ссылка на инструкцию, где его взять."
                      .format(u"Anthropic API" if provider == core.ANTHROPIC_API else u"OpenAI API"),
                      fatal=True)
    if provider == core.ANTHROPIC_API:
        model = core.anthropic_model(model)
        return Engine(provider, model, lambda text, tick: _run_api(
            provider, core.ANTHROPIC_URL, core.anthropic_request(key, model, text, system),
            core.parse_anthropic_response, tick))
    return Engine(provider, model, lambda text, tick: _run_api(
        provider, core.OPENAI_URL, core.openai_request(key, model, text, system),
        core.parse_openai_response, tick))


def _run_api(provider, url, request, parse, tick):
    headers, body = request
    status, text = email_ai_net.post_json(url, headers, body, tick=tick)
    if status != 200:
        raise core.classify_http_error(provider, status, text)
    return parse(text)


def _not_found_message(what, configured, folders, command):
    if configured:
        return (u"{} не найден по пути из настроек:\n{}\n\n"
                u"Исправьте путь (Shift+клик по кнопке) или очистите поле для "
                u"автопоиска.".format(what, configured))
    return (u"{} не найден: нет ни в PATH, ни в {}.\n\n"
            u"Установите программу по инструкции (ссылка в настройках — Shift+клик) "
            u"или укажите полный путь к ней в настройках. Узнать путь можно "
            u"командой `where.exe {}` в командной строке.".format(what, folders, command))
