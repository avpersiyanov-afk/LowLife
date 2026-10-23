# -*- coding: utf-8 -*-
"""
Чистая логика отдельного приложения «Задачи из почты» (apps/mail, для
тех, у кого нет Revit): где лежат настройки и как пересказать сообщения,
написанные для кнопки в Revit.
"""

import os
import re

from lowlife import ai_settings_core

PYREVIT_FOLDER = u"pyRevit"
APP_FOLDER = u"LowLife"


def settings_folder_name(appdata):
    """Папка настроек в %APPDATA%: если на компьютере уже настроена кнопка
    в Revit (есть %APPDATA%\\pyRevit\\LowLifeEmailTasks_settings.json) — её
    файл, чтобы настройки были общими; иначе своя папка LowLife."""
    existing = os.path.join(appdata or u"", PYREVIT_FOLDER, ai_settings_core.SETTINGS_FILE_NAME)
    return PYREVIT_FOLDER if appdata and os.path.isfile(existing) else APP_FOLDER


# Сообщения библиотеки отсылают к настройкам кнопки («Shift+клик по
# кнопке»); в приложении настройки открываются кнопкой «Настройки».
_SHIFT_CLICK = [
    (re.compile(u"в настройках кнопки \\(Shift\\+клик\\)"), u"в настройках (кнопка «Настройки»)"),
    (re.compile(u"\\(Shift\\+клик по кнопке\\)"), u"(кнопка «Настройки»)"),
    (re.compile(u"\\(Shift\\+клик\\)"), u"(кнопка «Настройки»)"),
    (re.compile(u"\\(Shift\\+клик ([^)]*)\\)"), u"(кнопка «Настройки» \\1)"),
    (re.compile(u"Shift\\+клик по кнопке"), u"кнопка «Настройки»"),
    (re.compile(u"Shift\\+клик"), u"кнопка «Настройки»"),
    (re.compile(u"процесса Revit"), u"этой программы"),
]


def app_text(text):
    """Сообщение для окна приложения: без отсылок к Shift+клику по кнопке."""
    text = text or u""
    for pattern, replacement in _SHIFT_CLICK:
        text = pattern.sub(replacement, text)
    return text
