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

# «Марки оборудования»: конец выноски следует за УГО прибора — updater
# (lib/lowlife/tag_leader_follow.py). force — после перезагрузки pyRevit
# заменить updater старого движка свежим кодом. Отдельный try.
try:
    from pyrevit import HOST_APP as _HOST_APP
    from lowlife import tag_leader_follow as _tag_leader_follow
    _tag_leader_follow.install(_HOST_APP.uiapp, force=True)
except Exception:
    pass

# Приветствие (кнопка Tools.panel/Greeting) при каждом запуске Revit —
# отдельный try, чтобы не мешать авто-режиму выгрузки выше.
try:
    from lowlife import greeting_window

    _greet_app = None
    try:
        from pyrevit import HOST_APP
        _greet_app = HOST_APP.uiapp
    except Exception:
        _greet_app = None
    if _greet_app is None:
        try:
            _greet_app = __revit__  # noqa: F821
        except Exception:
            _greet_app = None
    greeting_window.show_on_startup(_greet_app)
except Exception:
    pass
