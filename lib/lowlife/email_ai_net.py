# -*- coding: utf-8 -*-
"""
Подключение ИИ к «Задачам из почты»: поиск программы (claude/codex), запуск
её с запросом через stdin и POST JSON в HTTP API.

Запуск и HTTP — в двух вариантах с одинаковыми функциями: email_ai_clr
(.NET — в Revit, на обоих движках pyRevit, где есть clr) и email_ai_std
(stdlib — отдельное приложение apps/mail, обычный Python без .NET). Здесь
выбирается нужный, так что email_claude/email_codex/email_ai одни на оба.

Оба варианта ждут ответа, вызывая tick() примерно 4 раза в секунду (окно
прогресса перерисовывается, «Отмена» срабатывает); tick() вернул True —
процесс убивается / запрос прерывается и бросается Cancelled.
"""

from lowlife.email_ai_proc import TIMEOUT_SECONDS, find_executable, quote, work_dir  # noqa: F401

try:
    import clr  # noqa: F401
except ImportError:
    clr = None

if clr is None:
    from lowlife.email_ai_std import run_process, post_json  # noqa: F401
else:
    from lowlife.email_ai_clr import run_process, post_json  # noqa: F401
