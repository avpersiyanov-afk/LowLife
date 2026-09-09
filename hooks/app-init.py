# -*- coding: utf-8 -*-
"""
Один раз при запуске Revit — поднять авто-режим переименования выгрузки
(export_watcher.install). Это самый ранний и надёжный момент: не требует
ни открытого документа (в отличие от doc-opened.py), ни поддержки
startup.py конкретной сборкой pyRevit.

Всё в try/except — проблема здесь не должна мешать загрузке Revit.
Подробный след пишется самим export_watcher в
%APPDATA%\\pyRevit\\LowLifeExportRename_watcher.log.
"""

try:
    from lowlife import export_watcher

    app = None
    try:
        from pyrevit import HOST_APP
        app = HOST_APP.uiapp
    except Exception:
        app = None
    if app is None:
        try:
            app = __revit__  # noqa: F821 — UIControlledApplication
        except Exception:
            app = None

    # install() и с app=None подпишется на ComponentManager.ItemExecuted
    # (главный триггер); Idling нужен только для служебного флага.
    export_watcher.install(app)
except Exception:
    pass
