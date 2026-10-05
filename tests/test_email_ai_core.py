# -*- coding: utf-8 -*-
"""Тесты для lowlife.email_ai_core — чистая логика подключения ИИ к кнопке
«Задачи из почты»: провайдеры, ключи, тела запросов Anthropic/OpenAI API,
разбор ответов, перевод ошибок HTTP и Codex в понятный текст."""

import json

import pytest

from lowlife import email_ai_core as ai


def test_providers_and_defaults():
    assert ai.provider_keys() == [ai.CLAUDE_CLI, ai.ANTHROPIC_API, ai.CODEX_CLI, ai.OPENAI_API]
    assert ai.normalize_provider("openai_api") == ai.OPENAI_API
    assert ai.normalize_provider("нет такого") == ai.DEFAULT_PROVIDER
    assert ai.normalize_provider(None) == ai.CLAUDE_CLI
    for key in ai.provider_keys():
        assert key in ai.DEFAULT_MODELS
    assert ai.provider_short_name(ai.CODEX_CLI) == u"ChatGPT"


def test_resolve_key_prefers_settings_then_env():
    env = {"ANTHROPIC_API_KEY": " sk-ant-env ", "OPENAI_API_KEY": "sk-openai-env"}
    assert ai.resolve_key(u" sk-ant-own ", ai.ANTHROPIC_API, env) == u"sk-ant-own"
    assert ai.resolve_key(u"", ai.ANTHROPIC_API, env) == u"sk-ant-env"
    assert ai.resolve_key(None, ai.OPENAI_API, env) == u"sk-openai-env"
    assert ai.resolve_key(u"", ai.OPENAI_API, {}) == u""
    assert ai.resolve_key(u"", ai.CLAUDE_CLI, env) == u""


def test_mask_key_hides_middle():
    assert ai.mask_key(u"sk-ant-api03-abcdefghijklmnop-wxyz") == u"sk-ant…wxyz"
    assert ai.mask_key(u"") == u""
    assert u"short" not in ai.mask_key(u"shortkey")


def test_anthropic_request_shape():
    headers, body = ai.anthropic_request(u"sk-ant-x", u"", u"письма")
    assert headers["x-api-key"] == u"sk-ant-x"
    assert headers["anthropic-version"] == "2023-06-01"
    assert body["model"] == ai.DEFAULT_MODELS[ai.ANTHROPIC_API]
    assert body["max_tokens"] == ai.ANTHROPIC_MAX_TOKENS
    assert body["system"] == ai.SYSTEM_PROMPT
    assert body["messages"] == [{"role": "user", "content": u"письма"}]
    # Модель по умолчанию поддерживает серверный запасной маршрут
    assert body["fallbacks"] == "default"
    assert headers["anthropic-beta"] == ai.ANTHROPIC_FALLBACK_BETA
    json.dumps(body)  # сериализуется


def test_anthropic_aliases_and_fallback_only_where_supported():
    _headers, body = ai.anthropic_request(u"k", u"Sonnet", u"x")
    assert body["model"] == u"claude-sonnet-5-5"
    headers, body = ai.anthropic_request(u"k", u"haiku", u"x")
    assert body["model"] == u"claude-haiku-4-5"
    assert "fallbacks" not in body and "anthropic-beta" not in headers
    _headers, body = ai.anthropic_request(u"k", u"claude-opus-4-8", u"x")
    assert body["model"] == u"claude-opus-4-8" and "fallbacks" not in body


def test_parse_anthropic_response_joins_text_blocks():
    raw = json.dumps({
        "content": [
            {"type": "thinking", "thinking": ""},
            {"type": "text", "text": u"{\"tasks\": "},
            {"type": "text", "text": u"[]}"},
        ],
        "stop_reason": "end_turn",
    })
    assert ai.parse_anthropic_response(raw) == u"{\"tasks\": []}"


def test_parse_anthropic_response_refusal_and_truncation():
    refusal = json.dumps({"content": [], "stop_reason": "refusal",
                          "stop_details": {"type": "refusal", "category": "cyber",
                                           "explanation": "nope"}})
    with pytest.raises(ai.AIError) as err:
        ai.parse_anthropic_response(refusal)
    assert u"cyber" in err.value.message and not err.value.fatal

    cut = json.dumps({"content": [{"type": "text", "text": "{\"tasks\": ["}],
                      "stop_reason": "max_tokens"})
    with pytest.raises(ai.AIError) as err:
        ai.parse_anthropic_response(cut)
    assert u"лимит" in err.value.message

    with pytest.raises(ai.AIError):
        ai.parse_anthropic_response(u"<html>")


