# -*- coding: utf-8 -*-
"""Shared HTTP transport and process lock extracted from the existing Notes helpers.
No settings discovery, Revit imports or dependency on a particular tool.
"""
import json
import threading
import time
from lowlife.i18n import tr

class ApiError(Exception):
    pass


def err_text(ex):
    # У собственных исключений текст — в args; у .NET-исключений — в Message
    if isinstance(ex, ApiError) and ex.args:
        return u'{}'.format(ex.args[0])
    msg = getattr(ex, 'Message', None)
    if msg:
        return msg
    try:
        return u'{}'.format(ex)
    except Exception:
        return tr(u'ошибка')

def dumps_ascii(data, indent=None):
    """json.dumps с ASCII-результатом, безопасный для IronPython.

    Стандартный ensure_ascii=True в IronPython (pyRevit на части машин, напр. Revit 2022) падает на
    любой кириллице: UnicodeEncodeError 'ascii' codec can't encode character. Поэтому строим текст
    с ensure_ascii=False и сами заменяем не-ASCII символы на \\uXXXX — результат тот же, что у CPython.
    """
    text = json.dumps(data, ensure_ascii=False, indent=indent)
    out = []
    for ch in text:
        code = ord(ch)
        if code < 128:
            out.append(ch)
        elif code > 0xFFFF:  # CPython 3: символ вне BMP — суррогатная пара
            code -= 0x10000
            out.append(u'\\u{:04x}\\u{:04x}'.format(0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)))
        else:
            out.append(u'\\u{:04x}'.format(code))
    return u''.join(out)

