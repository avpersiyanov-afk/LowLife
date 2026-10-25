# -*- coding: utf-8 -*-
"""Язык интерфейса LowLife: русский (основной) или английский.

Выбирается списком «Язык» на панели LowLife и хранится в
``%APPDATA%\\pyRevit\\LowLifeLanguage_settings.json``. Без Revit API и clr —
модуль импортируется и в программе «Задачи из почты».

Лента переводится целиком (``ribbon_language``: английские ``title_en``/``tooltip_en``
из ``bundle.yaml`` каждой кнопки и панели). Текст окон и сообщений пишется через
``tr(u"по-русски", u"in English")`` — русский остаётся основным, английский
подставляется, если выбран English.
"""
import os

RU = "ru"
EN = "en"
LANGUAGES = (RU, EN)
DEFAULT = RU

# Подписи участников списка «Язык» — одинаковые при любом языке, чтобы свой язык было видно всегда.
LABELS = {RU: u"Русский", EN: u"English"}

_STORE = None
_CACHE = {"mtime": None, "lang": None}


def _store():
    global _STORE
    if _STORE is None:
        from lowlife import settings_core
        _STORE = settings_core.JsonStore("LowLifeLanguage_settings.json", u"языка интерфейса",
                                         share=False)
    return _STORE


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except (IOError, OSError):
        return None


def current():
    """Выбранный язык (``"ru"``/``"en"``). Файл перечитывается, только когда он изменился:
    у движка каждой кнопки своя копия модуля, а язык меняет кнопка-список."""
    try:
        path = _store().path()
    except Exception:
        return DEFAULT
    mtime = _mtime(path)
    if _CACHE["lang"] is None or mtime != _CACHE["mtime"]:
        lang = None
        try:
            lang = _store().read().get("language")
        except Exception:
            lang = None
        _CACHE["lang"] = lang if lang in LANGUAGES else DEFAULT
        _CACHE["mtime"] = mtime
    return _CACHE["lang"]


def save(lang):
    """Запомнить язык; неизвестный код игнорируется. Возвращает сохранённый язык или None."""
    if lang not in LANGUAGES:
        return None
    _store().update({"language": lang})
    _CACHE["lang"] = None  # перечитать при следующем current()
    return lang


def is_en():
    return current() == EN


def tr(ru, en=None):
    """Строка на выбранном языке: ``en``, если выбран английский и перевод есть, иначе ``ru``."""
    if en and current() == EN:
        return en
    return ru


def pick(values, lang=None):
    """Значение из словаря ``{"ru": ..., "en": ...}`` на выбранном языке (иначе — русское)."""
    lang = lang or current()
    return values.get(lang) or values.get(RU) or u""
