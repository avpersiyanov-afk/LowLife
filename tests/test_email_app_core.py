# -*- coding: utf-8 -*-
"""Тесты для lowlife.email_app_core — отдельное приложение «Задачи из
почты»: папка настроек и пересказ сообщений кнопки."""

from lowlife import email_app_core


def test_settings_folder_shared_with_revit_button_when_it_exists(tmpdir):
    assert email_app_core.settings_folder_name(str(tmpdir)) == u"LowLife"
    tmpdir.mkdir(u"pyRevit").join(u"LowLifeEmailTasks_settings.json").write(u"{}")
    assert email_app_core.settings_folder_name(str(tmpdir)) == u"pyRevit"
    assert email_app_core.settings_folder_name(None) == u"LowLife"


def test_app_text_has_no_shift_click():
    cases = {
        u"Проверьте ключ в настройках (Shift+клик по кнопке).": u"Проверьте ключ в настройках (кнопка «Настройки»).",
        u"Проверьте поле «Модель» в настройках (Shift+клик): например": u"Проверьте поле «Модель» в настройках (кнопка «Настройки»): например",
        u"Вставьте ключ в настройках кнопки (Shift+клик) — там же": u"Вставьте ключ в настройках (кнопка «Настройки») — там же",
        u"Проверьте настройки: Shift+клик по кнопке.": u"Проверьте настройки: кнопка «Настройки».",
        u"(ссылка в настройках — Shift+клик)": u"(ссылка в настройках — кнопка «Настройки»)",
    }
    for source, expected in cases.items():
        assert email_app_core.app_text(source) == expected
    assert email_app_core.app_text(None) == u""
