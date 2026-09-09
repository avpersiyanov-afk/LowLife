# -*- coding: utf-8 -*-
"""
Автозапуск переименования выгрузки после экспорта ModPlus.

Лёгкая версия — без опроса окон Проводника (COM ``Shell.Application`` на
UI-потоке каждый тик оказался слишком тяжёлым и мог подвесить Revit).

``install(host_app)`` вызывается из ``startup.py`` И из
``hooks/doc-opened.py`` (что-нибудь да сработает; дубли отсекает
процесс-глобальный флаг в ``sys``) и подписывается на два события:

**A. ``Autodesk.Windows.ComponentManager.ItemExecuted``** — клик по кнопке
ленты. Если у кнопки ``Id``/``Text``/``Cookie`` подходит под
``trigger_substrings`` (по умолчанию ``mprSheetExport`` — «Экспорт листов»
ModPlus), переименование «взводится» на ``ARM_WINDOW`` сек. Требует
``enabled``.

**B. ``UIApplication.Idling``** — раз в ``SCAN_INTERVAL`` сек. Если
переименование взведено (A) и между обработанными тиками была пауза больше
``GAP_THRESHOLD`` (окно экспорта ModPlus модальное → при нём ``Idling`` не
вызывается → пауза = окно закрылось) — берётся ``last_folder``; если там
есть свежие (моложе ``FRESH_SECONDS``) файлы с ``from_token`` в имени →
``rename_folder_interactive``, иначе один раз спрашивается
(``run_after_export``). Один клик по кнопке экспорта = одна попытка.

Аварийный выключатель: файл ``%APPDATA%\\pyRevit\\LowLifeExportRename_OFF``
(любого содержимого) — ``install`` тогда ничего не делает. Штатно —
``watch_explorer`` в настройках кнопки.

Весь ход пишется в ``%APPDATA%\\pyRevit\\LowLifeExportRename_watcher.log``.
"""

import os
import io
import sys
import time
import datetime

try:
    from lowlife import export_rename
except Exception:
    export_rename = None


# Как часто (не чаще) обрабатывать тик Idling, сек.
SCAN_INTERVAL = 2.0
# Считаем файл «только что выгруженным», если он моложе этого, сек.
FRESH_SECONDS = 1800.0
# Пауза между обработанными тиками больше этого = Idling был подавлен
# (модальное окно экспорта ModPlus / долгая команда) и только что снят.
GAP_THRESHOLD = 5.0
# На сколько секунд клик по кнопке экспорта «взводит» переименование.
ARM_WINDOW = 900.0
# Если паузы Idling так и не было (окно экспорта ModPlus не модальное) —
# через столько секунд после клика всё равно проверить last_folder (но
# только если там реально есть свежие файлы; папку не спрашивать).
POST_CLICK_FALLBACK = 25.0
# Не срабатывать повторно чаще, чем раз в столько секунд.
REFIRE_GUARD = 20.0

LOG_NAME = "LowLifeExportRename_watcher.log"
OFF_NAME = "LowLifeExportRename_OFF"
_MAX_LOG_BYTES = 200 * 1024

# Процесс-глобальные (переживают переимпорт модуля при перезагрузке pyRevit) —
# чтобы не наплодить подписок на Idling/ItemExecuted при каждой перезагрузке.
_SYS_KEY = "_lowlife_export_watcher"


_armed_until = 0.0
_armed_at = 0.0
_armed_hb = 0.0
_last_scan = 0.0
_prev_tick = 0.0
_last_fire = 0.0
_ticks = 0
_ie_seen = 0
_busy = False


def _pg():
    """Словарь процесс-глобального состояния, живущий в ``sys``."""
    d = getattr(sys, _SYS_KEY, None)
    if d is None:
        d = {"idling_installed": False, "item_installed": False,
             "idling_host": None, "idling_delegate": None,
             "item_delegate": None}
        setattr(sys, _SYS_KEY, d)
    return d


def _appdata_pyrevit():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(appdata, "pyRevit")
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except Exception:
            pass
    return folder


def _log_path():
    return os.path.join(_appdata_pyrevit(), LOG_NAME)


def _off_file():
    return os.path.join(_appdata_pyrevit(), OFF_NAME)