class Transport(object):
    def __init__(self):
        self._active=[]
        self._lock=threading.Lock()
        self._cancelled=[False]
        self.last_server_ms=[None]

    def begin_requests(self):
        self._cancelled[0] = False


    def abort_requests(self):
        """Оборвать все идущие запросы (окно закрыто); следующие до begin_requests() не начнутся."""
        self._cancelled[0] = True
        with self._lock:
            reqs = list(self._active)
        for req in reqs:
            try:
                req.Abort()
            except Exception:
                pass


    def _post(self,url, body, timeout_ms, track=True):
        from System.Net import HttpWebRequest, ServicePointManager, SecurityProtocolType, CredentialCache
        from System.IO import StreamReader
        from System.Text import Encoding
        try:
            ServicePointManager.SecurityProtocol = ServicePointManager.SecurityProtocol | SecurityProtocolType.Tls12
            # Без этого .NET шлёт «Expect: 100-continue» и ждёт лишний обмен с сервером (часть прокси его рвёт)
            ServicePointManager.Expect100Continue = False
            # По умолчанию 2 соединения на хост: фоновые отправки и загрузка сводки стояли бы в очереди друг за другом
            if ServicePointManager.DefaultConnectionLimit < 8:
                ServicePointManager.DefaultConnectionLimit = 8
        except Exception:
            pass
        data = Encoding.UTF8.GetBytes(body)
        req = HttpWebRequest.Create(url)
        req.Method = 'POST'
        req.ContentType = 'text/plain; charset=utf-8'
        req.Timeout = timeout_ms
        req.ReadWriteTimeout = timeout_ms
        req.AllowAutoRedirect = True  # Apps Script отвечает редиректом на googleusercontent.com
        if req.Proxy is not None:
            req.Proxy.Credentials = CredentialCache.DefaultNetworkCredentials
        req.ContentLength = data.Length
        if track:
            with self._lock:
                self._active.append(req)
        try:
            stream = req.GetRequestStream()
            try:
                stream.Write(data, 0, data.Length)
            finally:
                stream.Close()
            resp = req.GetResponse()
            try:
                return StreamReader(resp.GetResponseStream(), Encoding.UTF8).ReadToEnd()
            finally:
                resp.Close()
        finally:
            with self._lock:
                if req in self._active:
                    self._active.remove(req)

    def _is_transient(self,ex, timeout=False):
        """Сбой, который у Google случается сам по себе и проходит при повторе (обрыв, 5xx, 429).
        Таймаут повторяем только с timeout=True — в фоне, где лишнее ожидание не блокирует Revit:
        у Google отдельный запрос иногда «зависает», а новый проходит за несколько секунд."""
        from System.Net import WebException, WebExceptionStatus
        from System.IO import IOException
        _TRANSIENT = (WebExceptionStatus.ConnectionClosed, WebExceptionStatus.KeepAliveFailure,
                      WebExceptionStatus.ReceiveFailure, WebExceptionStatus.SendFailure,
                      WebExceptionStatus.ConnectFailure, WebExceptionStatus.NameResolutionFailure,
                      WebExceptionStatus.PipelineFailure, WebExceptionStatus.SecureChannelFailure)

        if self._cancelled[0]:
            return False
        net = getattr(ex, 'clsException', None) or ex
        if isinstance(net, WebException):
            if net.Status == WebExceptionStatus.Timeout:
                return timeout
            if net.Status == WebExceptionStatus.ProtocolError:
                try:
                    code = int(net.Response.StatusCode)
                except Exception:
                    return False
                return code >= 500 or code == 429
            return net.Status in _TRANSIENT
        return isinstance(net, IOException)

    def call(self,action, payload=None, timeout_ms=15000, url=None, token=None, retries=1, track=True,
             retry_timeout=False,error_transform=None):
        """Запрос к веб-приложению. Временный сбой связи повторяется (retries раз): все действия
        сервера безопасно повторять — «add» отсеивает повторную отправку по id.
        track=False — запрос не обрывается закрытием окна (фоновая отправка после закрытия, send_queue_detached)."""
        if not (url and token):
            raise ApiError(tr(u'Не настроено подключение к таблице (кнопка «Настройка»).'))
        body = dict(payload or {})
        body['action'] = action
        body['token'] = token
        text = dumps_ascii(body)
        attempt = 0
        while True:
            if track and self._cancelled[0]:
                raise ApiError(tr(u'Запрос отменён: окно закрыто.'))
            try:
                raw = self._post(url, text, timeout_ms, track)
            except Exception as ex:
                if attempt < retries and self._is_transient(ex, retry_timeout):
                    attempt += 1
                    time.sleep(1)
                    continue
                raise ApiError(tr(u'Нет связи с Google Таблицей: ') + err_text(ex))
            try:
                resp = json.loads(raw)
            except Exception:
                # Google иногда отдаёт страницу ошибки вместо ответа скрипта — один раз повторяем
                if attempt < retries and not self._cancelled[0]:
                    attempt += 1
                    time.sleep(1)
                    continue
                raise ApiError(tr(u'Таблица ответила не данными, а страницей. Проверьте адрес (должен заканчиваться на /exec) '
                               u'и что веб-приложение развернуто с доступом «Все».'))
            break
        try:
            self.last_server_ms[0] = float(resp.get('ms'))
        except Exception:
            self.last_server_ms[0] = None  # Code.gs старой версии не сообщает своё время
        if not resp.get('ok'):
            raise ApiError((error_transform or (lambda value:value))(resp.get('error') or tr(u'Неизвестная ошибка')))
        return resp


class AppDomainLock(object):
    """Блокировка файла очереди на весь процесс Revit: её трогают окна разных кнопок (каждая — в своём
    движке pyRevit со своей копией модуля) и фоновая отправка. Объект блокировки — в AppDomain."""
    def __init__(self, key='lowlife_queue_lock'):
        self.key = key

    def __enter__(self):
        import System
        from System.Threading import Monitor
        domain = System.AppDomain.CurrentDomain
        obj = domain.GetData(self.key)
        if obj is None:
            obj = System.Object()
            domain.SetData(self.key, obj)
            obj = domain.GetData(self.key)
        self.obj = obj
        Monitor.Enter(obj)
        return self

    def __exit__(self, *args):
        from System.Threading import Monitor
        Monitor.Exit(self.obj)
        return False
