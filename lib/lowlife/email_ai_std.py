# -*- coding: utf-8 -*-
"""
Обвязка подключения ИИ на stdlib (subprocess, urllib) — для отдельного
приложения «Задачи из почты» (apps/mail), где нет .NET. Те же функции и
то же поведение, что у email_ai_clr (выбирает email_ai_net):

    run_process(exe, args, stdin_text, name, tick)  -> (код, stdout, stderr)
    post_json(url, headers, body, tick)             -> (HTTP-код | None, текст)

Ждут ответа, вызывая tick() примерно 4 раза в секунду; tick() вернул
True — процесс убивается (вместе с дочерними) / запрос бросается, и
поднимается Cancelled.
"""

import json
from lowlife.i18n import tr
import os
import subprocess
import threading

try:
    from urllib import request as _urlrequest
    from urllib.error import HTTPError, URLError
except ImportError:  # CPython 2 — тесты (в Revit есть clr, и email_ai_net берёт email_ai_clr)
    import urllib2 as _urlrequest
    from urllib2 import HTTPError, URLError

from lowlife.email_ai_core import AIError, Cancelled
from lowlife.email_ai_proc import TIMEOUT_SECONDS, command_line, work_dir

_TICK_SECONDS = 0.25
# Окно консоли у дочернего процесса не показываем (флаг есть только на Windows)
_CREATE_NO_WINDOW = 0x08000000


def _wait(thread, tick, timeout_seconds, on_cancel, on_timeout):
    """Ждёт поток, вызывая tick(); Cancelled / on_timeout() — при отмене и тайм-ауте."""
    waited = 0.0
    while True:
        thread.join(_TICK_SECONDS)
        if not thread.is_alive():
            return
        waited += _TICK_SECONDS
        if tick is not None and tick():
            on_cancel()
            raise Cancelled()
        if waited >= timeout_seconds:
            on_cancel()
            on_timeout()


def run_process(exe_path, args, stdin_text, name, tick=None, timeout_seconds=TIMEOUT_SECONDS):
    """
    Запускает программу, отдаёт stdin_text в stdin (UTF-8 — не аргументом:
    у Windows лимит длины командной строки ~32k символов, а пачка писем
    около 30k), возвращает (код выхода, stdout, stderr).
    """
    if os.name == "nt":
        program, arguments = command_line(exe_path, args)
        cmd = u"{} {}".format(_quote_program(program), arguments)
        flags = _CREATE_NO_WINDOW
    else:
        cmd = [exe_path] + list(args)
        flags = 0
    try:
        proc = subprocess.Popen(cmd, cwd=work_dir(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, creationflags=flags)
    except Exception as ex:
        raise AIError(tr(u"Не удалось запустить {}:\n{}\n\n{}").format(name, exe_path, ex), fatal=True)

    result = {}

    def worker():
        # communicate читает stdout/stderr параллельно с записью stdin — без
        # взаимной блокировки на заполненном буфере
        try:
            result["out"], result["err"] = proc.communicate(stdin_text.encode("utf-8"))
        except Exception as ex:
            result["error"] = ex

    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()

    def timeout():
        raise AIError(tr(u"{} не ответил за {} мин. — вызов прерван.\n"
                      u"Попробуйте ещё раз или уменьшите период.").format(name, timeout_seconds // 60))

    _wait(thread, tick, timeout_seconds, lambda: _kill(proc), timeout)
    if "error" in result:
        raise AIError(tr(u"Ошибка обмена данными с {}:\n{}").format(name, result["error"]))
    return (proc.returncode, _decode(result.get("out")), _decode(result.get("err")))


def _quote_program(program):
    return u'"{}"'.format(program) if u" " in program and not program.startswith(u'"') else program


def _decode(data):
    return (data or b"").decode("utf-8", "replace")


def _kill(proc):
    if proc.poll() is not None:
        return
    if os.name == "nt":
        # /T — вместе с дочерними (у npm-шима claude.cmd это cmd.exe → node)
        try:
            subprocess.call(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=_CREATE_NO_WINDOW)
        except Exception:
            pass
    try:
        proc.kill()
    except Exception:
        pass


def post_json(url, headers, body, tick=None, timeout_seconds=TIMEOUT_SECONDS):
    """
    POST JSON. Возвращает (HTTP-код, текст ответа); код None — нет связи
    (текст — описание ошибки). Прокси — системный (urllib берёт настройки
    Windows), сертификаты — из хранилища Windows.
    """
    # ensure_ascii — кириллица уходит escape-последовательностями, без сюрпризов с кодировкой
    data = json.dumps(body).encode("utf-8")
    req = _urlrequest.Request(url, data=data)  # с data — POST
    for key, value in headers.items():
        req.add_header(key, value)

    result = {}

    def worker():
        try:
            resp = _urlrequest.urlopen(req, timeout=timeout_seconds)
            try:
                result["status"] = resp.getcode()
                result["text"] = _decode(resp.read())
            finally:
                resp.close()
        except HTTPError as ex:
            result["status"] = ex.code
            try:
                result["text"] = _decode(ex.read())
            except Exception:
                result["text"] = u"{}".format(ex)
        except URLError as ex:
            result["status"] = None
            result["text"] = u"{}".format(ex.reason)
        except Exception as ex:
            result["status"] = None
            result["text"] = u"{}".format(ex)

    thread = threading.Thread(target=worker)
    thread.daemon = True  # при отмене поток просто бросаем — urllib не умеет прервать запрос
    thread.start()

    def timeout():
        raise AIError(tr(u"Сервис не ответил за {} мин. — запрос прерван.\n"
                      u"Попробуйте ещё раз или уменьшите период.").format(timeout_seconds // 60))

    _wait(thread, tick, timeout_seconds + 5, lambda: None, timeout)
    return result.get("status"), result.get("text") or u""
