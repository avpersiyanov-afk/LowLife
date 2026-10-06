# -*- coding: utf-8 -*-
"""
Чистая логика (без .NET и Revit) подключения ИИ к кнопке «Задачи из почты»:
список провайдеров, тела HTTP-запросов к Anthropic/OpenAI API, разбор их
ответов, перевод ошибок в понятный пользователю текст, аргументы Codex CLI.

Четыре способа подключения (ключ "provider" в настройках):

    claude_cli     Claude Code (claude -p) под подпиской Claude — email_claude.py
    anthropic_api  Anthropic Messages API по ключу                — email_ai_api.py
    codex_cli      Codex CLI (codex exec) под подпиской ChatGPT   — email_codex.py
    openai_api     OpenAI Chat Completions API по ключу           — email_ai_api.py

Модуль без .NET и без обязательного unicode(), поэтому тестируется и под
Python 3 (tests/test_email_ai_core.py).
"""

import json

CLAUDE_CLI = "claude_cli"
ANTHROPIC_API = "anthropic_api"
CODEX_CLI = "codex_cli"
OPENAI_API = "openai_api"

DEFAULT_PROVIDER = CLAUDE_CLI

# (ключ, подпись в настройках, короткое имя для сообщений)
PROVIDERS = [
    (CLAUDE_CLI, u"Claude — приложение Claude Code (по подписке Claude)", u"Claude"),
    (ANTHROPIC_API, u"Claude — Anthropic API (по ключу API)", u"Claude"),
    (CODEX_CLI, u"ChatGPT — приложение Codex CLI (по подписке ChatGPT)", u"ChatGPT"),
    (OPENAI_API, u"ChatGPT — OpenAI API (по ключу API)", u"ChatGPT"),
]

DEFAULT_MODELS = {
    CLAUDE_CLI: u"sonnet",
    ANTHROPIC_API: u"claude-opus-5-5",
    CODEX_CLI: u"",  # пусто — модель по умолчанию из настроек Codex
    OPENAI_API: u"gpt-5",
}

# Переменные окружения — запасной источник ключа, если поле в настройках пустое
KEY_ENV_VARS = {
    ANTHROPIC_API: "ANTHROPIC_API_KEY",
    OPENAI_API: "OPENAI_API_KEY",
}

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_MAX_TOKENS = 16000

# Короткие имена, как у `claude --model`, — чтобы в поле API можно было
# писать так же, как для Claude Code
ANTHROPIC_ALIASES = {
    u"opus": u"claude-opus-5-5",
    u"sonnet": u"claude-sonnet-5-5",
    u"haiku": u"claude-haiku-4-5",
    u"fable": u"claude-fable-5-1",
}

# Модели, у которых есть серверный «запасной» маршрут при отказе
# классификатора безопасности (fallbacks: "default")
_ANTHROPIC_FALLBACK_MODELS = (u"claude-opus-5-5", u"claude-opus-5", u"claude-sonnet-5-5",
                              u"claude-fable-5-1")
ANTHROPIC_FALLBACK_BETA = "server-side-fallback-2026-07-01"

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

SYSTEM_PROMPT = (
    u"You extract action items from work emails for the user. "
    u"Follow the instructions in the message exactly and reply with JSON only."
)


class AIError(Exception):
    """Ошибка вызова ИИ с понятным пользователю текстом. fatal=True —
    продолжать следующие пачки бессмысленно (не найден, не залогинен, нет
    ключа, лимит)."""

    def __init__(self, message, fatal=False, details=u""):
        Exception.__init__(self, message)
        self.message = message
        self.fatal = fatal
        self.details = details


class Cancelled(Exception):
    pass


def provider_keys():
    return [p[0] for p in PROVIDERS]


def normalize_provider(value):
    return value if value in provider_keys() else DEFAULT_PROVIDER


def provider_label(provider):
    for key, label, _short in PROVIDERS:
        if key == provider:
            return label
    return provider


def provider_short_name(provider):
    for key, _label, short in PROVIDERS:
        if key == provider:
            return short
    return u"ИИ"


def resolve_key(configured, provider, environ):
    """Ключ API: из настроек, иначе из переменной окружения провайдера."""
    key = (configured or u"").strip()
    if key:
        return key
    env_name = KEY_ENV_VARS.get(provider)
    return ((environ or {}).get(env_name) or u"").strip() if env_name else u""


