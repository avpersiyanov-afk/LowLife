# -*- coding: utf-8 -*-
"""Текст для кнопки «Приветствие» (Tools.panel/Greeting): приветствие по
времени суток и имени пользователя, большими буквами. Без Revit API."""


def part_of_day(hour):
    """Приветствие по часу (0–23): утро 5–11, день 12–16, вечер 17–22, ночь."""
    if 5 <= hour < 12:
        return u"Доброе утро"
    if 12 <= hour < 17:
        return u"Добрый день"
    if 17 <= hour < 23:
        return u"Добрый вечер"
    return u"Доброй ночи"


def greeting_lines(hour, name=None):
    """Две строки для окна: крупное приветствие и имя (или пустая строка).

    Всё в верхнем регистре — окно показывает их большими буквами.
    """
    name = (name or u"").strip()
    if not name:
        return u"{}!".format(part_of_day(hour)).upper(), u""
    return u"{},".format(part_of_day(hour)).upper(), u"{}!".format(name).upper()
