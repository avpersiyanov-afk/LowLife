# -*- coding: utf-8 -*-
"""
Стартовый скрипт расширения — pyRevit выполняет его один раз при загрузке
(если поддерживает; на всякий случай то же самое делает
``hooks/doc-opened.py``).

Задачи:
1. включить авто-режим переименования выгрузки —
   ``lib/lowlife/export_watcher.install()``;
2. вернуть выбранную тему ленты (``panel_themes.restore_on_idle``): pyRevit
   выполняет этот файл при каждой загрузке — запуск Revit, перезагрузка,
   обновление расширения — но ДО построения ленты, а построенная лента
   показывает все кнопки. Поэтому тема включается при первом простое
   Revit. (``hooks/app-init.py`` для этого не годится: это событие Revit
   ApplicationInitialized, при перезагрузке pyRevit его нет.)
3. построить панели «Избранного» (``favorites.restore_on_idle``) — тоже при
   первом простое: pyRevit при загрузке прячет чужие панели вкладки и
   пересобирает команды кнопок в новую сборку.

По первой задаче пишем след в
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


# Тема ленты — отдельный try, ничего выше не задевает.
try:
    from lowlife import panel_themes as _panel_themes

    _theme_app = None
    try:
        _theme_app = __revit__  # noqa: F821 — UIControlledApplication / UIApplication
    except Exception:
        _theme_app = None
    if _theme_app is None:
        from pyrevit import HOST_APP as _theme_host
        _theme_app = _theme_host.uiapp
    if _theme_app is not None:
        _panel_themes.restore_on_idle(_theme_app)
except Exception as exc:
    _crumb(u"тема ленты: {}".format(exc))



# Избранное — отдельный try, ничего выше не задевает.
try:
    from lowlife import favorites as _favorites

    _fav_app = None
    try:
        _fav_app = __revit__  # noqa: F821 — UIControlledApplication / UIApplication
    except Exception:
        _fav_app = None
    if _fav_app is None:
        from pyrevit import HOST_APP as _fav_host
        _fav_app = _fav_host.uiapp
    if _fav_app is not None:
        _favorites.restore_on_idle(_fav_app)
except Exception as exc:
    _crumb(u"избранное: {}".format(exc))