def mask_key(key):
    """sk-ant-…a1b2 — чтобы показать, какой ключ подхватился, не раскрывая его."""
    key = (key or u"").strip()
    if not key:
        return u""
    if len(key) <= 10:
        return u"…" + key[-2:]
    return key[:6] + u"…" + key[-4:]


# --------------------------------------------------------------- Anthropic API

def anthropic_model(model):
    model = (model or u"").strip()
    if not model:
        return DEFAULT_MODELS[ANTHROPIC_API]
    return ANTHROPIC_ALIASES.get(model.lower(), model)


def anthropic_request(api_key, model, request_text, system=SYSTEM_PROMPT):
    """(заголовки, тело) запроса POST /v1/messages. system — системный промпт
    (по умолчанию — для писем; у «Проверки орфографии» свой)."""
    model = anthropic_model(model)
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": ANTHROPIC_MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": request_text}],
    }
    if model in _ANTHROPIC_FALLBACK_MODELS:
        headers["anthropic-beta"] = ANTHROPIC_FALLBACK_BETA
        body["fallbacks"] = "default"
    return headers, body


def parse_anthropic_response(raw):
    """Текст ответа модели из JSON ответа Messages API."""
    data = _loads(raw, u"Anthropic API")
    stop = data.get("stop_reason")
    if stop == "refusal":
        details = data.get("stop_details") or {}
        raise AIError(u"Claude отказался обрабатывать эту часть запроса "
                      u"(фильтр безопасности{}).".format(
                          u": " + details["category"] if details.get("category") else u""),
                      details=details.get("explanation") or u"")
    text = u"".join(block.get("text") or u"" for block in (data.get("content") or [])
                    if block.get("type") == "text").strip()
    if stop == "max_tokens":
        raise AIError(u"Ответ Claude оборвался на лимите длины. Уменьшите объём "
                      u"запроса (период, число писем или текстов).", details=text[:1500])
    if not text:
        raise AIError(u"В ответе Anthropic API нет текста.", details=_short(raw))
    return text


# ------------------------------------------------------------------ OpenAI API

def openai_model(model):
    return (model or u"").strip() or DEFAULT_MODELS[OPENAI_API]


def openai_request(api_key, model, request_text, system=SYSTEM_PROMPT):
    """(заголовки, тело) запроса POST /v1/chat/completions."""
    headers = {
        "authorization": "Bearer " + api_key,
        "content-type": "application/json",
    }
    body = {
        "model": openai_model(model),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": request_text},
        ],
    }
    return headers, body


def parse_openai_response(raw):
    data = _loads(raw, u"OpenAI API")
    choices = data.get("choices") or []
    if not choices:
        raise AIError(u"В ответе OpenAI API нет вариантов ответа.", details=_short(raw))
    choice = choices[0]
    message = choice.get("message") or {}
    if message.get("refusal"):
        raise AIError(u"ChatGPT отказался обрабатывать эту часть запроса.",
                      details=message.get("refusal"))
    text = (message.get("content") or u"").strip()
    if choice.get("finish_reason") == "length":
        raise AIError(u"Ответ ChatGPT оборвался на лимите длины. Уменьшите объём "
                      u"запроса (период, число писем или текстов).", details=text[:1500])
    if not text:
        raise AIError(u"В ответе OpenAI API нет текста.", details=_short(raw))
    return text


# ---------------------------------------------------------- ошибки HTTP API

