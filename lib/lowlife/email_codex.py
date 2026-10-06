# -*- coding: utf-8 -*-
"""
Вызов Codex CLI (codex exec) для кнопки «Задачи из почты» (способ
подключения "codex_cli"). Работает под подпиской ChatGPT, под которой
залогинен Codex (`codex login`), — API-ключ не нужен.

Запрос уходит через stdin (`-` вместо текста запроса), последний ответ
модели Codex пишет в файл (-o) — его и читаем; флаги — в
email_ai_core.codex_arguments. Модель работает в песочнице только для
чтения во временной папке, где ничего нет.
"""

import os
import io
import uuid

from lowlife import email_ai_net
from lowlife.email_ai_core import (
    AIError, SYSTEM_PROMPT, codex_arguments, codex_request_text, classify_codex_failure
)

# Codex думает дольше одного хода Claude — даём больше времени
TIMEOUT_SECONDS = 300


def find_codex(configured_path=u""):
    """
    Путь к codex или None. Порядок: путь из настроек → PATH →
    %APPDATA%\\npm\\codex.cmd (установка через npm) →
    %USERPROFILE%\\.local\\bin\\codex.exe.
    """
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    appdata = os.environ.get("APPDATA") or u""
    extra = []
    if appdata:
        extra.append(os.path.join(appdata, u"npm", u"codex.cmd"))
    extra.append(os.path.join(home, u".local", u"bin", u"codex.exe"))
    return email_ai_net.find_executable(
        configured_path, [u"codex.exe", u"codex.cmd", u"codex"], extra)


def run_codex(codex_path, model, request_text, tick=None, timeout_seconds=TIMEOUT_SECONDS,
              system=SYSTEM_PROMPT):
    """Запускает codex exec, возвращает текст последнего ответа модели."""
    out_file = os.path.join(email_ai_net.work_dir(), u"codex_answer_{}.txt".format(uuid.uuid4().hex))
    try:
        exit_code, stdout, stderr = email_ai_net.run_process(
            codex_path, codex_arguments(model, out_file), codex_request_text(request_text, system or SYSTEM_PROMPT),
            u"codex", tick=tick, timeout_seconds=timeout_seconds)

        answer = u""
        if os.path.isfile(out_file):
            with io.open(out_file, "r", encoding="utf-8") as f:
                answer = f.read().strip()
    finally:
        try:
            if os.path.isfile(out_file):
                os.remove(out_file)
        except Exception:
            pass

    if exit_code != 0:
        raise classify_codex_failure(u"код выхода {}\n{}\n{}".format(
            exit_code, stderr.strip()[-3000:], stdout.strip()[-1500:]).strip())
    if not answer:
        # Старые версии без -o: ответ — в stdout
        answer = stdout.strip()
    if not answer:
        raise AIError(u"codex ничего не вернул.", details=stderr.strip()[-1500:])
    return unicode(answer)
