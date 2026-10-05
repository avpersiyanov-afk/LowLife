# -*- coding: utf-8 -*-
"""
.NET-обвязка подключения ИИ к кнопке «Задачи из почты»: поиск программы
(claude/codex), запуск её с запросом через stdin и POST JSON в HTTP API.

Оба способа ждут ответа, вызывая tick() примерно 4 раза в секунду (окно
прогресса перерисовывается, «Отмена» срабатывает); tick() вернул True —
процесс убивается / запрос прерывается и бросается Cancelled.
"""

import os
import json

import clr
clr.AddReference("System")

from System.Diagnostics import Process, ProcessStartInfo
from System.IO import StreamReader
from System.Net import (
    HttpWebRequest, ServicePointManager, SecurityProtocolType, CredentialCache, WebException
)
from System.Text import UTF8Encoding, Encoding
from System.Threading import Thread, ThreadStart

from lowlife.email_ai_core import AIError, Cancelled

TIMEOUT_SECONDS = 180


def find_executable(configured_path, names, extra_candidates=()):
    """
    Путь к программе или None. Порядок: путь из настроек (файл или папка) →
    PATH → extra_candidates. PATH процесса Revit может быть старым (программу
    поставили после запуска Revit), поэтому известные папки установки
    передаются отдельно.
    """
    configured_path = (configured_path or u"").strip().strip('"')
    if configured_path:
        path = os.path.expandvars(configured_path)
        if os.path.isdir(path):
            for name in names:
                if os.path.isfile(os.path.join(path, name)):
                    return os.path.join(path, name)
            return None
        return path if os.path.isfile(path) else None

    candidates = []
    for folder in (os.environ.get("PATH") or u"").split(os.pathsep):
        folder = folder.strip().strip('"')
        if folder:
            candidates.extend(os.path.join(folder, name) for name in names)
    candidates.extend(extra_candidates)
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def quote(arg):
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


def work_dir():
    """Временная папка запуска: программа не подхватит CLAUDE.md/AGENTS.md
    случайного рабочего каталога Revit."""
    folder = os.path.join(os.environ.get("TEMP") or os.path.expanduser("~"), u"LowLifeEmailTasks")
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except Exception:
            pass
    return folder


def run_process(exe_path, args, stdin_text, name, tick=None, timeout_seconds=TIMEOUT_SECONDS):
    """
    Запускает программу, отдаёт stdin_text в stdin (UTF-8 без BOM — не
    аргументом: у Windows лимит длины командной строки ~32k символов, а
    пачка писем около 30k), возвращает (код выхода, stdout, stderr).
    name — имя программы для сообщений об ошибках.
    """
    info = ProcessStartInfo()
    arguments = u" ".join(quote(a) for a in args)
    if os.path.splitext(exe_path)[1].lower() in (u".cmd", u".bat"):
        # npm-шим: запускаем через cmd.exe
        info.FileName = os.environ.get("ComSpec") or u"cmd.exe"
        info.Arguments = u'/d /s /c "{} {}"'.format(quote(exe_path), arguments)
    else:
        info.FileName = exe_path
        info.Arguments = arguments
    info.WorkingDirectory = work_dir()
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
        raise AIError(u"Не удалось запустить {}:\n{}\n\n{}".format(name, exe_path, ex), fatal=True)

    try:
        # Читаем stdout/stderr асинхронно, иначе при большом выводе процесс
        # встанет на заполненном буфере, пока мы пишем ему stdin.
        out_task = proc.StandardOutput.ReadToEndAsync()
        err_task = proc.StandardError.ReadToEndAsync()

        # stdin — строго UTF-8 без BOM (StandardInput по умолчанию в OEM-кодировке
        # консоли, а StandardInputEncoding есть не во всех версиях .NET).
        data = UTF8Encoding(False).GetBytes(stdin_text)
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
                raise AIError(
                    u"{} не ответил за {} мин. — вызов прерван.\n"
                    u"Попробуйте ещё раз или уменьшите период.".format(name, timeout_seconds // 60))
        proc.WaitForExit()

        return proc.ExitCode, out_task.Result or u"", err_task.Result or u""
    finally:
        try:
            proc.Dispose()
        except Exception:
            pass


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


def post_json(url, headers, body, tick=None, timeout_seconds=TIMEOUT_SECONDS):
    """
    POST JSON. Возвращает (HTTP-код, текст ответа); код None — нет связи
    (текст — описание ошибки). Запрос идёт в фоновом потоке, а этот поток
    ждёт его, вызывая tick() — так окно прогресса не «замерзает» на минуты.
    """
    try:
        ServicePointManager.SecurityProtocol = ServicePointManager.SecurityProtocol | SecurityProtocolType.Tls12
    except Exception:
        pass

    # ensure_ascii — кириллица уходит escape-последовательностями, без сюрпризов с кодировкой
    data = UTF8Encoding(False).GetBytes(json.dumps(body))
    req = HttpWebRequest.Create(url)
    req.Method = "POST"
    for key, value in headers.items():
        if key.lower() == "content-type":
            req.ContentType = value
        else:
            req.Headers.Add(key, value)
    req.Timeout = timeout_seconds * 1000
    req.ReadWriteTimeout = timeout_seconds * 1000
    if req.Proxy is not None:
        req.Proxy.Credentials = CredentialCache.DefaultNetworkCredentials
    req.ContentLength = data.Length

    result = {}

    def worker():
        try:
            stream = req.GetRequestStream()
            try:
                stream.Write(data, 0, data.Length)
            finally:
                stream.Close()
            resp = req.GetResponse()
            try:
                result["status"] = int(resp.StatusCode)
                result["text"] = _read(resp)
            finally:
                resp.Close()
        except WebException as ex:
            if ex.Response is not None:
                try:
                    result["status"] = int(ex.Response.StatusCode)
                    result["text"] = _read(ex.Response)
                finally:
                    ex.Response.Close()
            else:
                result["status"] = None
                result["text"] = unicode(ex.Message)
        except Exception as ex:
            result["status"] = None
            result["text"] = unicode(ex)

    thread = Thread(ThreadStart(worker))
    thread.IsBackground = True
    thread.Start()

    waited_ms = 0
    while not thread.Join(250):
        waited_ms += 250
        if tick is not None and tick():
            _abort(req)
            raise Cancelled()
        if waited_ms >= timeout_seconds * 1000 + 5000:
            _abort(req)
            raise AIError(u"Сервис не ответил за {} мин. — запрос прерван.\n"
                          u"Попробуйте ещё раз или уменьшите период.".format(timeout_seconds // 60))
    return result.get("status"), result.get("text") or u""


def _read(resp):
    return StreamReader(resp.GetResponseStream(), Encoding.UTF8).ReadToEnd()


def _abort(req):
    try:
        req.Abort()
    except Exception:
        pass
