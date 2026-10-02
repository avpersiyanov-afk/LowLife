# -*- coding: utf-8 -*-
"""
Вызов Claude Code CLI в headless-режиме (claude -p) для кнопки «Задачи из
почты». Работает под подпиской, под которой залогинен Claude Code, —
API-ключ не нужен.

Запрос (промпт + письма) уходит через stdin в UTF-8, а не аргументом
командной строки: у Windows ограничение на длину командной строки
(~32k символов), а пачка писем — около 30k. Флаги (проверены по
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

import clr
clr.AddReference("System")

from System.Diagnostics import Process, ProcessStartInfo
from System.Text import UTF8Encoding, Encoding

DEFAULT_MODEL = u"sonnet"
TIMEOUT_SECONDS = 180

_SYSTEM_PROMPT = (
    u"You extract action items from work emails for the user. "
    u"Follow the instructions in the message exactly and reply with JSON only."
)


class ClaudeError(Exception):
    """Ошибка вызова claude с понятным пользователю текстом. fatal=True —
    продолжать следующие пачки бессмысленно (не найден, не залогинен, лимит)."""

    def __init__(self, message, fatal=False, details=u""):
        Exception.__init__(self, message)
        self.message = message
        self.fatal = fatal
        self.details = details


class Cancelled(Exception):
    pass


def _candidates_from_path():
    names = [u"claude.exe", u"claude.cmd", u"claude"]
    for folder in (os.environ.get("PATH") or u"").split(os.pathsep):
        folder = folder.strip().strip('"')
        if not folder:
            continue
        for name in names:
            yield os.path.join(folder, name)


def find_claude(configured_path=u""):
    """
    Путь к claude или None. Порядок: путь из настроек → PATH →
    %USERPROFILE%\\.local\\bin\\claude.exe (нативный установщик) →
    %APPDATA%\\npm\\claude.cmd (установка через npm).
    PATH процесса Revit может быть старым (Claude Code поставили после
    запуска Revit), поэтому известные папки проверяются отдельно.
    """
    configured_path = (configured_path or u"").strip().strip('"')
    if configured_path:
        path = os.path.expandvars(configured_path)
        if os.path.isdir(path):
            path = os.path.join(path, u"claude.exe")
        return path if os.path.isfile(path) else None

    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    appdata = os.environ.get("APPDATA") or u""
    candidates = list(_candidates_from_path())
    candidates.append(os.path.join(home, u".local", u"bin", u"claude.exe"))
    if appdata:
        candidates.append(os.path.join(appdata, u"npm", u"claude.cmd"))

    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _quote(arg):
    """Аргумент командной строки Windows (правила CommandLineToArgvW)."""
    arg = unicode(arg)
    if arg and not any(ch in arg for ch in u' \t"'):
        return arg
    result = u'"'
    backslashes = 0
    for ch in arg:
        if ch == u"\\":
            backslashes += 1
        elif ch == u'"':
            result += u"\\" * (backslashes * 2 + 1) + u'"'
            backslashes = 0
        else:
            result += u"\\" * backslashes + ch
            backslashes = 0
    result += u"\\" * (backslashes * 2) + u'"'
    return result


def build_arguments(model):
    args = [
        u"-p",
        u"--output-format", u"json",
        u"--model", model or DEFAULT_MODEL,
        u"--tools", u"",
        u"--max-turns", u"1",
        u"--no-session-persistence",
        u"--strict-mcp-config",
        u"--system-prompt", _SYSTEM_PROMPT,
    ]
    return u" ".join(_quote(a) for a in args)


def _work_dir():
    folder = os.path.join(os.environ.get("TEMP") or os.path.expanduser("~"), u"LowLifeEmailTasks")
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except Exception:
            pass
    return folder


def _classify_failure(text):
    low = (text or u"").lower()
    if any(k in low for k in (u"not logged in", u"/login", u"please run", u"invalid api key",
                              u"authentication", u"unauthorized", u"oauth", u"http 401")):
        return ClaudeError(
            u"Claude Code не залогинен (или вход устарел).\n\n"
            u"Откройте командную строку, запустите `claude` и выполните /login, "
            u"затем повторите.", fatal=True, details=text)
    if any(k in low for k in (u"usage limit", u"rate limit", u"limit reached", u"hit your limit",
                              u"limit will reset", u"http 429", u"quota")):
        return ClaudeError(
            u"Claude упёрся в лимит использования подписки.\n\n"
            u"Подождите, пока лимит сбросится (время сброса — в тексте ниже), "
            u"или уменьшите период в настройках.", fatal=True, details=text)
    if u"unknown option" in low or u"error: option" in low:
        return ClaudeError(
            u"Установленная версия Claude Code не поддерживает нужные флаги.\n\n"
            u"Обновите её: `claude update` в командной строке.", fatal=True, details=text)
    if u"selected model" in low or u"unrecognized_model" in low or u"model not found" in low:
        return ClaudeError(
            u"Модель недоступна или указана с ошибкой.\n\n"
            u"Проверьте поле «Модель» в настройках (Shift+клик): например "
            u"sonnet, opus или haiku.", fatal=True, details=text)
    if u"overloaded" in low or u"http 529" in low:
        return ClaudeError(u"Сервис Claude перегружен — попробуйте чуть позже.",
                           fatal=True, details=text)
    return ClaudeError(u"Claude вернул ошибку.", fatal=False, details=text)


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
    ответа модели (поле result). tick() вызывается примерно 4 раза в секунду,
    пока ждём ответа (обновить окно прогресса); если tick вернул True —
    процесс убивается и бросается Cancelled.
    """
    info = ProcessStartInfo()
    ext = os.path.splitext(claude_path)[1].lower()
    arguments = build_arguments(model)
    if ext in (u".cmd", u".bat"):
        # npm-шим: запускаем через cmd.exe
        info.FileName = os.environ.get("ComSpec") or u"cmd.exe"
        info.Arguments = u'/d /s /c "{} {}"'.format(_quote(claude_path), arguments)
    else:
        info.FileName = claude_path
        info.Arguments = arguments
    info.WorkingDirectory = _work_dir()
    info.UseShellExecute = False
    info.CreateNoWindow = True
    info.RedirectStandardInput = True
    info.RedirectStandardOutput = True
    info.RedirectStandardError = True
    info.StandardOutputEncoding = Encoding.UTF8
    info.StandardErrorEncoding = Encoding.UTF8

    try:
        proc = Process.Start(info)
    except Exception as ex:
        raise ClaudeError(
            u"Не удалось запустить claude:\n{}\n\n{}".format(claude_path, ex),
            fatal=True)

    try:
        # Читаем stdout/stderr асинхронно, иначе при большом выводе процесс
        # встанет на заполненном буфере, пока мы пишем ему stdin.
        out_task = proc.StandardOutput.ReadToEndAsync()
        err_task = proc.StandardError.ReadToEndAsync()

        # stdin — строго UTF-8 без BOM (StandardInput по умолчанию в OEM-кодировке
        # консоли, а StandardInputEncoding есть не во всех версиях .NET).
        data = UTF8Encoding(False).GetBytes(request_text)
        stream = proc.StandardInput.BaseStream
        stream.Write(data, 0, data.Length)
        stream.Flush()
        proc.StandardInput.Close()

        waited_ms = 0
        while not proc.WaitForExit(250):
            waited_ms += 250
            if tick is not None and tick():
                _kill(proc)
                raise Cancelled()
            if waited_ms >= timeout_seconds * 1000:
                _kill(proc)
                raise ClaudeError(
                    u"Claude не ответил за {} мин. — вызов прерван.\n"
                    u"Попробуйте ещё раз или уменьшите период.".format(timeout_seconds // 60),
                    fatal=False)
        proc.WaitForExit()

        stdout = out_task.Result or u""
        stderr = err_task.Result or u""
        exit_code = proc.ExitCode
    finally:
        try:
            proc.Dispose()
        except Exception:
            pass

    result = _parse_cli_json(stdout)
    if result is None:
        if exit_code != 0 or stderr.strip():
            raise _classify_failure(u"код выхода {}\n{}\n{}".format(
                exit_code, stderr.strip(), stdout.strip()).strip())
        raise ClaudeError(u"claude ничего не вернул (код выхода {}).".format(exit_code))

    if result.get("is_error") or exit_code != 0:
        text = u"{}\n{}".format(result.get("result") or u"", stderr).strip()
        if result.get("api_error_status"):
            text = u"HTTP {}: {}".format(result.get("api_error_status"), text)
        if result.get("subtype") == u"error_max_turns":
            text = u"error_max_turns: модель попыталась сделать больше одного хода.\n" + text
        raise _classify_failure(text or u"код выхода {}".format(exit_code))

    answer = result.get("result")
    if not answer:
        raise ClaudeError(u"В ответе claude нет текста (поле result пустое).",
                          details=stdout)
    return unicode(answer)


def _kill(proc):
    try:
        if proc.HasExited:
            return
    except Exception:
        return
    try:
        proc.Kill(True)  # .NET Core 3+ (Revit 2025+): вместе с дочерними процессами
    except Exception:
        try:
            proc.Kill()
        except Exception:
            pass
