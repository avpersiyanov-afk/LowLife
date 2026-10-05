# -*- coding: utf-8 -*-
"""
Вызов Claude Code CLI в headless-режиме (claude -p) для кнопки «Задачи из
почты» (способ подключения "claude_cli"). Работает под подпиской, под
которой залогинен Claude Code, — API-ключ не нужен.

Запрос (промпт + письма) уходит через stdin в UTF-8, а не аргументом
командной строки (см. email_ai_net.run_process). Флаги (проверены по
`claude --help`, Claude Code 2.1.x):

    -p                         неинтерактивный режим: напечатать ответ и выйти
    --output-format json       один JSON-объект с полями result/is_error/...
    --model <alias|name>       модель (по умолчанию sonnet)
    --tools ""                 без инструментов (ни Bash, ни чтения файлов)
    --max-turns 1              один ход, без агентного цикла
    --no-session-persistence   не сохранять сессию на диск
    --strict-mcp-config        не поднимать MCP-серверы из настроек пользователя
    --system-prompt <text>     короткий системный промпт вместо промпта Claude Code

Процесс запускается в отдельной временной папке, чтобы CLI не подхватил
CLAUDE.md случайного рабочего каталога Revit.
"""

import os
import json

from lowlife import email_ai_net
from lowlife.email_ai_core import AIError, Cancelled, SYSTEM_PROMPT, DEFAULT_MODELS, CLAUDE_CLI  # noqa: F401 — Cancelled: прежнее имя

DEFAULT_MODEL = DEFAULT_MODELS[CLAUDE_CLI]
TIMEOUT_SECONDS = email_ai_net.TIMEOUT_SECONDS

# Прежние имена — для совместимости
ClaudeError = AIError
_quote = email_ai_net.quote


def find_claude(configured_path=u""):
    """
    Путь к claude или None. Порядок: путь из настроек → PATH →
    %USERPROFILE%\\.local\\bin\\claude.exe (нативный установщик) →
    %APPDATA%\\npm\\claude.cmd (установка через npm).
    """
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    appdata = os.environ.get("APPDATA") or u""
    extra = [os.path.join(home, u".local", u"bin", u"claude.exe")]
    if appdata:
        extra.append(os.path.join(appdata, u"npm", u"claude.cmd"))
    return email_ai_net.find_executable(
        configured_path, [u"claude.exe", u"claude.cmd", u"claude"], extra)


def build_arguments(model):
    return [
        u"-p",
        u"--output-format", u"json",
        u"--model", model or DEFAULT_MODEL,
        u"--tools", u"",
        u"--max-turns", u"1",
        u"--no-session-persistence",
        u"--strict-mcp-config",
        u"--system-prompt", SYSTEM_PROMPT,
    ]


def _classify_failure(text):
    low = (text or u"").lower()
    if any(k in low for k in (u"not logged in", u"/login", u"please run", u"invalid api key",
                              u"authentication", u"unauthorized", u"oauth", u"http 401")):
        return AIError(
            u"Claude Code не залогинен (или вход устарел).\n\n"
            u"Откройте командную строку, запустите `claude` и выполните /login, "
            u"затем повторите.", fatal=True, details=text)
    if any(k in low for k in (u"usage limit", u"rate limit", u"limit reached", u"hit your limit",
                              u"limit will reset", u"http 429", u"quota")):
        return AIError(
            u"Claude упёрся в лимит использования подписки.\n\n"
            u"Подождите, пока лимит сбросится (время сброса — в тексте ниже), "
            u"или уменьшите период в настройках.", fatal=True, details=text)
    if u"unknown option" in low or u"error: option" in low:
        return AIError(
            u"Установленная версия Claude Code не поддерживает нужные флаги.\n\n"
            u"Обновите её: `claude update` в командной строке.", fatal=True, details=text)
    if u"selected model" in low or u"unrecognized_model" in low or u"model not found" in low:
        return AIError(
            u"Модель недоступна или указана с ошибкой.\n\n"
            u"Проверьте поле «Модель» в настройках (Shift+клик): например "
            u"sonnet, opus или haiku.", fatal=True, details=text)
    if u"overloaded" in low or u"http 529" in low:
        return AIError(u"Сервис Claude перегружен — попробуйте чуть позже.",
                       fatal=True, details=text)
    return AIError(u"Claude вернул ошибку.", fatal=False, details=text)


def _parse_cli_json(stdout):
    """Объект результата из stdout claude --output-format json."""
    text = (stdout or u"").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    # На всякий случай: предупреждения перед JSON — берём последнюю строку-объект
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith(u"{"):
            try:
                return json.loads(line)
            except Exception:
                continue
    return None


def run_claude(claude_path, model, request_text, tick=None, timeout_seconds=TIMEOUT_SECONDS):
    """
    Запускает claude -p, отдаёт request_text в stdin, возвращает текст
    ответа модели (поле result). tick() — см. email_ai_net.run_process.
    """
    exit_code, stdout, stderr = email_ai_net.run_process(
        claude_path, build_arguments(model), request_text, u"claude",
        tick=tick, timeout_seconds=timeout_seconds)

    result = _parse_cli_json(stdout)
    if result is None:
        if exit_code != 0 or stderr.strip():
            raise _classify_failure(u"код выхода {}\n{}\n{}".format(
                exit_code, stderr.strip(), stdout.strip()).strip())
        raise AIError(u"claude ничего не вернул (код выхода {}).".format(exit_code))

    if result.get("is_error") or exit_code != 0:
        text = u"{}\n{}".format(result.get("result") or u"", stderr).strip()
        if result.get("api_error_status"):
            text = u"HTTP {}: {}".format(result.get("api_error_status"), text)
        if result.get("subtype") == u"error_max_turns":
            text = u"error_max_turns: модель попыталась сделать больше одного хода.\n" + text
        raise _classify_failure(text or u"код выхода {}".format(exit_code))

    answer = result.get("result")
    if not answer:
        raise AIError(u"В ответе claude нет текста (поле result пустое).", details=stdout)
    return unicode(answer)
