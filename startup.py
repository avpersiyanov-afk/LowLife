# -*- coding: utf-8 -*-
"""
Стартовый скрипт расширения — pyRevit выполняет его один раз при загрузке.

Пока нужен только для одного: включить слежение за открытием папки
выгрузки в Проводнике (кнопка «Переименование выгрузки», ключ настроек
``watch_explorer``). Вся логика — в ``lib/lowlife/export_watcher.py``;
здесь только передаём ему приложение Revit и гасим любые ошибки, чтобы
проблема в watcher'е не помешала загрузиться расширению.
"""

try:
    from lowlife import export_watcher

    _app = None
    try:
        _app = __revit__  # noqa: F821 — pyRevit кладёт сюда UIControlledApplication
    except Exception:
        _app = None

    if _app is None:
        try:
            from pyrevit import HOST_APP
            _app = HOST_APP.uiapp
        except Exception:
            _app = None

    if _app is not None:
        export_watcher.install(_app)
except Exception:
    pass
