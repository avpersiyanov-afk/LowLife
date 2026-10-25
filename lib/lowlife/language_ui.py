# -*- coding: utf-8 -*-
"""Окно кнопки «Язык / Language» (панель LowLife): выбрать русский или английский.

Выбор сохраняется (lowlife.i18n) и сразу переводит ленту (lowlife.ribbon_language.switch).
Подписи окна — на обоих языках сразу: его должен понять тот, кто не читает текущий язык.
"""
from lowlife import i18n

_CURRENT_MARK = u"✓ "


def _options(current):
    """[(подпись в окне, код языка)] — текущий язык помечен галочкой."""
    return [((_CURRENT_MARK if lang == current else u"") + i18n.LABELS[lang], lang)
            for lang in i18n.LANGUAGES]


def chosen_language(label, current):
    """Код языка по подписи, которую вернуло окно, или None."""
    for text, lang in _options(current):
        if text == label:
            return lang
    return None


def run():
    from lowlife import ribbon_language, select_list

    current = i18n.current()
    options = _options(current)
    label = select_list.CommandSwitchWindow.show(
        [text for text, _ in options],
        message=u"Язык LowLife / LowLife language")
    lang = chosen_language(label, current) if label else None
    if lang is None:
        return
    ribbon_language.switch(lang)
