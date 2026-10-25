# -*- coding: utf-8 -*-
"""
.NET-обвязка подключения ИИ к кнопке «Задачи из почты» (в Revit): запуск
программы (claude/codex) с запросом через stdin и POST JSON в HTTP API.
Выбирает её email_ai_net; в отдельном приложении вместо неё — email_ai_std.

Оба способа ждут ответа, вызывая tick() примерно 4 раза в секунду (окно
прогресса перерисовывается, «Отмена» срабатывает); tick() вернул True —
процесс убивается / запрос прерывается и бросается Cancelled.
"""

try:
    unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3
    unicode = str


import json
from lowlife.i18n import tr

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
from lowlife.email_ai_proc import TIMEOUT_SECONDS, command_line, work_dir


def run_process(exe_path, args, stdin_text, name, tick=None, timeout_seconds=TIMEOUT_SECONDS):
    """
    Запускает программу, отдаёт stdin_text в stdin (UTF-8 без BOM — не
    аргументом: у Windows лимит длины командной строки ~32k символов, а
    пачка писем около 30k), возвращает (код выхода, stdout, stderr).
    name — имя программы для сообщений об ошибках.
    """
    info = ProcessStartInfo()
    info.FileName, info.Arguments = command_line(exe_path, args)
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
        raise AIError(tr(u"Не удалось запустить {}:\n{}\n\n{}").format(name, exe_path, ex), fatal=True)

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
                    tr(u"{} не ответил за {} мин. — вызов прерван.\n"
                    u"Попробуйте ещё раз или уменьшите период.").format(name, timeout_seconds // 60))
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
            raise AIError(tr(u"Сервис не ответил за {} мин. — запрос прерван.\n"
                          u"Попробуйте ещё раз или уменьшите период.").format(timeout_seconds // 60))
    return result.get("status"), result.get("text") or u""


def _read(resp):
    return StreamReader(resp.GetResponseStream(), Encoding.UTF8).ReadToEnd()


def _abort(req):
    try:
        req.Abort()
    except Exception:
        pass
