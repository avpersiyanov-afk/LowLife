# -*- coding: utf-8 -*-
"""
При открытии проекта:
1. включить авто-режим переименования выгрузки (export_watcher.install) —
   надёжнее, чем startup.py, который не во всякой сборке pyRevit
   выполняется;
2. тихий мониторинг каталога семейств (см. ниже).

Тихий мониторинг каталога семейств: если в настройках включено «проверять
актуальность при открытии» (Shift+клик по кнопке «Обновление/проверка семейств» →
вопрос про мониторинг), быстро проверяет — не устарели ли загруженные
семейства относительно каталога — и, если да, показывает toast.
Ничего модального, ничего не меняет.

Проверка НЕ сканирует каталог: для каждого помеченного семейства берёт
путь и дату из его скрытой метки и делает один stat по файлу
(check_stale_against_catalog). Дёшево даже на сетевой библиотеке.
"""

try:
    from pyrevit import forms, EXEC_PARAMS
    from lowlife import family_catalog as fc
except Exception:
    forms = None
    fc = None


def _install_export_watcher():
    try:
        from lowlife import export_watcher
    except Exception:
        return
    app = None
    try:
        from pyrevit import HOST_APP
        app = HOST_APP.uiapp
    except Exception:
        app = None
    if app is None:
        try:
            app = __revit__  # noqa: F821
        except Exception:
            app = None
    if app is not None:
        try:
            export_watcher.install(app)
        except Exception:
            pass


_install_export_watcher()


def _run():
    if fc is None or not fc.load_monitor_enabled():
        return

    try:
        doc = EXEC_PARAMS.event_args.Document
    except Exception:
        doc = None
    if doc is None:
        return
    try:
        if doc.IsFamilyDocument:
            return
    except Exception:
        return

    try:
        stale, checked, names = fc.check_stale_against_catalog(doc)
    except Exception:
        return

    if stale <= 0:
        return

    msg = u"{} семейств(а) устарели относительно каталога.".format(stale)
    if names:
        msg += u"\n" + u", ".join(names[:8])
        if stale > 8:
            msg += u" …"
    msg += u"\nЗапустите «Обновление/проверка семейств» для обновления."

    try:
        forms.toast(msg, title=u"Каталог семейств")
    except Exception:
        try:
            forms.alert(msg, title=u"Каталог семейств")
        except Exception:
            pass


_run()
