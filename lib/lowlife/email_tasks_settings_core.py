# -*- coding: utf-8 -*-
"""
Настройки «Задач из почты» без окон, .NET и pyRevit: значения по
умолчанию, чтение/запись, свой или стандартный промпт. Общие для кнопки
(окно — email_tasks_settings.py, реэкспортирует всё отсюда) и отдельного
приложения (apps/mail). Файл тот же, что у подключения ИИ
(ai_settings_core.SETTINGS_FILE_NAME).
"""

from lowlife import ai_settings_core, settings_core

SETTINGS_FILE_NAME = ai_settings_core.SETTINGS_FILE_NAME

DEFAULTS = {
    "days": 3,
    "unread_only": False,
    "include_subfolders": True,
    "subfolder": u"",
    "test_mode": False,
    "prompt": u"",
}
DEFAULTS.update(ai_settings_core.DEFAULTS)


_STORE = settings_core.JsonStore(SETTINGS_FILE_NAME)


def load():
    # Сначала сохранённое (normalize переносит прежний ключ "model"), потом умолчания
    stored = ai_settings_core.normalize(dict(_STORE.read()))
    values = dict(DEFAULTS)
    values.update(stored)
    try:
        values["days"] = max(1, int(values.get("days") or DEFAULTS["days"]))
    except Exception:
        values["days"] = DEFAULTS["days"]
    values["unread_only"] = bool(values.get("unread_only"))
    values["include_subfolders"] = bool(values.get("include_subfolders"))
    values["test_mode"] = bool(values.get("test_mode"))
    values["prompt"] = values.get("prompt") or u""
    return values


def effective_prompt(values, default_prompt):
    """Промпт для запроса: свой из настроек, иначе стандартный (prompt.txt)."""
    custom = values.get("prompt") or u""
    return custom if custom.strip() else default_prompt


def save(values):
    return _STORE.write(values)


def same_text(a, b):
    norm = lambda t: (t or u"").replace(u"\r\n", u"\n").strip()
    return norm(a) == norm(b)


def stored_prompt(text, default_prompt):
    """Что записать в "prompt": совпадает со стандартным — пусто, чтобы
    правки prompt.txt в новых версиях подхватывались сами."""
    return u"" if same_text(text, default_prompt) else text


def parse_days(text):
    """Период из поля окна: целое ≥ 1 или None."""
    try:
        days = int(u"{}".format(text).strip())
    except Exception:
        return None
    return days if days >= 1 else None


def settings_path():
    """Полный путь к файлу настроек (для сообщений)."""
    return _STORE.path()
