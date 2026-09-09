# -*- coding: utf-8 -*-

__title__ = u"Переименование\nвыгрузки"
__doc__ = (
    u"Переименовывает файлы выгрузки Revit/ModPlus: в имени каждого файла "
    u"меняет «0000» на «000» (по умолчанию). Нужно, когда два листа идут "
    u"под одним номером, но с разными именами — им дают разные номера "
    u"(«0000» и «000»), а после выгрузки приводят к одному.\n\n"
    u"Обычный клик — спросить папку выгрузки (подставляется прошлый путь), "
    u"показать список и переименовать. Ничего в модели не меняется.\n\n"
    u"Shift+клик — настройки: что на что менять, расширения, подпапки, "
    u"автозапуск после команды (нужен id команды ModPlus, см. "
    u"docs/rename-export-files.md)."
)
__author__ = "Pipers"

from pyrevit import EXEC_PARAMS

from lowlife import export_rename

# заодно поднять авто-режим на эту сессию — вдруг startup.py / doc-opened
# в этой сборке pyRevit не отработали
try:
    from lowlife import export_watcher
    export_watcher.ensure_installed()
except Exception:
    pass

try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    export_rename.configure()
else:
    export_rename.run_after_export()