def _log(msg):
    try:
        path = _log_path()
        try:
            if os.path.getsize(path) > _MAX_LOG_BYTES:
                os.remove(path)
        except Exception:
            pass
        with io.open(path, "a", encoding="utf-8") as f:
            f.write(u"{}  {}\n".format(
                datetime.datetime.now().strftime(u"%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def _exc(prefix):
    import traceback
    return u"{}: {}".format(prefix, traceback.format_exc().splitlines()[-1])


def ensure_installed():
    """Сам добыть приложение Revit и вызвать install(). Для вызова из
    скриптов кнопок — на случай, если ни startup.py, ни hooks/doc-opened.py
    в этой сборке pyRevit не отработали."""
    app = None
    try:
        from pyrevit import HOST_APP
        app = HOST_APP.uiapp
    except Exception:
        app = None
    if app is None:
        try:
            import __builtin__
            app = getattr(__builtin__, "__revit__", None)
        except Exception:
            app = None
    _log(u"ensure_installed(): app={}".format(
        type(app).__name__ if app is not None else None))
    install(app)


def install(host_app):
    """Подписаться на Idling и ItemExecuted. Идемпотентно на уровне процесса
    (не только модуля)."""
    if export_rename is None:
        _log(u"install: export_rename не импортирован — выход")
        return

    if os.path.isfile(_off_file()):
        _log(u"install: есть файл-выключатель {} — авто-режим не ставим".format(
            OFF_NAME))
        return

    try:
        cfg = export_rename.load_config()
    except Exception:
        _log(_exc(u"install: load_config упал"))
        return
    if not cfg.get("watch_explorer", True):
        _log(u"install: watch_explorer=выкл")
        return

    _install_idling(host_app)
    _install_item_executed()


def _install_idling(host_app):
    pg = _pg()
    if pg["idling_installed"]:
        return
    if host_app is None:
        _log(u"install: host_app is None — Idling не подписан")
        return

    def _on_idling(sender, args):
        try:
            _tick()
        except Exception:
            _log(_exc(u"_tick упал"))

    try:
        host_app.Idling += _on_idling
    except Exception:
        _log(_exc(u"install: подписка на Idling упала"))
        return

    pg["idling_installed"] = True
    pg["idling_host"] = host_app
    pg["idling_delegate"] = _on_idling
    _log(u"install: Idling ОК (host={})".format(type(host_app).__name__))


def _install_item_executed():
    pg = _pg()
    if pg["item_installed"]:
        return

    try:
        import clr
        clr.AddReference("AdWindows")
        from Autodesk.Windows import ComponentManager
    except Exception:
        _log(_exc(u"ItemExecuted: AdWindows недоступен"))
        return

    def _on_item_executed(sender, e):
        global _armed_until, _armed_at, _ie_seen
        try:
            cfg = export_rename.load_config()
        except Exception:
            return
        try:
            item = e.Item
        except Exception:
            item = None
        if item is None:
            return
        blob = u" ".join(
            unicode(getattr(item, a, u"") or u"")
            for a in (u"Id", u"Text", u"Cookie"))
        matched = False
        try:
            matched = export_rename.command_matches(blob, cfg)
        except Exception:
            pass
        if matched and cfg.get("enabled", True):
            _armed_until = time.time() + ARM_WINDOW
            _armed_at = time.time()
            _log(u"ItemExecuted: ВЗВОД по «{}»".format(blob[:160]))
        elif matched:
            _log(u"ItemExecuted: совпало, но enabled=выкл")
        elif _ie_seen < 25:
            _ie_seen += 1
            _log(u"ItemExecuted: {}".format(blob[:160]))

    try:
        ComponentManager.ItemExecuted += _on_item_executed
    except Exception:
        _log(_exc(u"ItemExecuted: подписка упала"))
        return

    pg["item_installed"] = True
    pg["item_delegate"] = _on_item_executed
    _log(u"ItemExecuted: подписка ОК")


def _tick():
    global _last_scan, _prev_tick, _last_fire, _armed_until, _armed_hb, _busy, _ticks

    if _busy or export_rename is None:
        return

    now = time.time()
    if now - _last_scan < SCAN_INTERVAL:
        return

    gap = now - _last_scan if _last_scan else 0.0
    prev = _prev_tick
    _last_scan = now
    _prev_tick = now
    _ticks += 1

    # ничего не взведено — самый частый случай, выходим максимально дёшево
    if now >= _armed_until:
        return

    if now - _last_fire < REFIRE_GUARD:
        return

    dialog_just_closed = bool(prev) and gap >= GAP_THRESHOLD
    since_arm = now - _armed_at if _armed_at else 0.0
    fallback = since_arm >= POST_CLICK_FALLBACK

    if now - _armed_hb >= 15.0:
        _armed_hb = now
        _log(u"tick #{}: взведено, ждём завершения (пауза={}с, с клика={}с)".format(
            _ticks, int(gap), int(since_arm)))

    if not (dialog_just_closed or fallback):
        return  # экспорт ещё идёт — ждём

    try:
        cfg = export_rename.load_config()
    except Exception:
        return
    if not cfg.get("watch_explorer", True) or not cfg.get("enabled", True):
        return

    _armed_until = 0.0  # один клик по кнопке экспорта = одна попытка
    _last_fire = now
    trg = u"пауза {}с (окно закрылось)".format(int(gap)) if dialog_just_closed \
        else u"прошло {}с после клика, паузы не было".format(int(since_arm))
    _log(u"tick #{}: взведено + {} → проверяем выгрузку".format(_ticks, trg))

    _busy = True
    try:
        last = cfg.get("last_folder") or u""
        if last and os.path.isdir(last) and _has_fresh_match(last, cfg, now):
            _log(u"tick: last_folder со свежими файлами → {}".format(last))
            try:
                res = export_rename.rename_folder_interactive(
                    last, cfg=cfg, source_label=u"Экспорт ModPlus завершён.",
                    quiet_if_empty=True)
            except Exception:
                res = None
                _log(_exc(u"rename_folder_interactive упал"))
            _log(u"tick: результат {}".format(res))
        elif dialog_just_closed:
            _log(u"tick: last_folder={!r} без свежих файлов → спрашиваем "
                 u"папку".format(last))
            try:
                export_rename.run_after_export(
                    command_id_text=u"ModPlus: экспорт листов")
            except Exception:
                _log(_exc(u"run_after_export упал"))
        else:
            _log(u"tick: last_folder={!r} без свежих файлов, паузы не было "
                 u"— не спрашиваем (нажми кнопку вручную)".format(last))
    finally:
        _busy = False


def _has_fresh_match(folder, cfg, now):
    try:
        plans = export_rename.plan_renames(folder, cfg)
    except Exception:
        return False
    for src, _dst, status in plans:
        if status != "ok":
            continue
        try:
            if now - os.path.getmtime(src) <= FRESH_SECONDS:
                return True
        except Exception:
            continue
    return False


def status_text():
    """Сводка состояния — для диагностической кнопки. Всё в int/строках:
    IronPython 2.7 роняет ``{:.0f}`` на int («Precision not allowed in
    integer format specifier»)."""
    pg = _pg()
    now = time.time()
    armed_left = int(max(0.0, _armed_until - now))
    since_tick = int(now - _last_scan) if _last_scan else -1
    since_fire = int(now - _last_fire) if _last_fire else -1
    lines = [
        u"export_watcher (лёгкая версия, без опроса Проводника):",
        u"  Idling подписан={}  ItemExecuted подписан={}".format(
            pg.get("idling_installed"), pg.get("item_installed")),
        u"  тиков Idling обработано={}  кликов по ленте залогировано={}".format(
            _ticks, _ie_seen),
        u"  взведено={}  (осталось {}с)".format(bool(now < _armed_until), armed_left),
        u"  последний тик {}с назад, последнее срабатывание {}с назад".format(
            since_tick, since_fire),
        u"  файл-выключатель {}: {}".format(
            OFF_NAME, u"ЕСТЬ (авто выкл)" if os.path.isfile(_off_file()) else u"нет"),
    ]
    try:
        cfg = export_rename.load_config()
        lines.append(
            u"  cfg: watch_explorer={} enabled={} trigger={} last_folder={!r}".format(
                cfg.get("watch_explorer"), cfg.get("enabled"),
                cfg.get("trigger_substrings"), cfg.get("last_folder")))
    except Exception:
        lines.append(u"  cfg: не прочитать")
    lines.append(u"  лог: {}".format(_log_path()))
    return u"\n".join(lines)
