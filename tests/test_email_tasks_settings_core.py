# -*- coding: utf-8 -*-
"""Тесты для lowlife.email_tasks_settings_core / ai_settings_core — настройки
«Задач из почты» без окон: общие для кнопки в Revit и приложения apps/mail."""

import pytest

from lowlife import ai_settings_core, email_ai_core, settings_core
from lowlife import email_tasks_settings_core as core


@pytest.fixture
def appdata(tmpdir, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmpdir))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return tmpdir


def test_load_defaults_and_roundtrip(appdata):
    values = core.load()
    assert values["days"] == 3 and values["provider"] == email_ai_core.DEFAULT_PROVIDER
    values.update({"days": 7, "test_mode": 1, "model": u"opus"})
    assert core.save(values)
    loaded = core.load()
    assert loaded["days"] == 7 and loaded["test_mode"] is True
    assert core.settings_path() == str(appdata.join(settings_core.SETTINGS_FOLDER_NAME,
                                                    core.SETTINGS_FILE_NAME))


def test_old_model_key_moves_to_claude_cli(appdata):
    core.save({"model": u"opus", "days": u"x"})
    loaded = core.load()
    assert loaded["claude_cli_model"] == u"opus" and "model" not in loaded and loaded["days"] == 3


def test_prompt_and_days_helpers():
    assert core.stored_prompt(u"стандарт\r\n", u"стандарт") == u""
    assert core.stored_prompt(u"свой", u"стандарт") == u"свой"
    assert core.effective_prompt({"prompt": u"  "}, u"стандарт") == u"стандарт"
    assert core.parse_days(u" 5 ") == 5 and core.parse_days(u"0") is None and core.parse_days(u"abc") is None


def test_validate_connection(appdata):
    values = ai_settings_core.normalize({"provider": email_ai_core.ANTHROPIC_API})
    assert u"ключ API" in ai_settings_core.validate(values)
    values["anthropic_api_key"] = u"sk-ant-1"
    assert ai_settings_core.validate(values) is None
    values = ai_settings_core.normalize({"provider": email_ai_core.CLAUDE_CLI, "claude_path": u"/нет/claude"})
    assert u"не найден" in ai_settings_core.validate(values)
    assert u"ANTHROPIC_API_KEY" in ai_settings_core.key_hint(email_ai_core.ANTHROPIC_API)
