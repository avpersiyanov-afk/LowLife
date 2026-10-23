# -*- coding: utf-8 -*-
"""
Хранение общего подключения ИИ («Задачи из почты», «Проверка орфографии»)
без окон, .NET и pyRevit — его же читает отдельное приложение «Задачи из
почты» (apps/mail). Блок окна настроек для Revit — ai_settings.py (он
реэкспортирует всё отсюда).
"""

from lowlife import email_ai_core as ai
from lowlife import settings_core

SETTINGS_FILE_NAME = "LowLifeEmailTasks_settings.json"

REPO_URL = u"https://github.com/avpersiyanov-afk/LowLife"
GUIDE_URL = REPO_URL + u"/blob/main/docs/email-tasks.md"
# Разделы инструкции docs/email-tasks.md (якоря GitHub по заголовкам «### …»)
GUIDE_URLS = {
    ai.CLAUDE_CLI: GUIDE_URL + u"#claude-code-подписка-claude",
    ai.ANTHROPIC_API: GUIDE_URL + u"#anthropic-api-ключ",
    ai.CODEX_CLI: GUIDE_URL + u"#codex-cli-подписка-chatgpt",
    ai.OPENAI_API: GUIDE_URL + u"#openai-api-ключ",
}

DEFAULTS = {
    "provider": ai.DEFAULT_PROVIDER,
    "claude_path": u"",
    "codex_path": u"",
    "anthropic_api_key": u"",
    "openai_api_key": u"",
}
for _provider in ai.provider_keys():
    DEFAULTS[_provider + "_model"] = ai.DEFAULT_MODELS[_provider]

KEYS = sorted(DEFAULTS)

_STORE = settings_core.JsonStore(SETTINGS_FILE_NAME)


def normalize(values):
    """Дополняет values ключами подключения по умолчанию и чистит их (на месте)."""
    # До выбора способа подключения модель Claude Code хранилась под ключом "model"
    if values.get("model") and not values.get("claude_cli_model"):
        values["claude_cli_model"] = values["model"]
    values.pop("model", None)
    for key, default in DEFAULTS.items():
        if values.get(key) is None:
            values[key] = default
    values["provider"] = ai.normalize_provider(values.get("provider"))
    for provider in ai.provider_keys():
        key = provider + "_model"
        values[key] = (values.get(key) or u"").strip() or DEFAULTS[key]
    return values


def load():
    """Только ключи подключения ИИ из общего файла."""
    stored = normalize(_STORE.read())
    return dict((key, stored[key]) for key in KEYS)


def save(values):
    """Записывает ключи подключения, не трогая остальные настройки файла."""
    return _STORE.update(dict((key, values[key]) for key in KEYS if key in values))


def validate(values):
    """Текст ошибки подключения или None. Проверяет только выбранный способ:
    остальные могут быть не настроены."""
    import os
    from lowlife import email_claude, email_codex
    provider = values.get("provider")
    claude_path, codex_path = values.get("claude_path") or u"", values.get("codex_path") or u""
    if provider == ai.CLAUDE_CLI and claude_path and email_claude.find_claude(claude_path) is None:
        return (u"По указанному пути claude не найден:\n{}\n\n"
                u"Укажите полный путь к claude.exe или оставьте поле "
                u"пустым для автопоиска.".format(claude_path))
    if provider == ai.CODEX_CLI and codex_path and email_codex.find_codex(codex_path) is None:
        return (u"По указанному пути codex не найден:\n{}\n\n"
                u"Укажите полный путь к codex или оставьте поле "
                u"пустым для автопоиска.".format(codex_path))
    key_field = provider + "_key"
    if key_field in values and not ai.resolve_key(values[key_field], provider, os.environ):
        return (u"Вставьте ключ API — или выберите другой способ подключения.\n\n"
                u"Где взять ключ — по ссылке «Как получить ключ» в окне настроек.")
    return None


def key_hint(provider):
    """Подсказка под полем ключа API: где хранится и что сейчас в переменной окружения."""
    import os
    env_name = ai.KEY_ENV_VARS[provider]
    env_key = ai.resolve_key(u"", provider, os.environ)
    found = u"сейчас там {}".format(ai.mask_key(env_key)) if env_key else u"сейчас её нет"
    return (u"Хранится в файле настроек на этом компьютере. Пусто — взять из "
            u"переменной окружения {} ({}).".format(env_name, found))