def classify_http_error(provider, status, raw):
    """AIError по коду HTTP и телу ответа API (status None — нет связи)."""
    name = u"Anthropic API" if provider == ANTHROPIC_API else u"OpenAI API"
    message, kind = _api_error_text(raw)
    low = (message + u" " + kind).lower()
    details = message or _short(raw)

    if status is None:
        return AIError(u"Нет связи с {}. Проверьте интернет и прокси.".format(name),
                       fatal=True, details=details)
    if status == 401:
        return AIError(u"{} отклонил ключ (неверный или отозван).\n\n"
                       u"Проверьте ключ в настройках (Shift+клик по кнопке).".format(name),
                       fatal=True, details=details)
    if status == 403:
        return AIError(u"У ключа нет доступа к {} (или к этой модели).".format(name),
                       fatal=True, details=details)
    if status == 404 or u"model_not_found" in low:
        return AIError(u"Модель недоступна или указана с ошибкой.\n\n"
                       u"Проверьте поле «Модель» в настройках (Shift+клик).",
                       fatal=True, details=details)
    if u"credit balance" in low or u"insufficient_quota" in low or u"billing" in low:
        return AIError(u"На счёте {} закончились деньги или не подключена оплата.\n\n"
                       u"Пополните баланс в консоли разработчика.".format(name),
                       fatal=True, details=details)
    if status == 429:
        return AIError(u"{} ограничил частоту запросов (лимит). Подождите минуту "
                       u"и повторите или уменьшите период.".format(name),
                       fatal=True, details=details)
    if status in (529, 503) or u"overloaded" in low:
        return AIError(u"Сервис перегружен — попробуйте чуть позже.", fatal=True, details=details)
    if status >= 500:
        return AIError(u"{} вернул ошибку сервера (HTTP {}).".format(name, status),
                       details=details)
    return AIError(u"{} отклонил запрос (HTTP {}).".format(name, status),
                   fatal=True, details=details)


def _api_error_text(raw):
    """(message, type) из тела ошибки — у обоих API это {"error": {...}}."""
    try:
        data = json.loads(raw or u"")
    except Exception:
        return _short(raw), u""
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        kind = u"{} {}".format(error.get("type") or u"", error.get("code") or u"").strip()
        return error.get("message") or u"", kind
    return _short(raw), u""


# ------------------------------------------------------------------- Codex CLI

def codex_arguments(model, output_file):
    """Аргументы `codex exec` (сверены с документацией Codex CLI):

        --skip-git-repo-check   запуск вне git-репозитория (временная папка)
        --sandbox read-only     модели ничего нельзя менять на диске
        --ephemeral             не сохранять сессию на диск
        --color never           без ANSI-цветов в выводе
        -o <файл>               последний ответ модели — в файл
        -m <модель>             только если задана; иначе модель из настроек Codex
        -                       запрос читается из stdin
    """
    args = ["exec", "--skip-git-repo-check", "--sandbox", "read-only",
            "--ephemeral", "--color", "never", "-o", output_file]
    model = (model or u"").strip()
    if model:
        args += ["-m", model]
    args.append("-")
    return args


def codex_request_text(request_text, system=SYSTEM_PROMPT):
    """У codex exec нет флага системного промпта — он идёт первой строкой запроса."""
    return system + u"\n\n" + request_text


def classify_codex_failure(text):
    low = (text or u"").lower()
    if any(k in low for k in (u"not logged in", u"codex login", u"please log in",
                              u"unauthorized", u"401", u"authentication")):
        return AIError(u"Codex не залогинен (или вход устарел).\n\n"
                       u"Откройте командную строку, выполните `codex login` и войдите "
                       u"в аккаунт ChatGPT, затем повторите.", fatal=True, details=text)
    if any(k in low for k in (u"usage limit", u"rate limit", u"429", u"quota",
                              u"limit reached", u"try again in")):
        return AIError(u"Codex упёрся в лимит использования подписки.\n\n"
                       u"Подождите, пока лимит сбросится, или уменьшите период.",
                       fatal=True, details=text)
    if u"unexpected argument" in low or u"unrecognized" in low or u"unknown option" in low:
        return AIError(u"Установленная версия Codex не поддерживает нужные флаги.\n\n"
                       u"Обновите её: `npm install -g @openai/codex@latest`.",
                       fatal=True, details=text)
    if u"model" in low and any(k in low for k in (u"not supported", u"does not exist",
                                                  u"not found", u"unknown model")):
        return AIError(u"Модель недоступна или указана с ошибкой.\n\n"
                       u"Проверьте поле «Модель» в настройках (Shift+клик) или "
                       u"оставьте его пустым.", fatal=True, details=text)
    return AIError(u"Codex вернул ошибку.", details=text)


# --------------------------------------------------------------------- общее

def _loads(raw, name):
    try:
        data = json.loads(raw or u"")
    except Exception:
        raise AIError(u"{} ответил не JSON.".format(name), details=_short(raw))
    if not isinstance(data, dict):
        raise AIError(u"{} ответил неожиданным JSON.".format(name), details=_short(raw))
    return data


def _short(raw):
    return (raw or u"").strip()[:1500]