def test_openai_request_and_response():
    headers, body = ai.openai_request(u"sk-x", u"", u"письма")
    assert headers["authorization"] == u"Bearer sk-x"
    assert body["model"] == ai.DEFAULT_MODELS[ai.OPENAI_API]
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["messages"][1]["content"] == u"письма"

    raw = json.dumps({"choices": [{"message": {"content": u" {\"tasks\": []} "},
                                   "finish_reason": "stop"}]})
    assert ai.parse_openai_response(raw) == u"{\"tasks\": []}"

    refusal = json.dumps({"choices": [{"message": {"content": None, "refusal": "no"},
                                       "finish_reason": "stop"}]})
    with pytest.raises(ai.AIError):
        ai.parse_openai_response(refusal)

    cut = json.dumps({"choices": [{"message": {"content": "{"}, "finish_reason": "length"}]})
    with pytest.raises(ai.AIError) as err:
        ai.parse_openai_response(cut)
    assert u"лимит" in err.value.message


@pytest.mark.parametrize("provider,status,body,fatal,needle", [
    (ai.ANTHROPIC_API, 401, {"type": "error", "error": {"type": "authentication_error",
                                                         "message": "invalid x-api-key"}},
     True, u"ключ"),
    (ai.ANTHROPIC_API, 404, {"type": "error", "error": {"type": "not_found_error",
                                                         "message": "model: foo"}},
     True, u"Модель"),
    (ai.ANTHROPIC_API, 400, {"type": "error", "error": {
        "type": "invalid_request_error",
        "message": "Your credit balance is too low to access the Anthropic API."}},
     True, u"деньги"),
    (ai.ANTHROPIC_API, 529, {"type": "error", "error": {"type": "overloaded_error",
                                                         "message": "Overloaded"}},
     True, u"перегружен"),
    (ai.OPENAI_API, 429, {"error": {"message": "You exceeded your current quota",
                                    "type": "insufficient_quota", "code": "insufficient_quota"}},
     True, u"деньги"),
    (ai.OPENAI_API, 429, {"error": {"message": "Rate limit reached", "type": "requests",
                                    "code": "rate_limit_exceeded"}},
     True, u"лимит"),
    (ai.OPENAI_API, 500, {"error": {"message": "boom", "type": "server_error"}},
     False, u"HTTP 500"),
])
def test_classify_http_error(provider, status, body, fatal, needle):
    err = ai.classify_http_error(provider, status, json.dumps(body))
    assert err.fatal is fatal
    assert needle in err.message


def test_classify_http_error_no_connection():
    err = ai.classify_http_error(ai.OPENAI_API, None, u"The remote name could not be resolved")
    assert err.fatal and u"Нет связи" in err.message
    assert u"resolved" in err.details


def test_codex_arguments():
    args = ai.codex_arguments(u"", u"C:\\tmp\\out.txt")
    assert args[0] == "exec" and args[-1] == "-"
    assert "--skip-git-repo-check" in args
    assert args[args.index("--sandbox") + 1] == "read-only"
    assert args[args.index("-o") + 1] == u"C:\\tmp\\out.txt"
    assert "-m" not in args
    args = ai.codex_arguments(u"gpt-5", u"out.txt")
    assert args[args.index("-m") + 1] == u"gpt-5"
    assert args[-1] == "-"
    assert ai.codex_request_text(u"письма").startswith(ai.SYSTEM_PROMPT)


@pytest.mark.parametrize("text,fatal,needle", [
    (u"Error: Not logged in. Run `codex login`", True, u"codex login"),
    (u"You've hit your usage limit. Try again in 3 hours", True, u"лимит"),
    (u"error: unexpected argument '--ephemeral' found", True, u"@openai/codex@latest"),
    (u"The model 'gpt-9' does not exist", True, u"Модель"),
    (u"something odd happened", False, u"Codex"),
])
def test_classify_codex_failure(text, fatal, needle):
    err = ai.classify_codex_failure(text)
    assert err.fatal is fatal
    assert needle in err.message
