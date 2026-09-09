# -*- coding: utf-8 -*-
"""
Стартовый скрипт расширения — pyRevit выполняет его один раз при загрузке
(если поддерживает; на всякий случай то же самое делает
``hooks/doc-opened.py``).

Единственная задача: включить авто-режим переименования выгрузки —
``lib/lowlife/export_watcher.install()``. Пишем след в
``%APPDATA%\\pyRevit\\LowLifeExportRename_watcher.log``, чтобы понять,
запускается ли этот файл вообще.
"""

import os
import io
import datetime


def _crumb(msg):
    try:
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(appdata, "pyRevit", "LowLifeExportRename_watcher.log")
        with io.open(path, "a", encoding="utf-8") as f:
            f.write(u"{}  startup.py: {}\n".format(
                datetime.datetime.now().strftime(u"%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


_crumb(u"файл выполняется")

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

    _crumb(u"export_watcher импортирован, _app={}".format(
        type(_app).__name__ if _app is not None else None))

    if _app is not None:
        export_watcher.install(_app)
    else:
        _crumb(u"_app is None — install не вызван")
except Exception as exc:
    _crumb(u"ОШИБКА: {}".format(exc))
