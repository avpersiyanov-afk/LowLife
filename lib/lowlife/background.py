# -*- coding: utf-8 -*-
"""Shared window worker extracted from Notes; network work never accesses Revit."""
import traceback
from lowlife.i18n import tr
from lowlife.cloud_io import ApiError, err_text


def log_error(where,details,callback):
    if callback is not None:
        callback(where,details)


def in_background(window, work, done, transport, on_error=None):
    """work() — в фоновом потоке (только сеть и файлы, без Revit API), затем done(результат, ошибка)
    — в потоке окна. Пока идёт запрос, окно живое и Revit не «зависает».
    При закрытии окна идущие запросы обрываются, а потоки дожидаются (_stop_background)."""
    import System
    from System.Threading import Thread, ThreadStart
    if not getattr(window, '_bg_threads', None):
        window._bg_threads = []
        window._bg_closed = False
        window.Closed += lambda s, e: stop_background(window,transport)
    transport.begin_requests()

    def deliver(result, error):
        if window._bg_closed:
            return
        try:
            done(result, error)
        except Exception:
            log_error(getattr(done, '__name__', 'done'), traceback.format_exc(),on_error)

    def body():
        result, error = None, None
        try:
            result = work()
        except ApiError as ex:
            error = err_text(ex)
        except Exception as ex:
            error = err_text(ex)
            log_error(getattr(work, '__name__', 'work'), traceback.format_exc(),on_error)
        except:  # noqa: E722 — из фонового потока не должно вылететь ничего: это уронило бы Revit
            error = tr(u'ошибка')
        try:
            window.Dispatcher.BeginInvoke(System.Action(lambda: deliver(result, error)))
        except:  # noqa: E722
            pass

    thread = Thread(ThreadStart(body))
    thread.IsBackground = True
    window._bg_threads.append(thread)
    thread.Start()


def stop_background(window,transport):
    window._bg_closed = True
    transport.abort_requests()
    for thread in window._bg_threads:
        try:
            thread.Join(3000)
        except Exception:
            pass
    transport.begin_requests()


