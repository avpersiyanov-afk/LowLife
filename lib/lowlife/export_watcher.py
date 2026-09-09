# -*- coding: utf-8 -*-
"""
Автозапуск переименования выгрузки после экспорта ModPlus.

Хук pyRevit на команду ModPlus не завёлся (см. ``docs/rename-export-files.md``),
поэтому ``install(host_app)`` (из ``startup.py`` И из ``hooks/doc-opened.py`` —
что-нибудь да сработает; повторные вызовы отсекает ``_installed``)
подписывается на два события. Весь ход пишется в
``%APPDATA%\\pyRevit\\LowLifeExportRename_watcher.log`` — если «не работает»,
смотреть туда (или Shift+клик по кнопке «Поймать id команды»).

**A. ``Autodesk.Windows.ComponentManager.ItemExecuted``** — статическое
событие ленты, срабатывает на клик по любой кнопке (в т.ч. плагинов). Если
у нажатой кнопки ``Id``/``Text``/``Cookie`` содержит любую из
``trigger_substrings`` (по умолчанию ``mprSheetExport`` — «Экспорт листов»
ModPlus), переименование «взводится» на ``ARM_WINDOW`` секунд. Точный
сигнал «пользователь запустил именно экспорт листов». Требует ``enabled``.

**B. ``UIApplication.Idling``** — Revit дёргает его в паузах между
действиями (тот же механизм, что в ``route_preview.schedule_preview_cleanup``).
Раз в ``SCAN_INTERVAL`` сек проверяет, что экспорт закончился, по:
  1. новому окну Проводника (COM ``Shell.Application``) — ModPlus в конце
     открывает папку выгрузки;
  2. закрытию модального окна — окно экспорта ModPlus модальное, при нём
     ``Idling`` не вызывается, поэтому пауза между тиками больше
     ``GAP_THRESHOLD`` = окно только что закрылось.

Переименование взведено (A) и сработал признак завершения (B) → берётся
папка нового окна Проводника, иначе ``last_folder``, иначе спрашивается
(``run_after_export``); затем ``rename_folder_interactive(...,
quiet_if_empty=True)``. Один клик по кнопке экспорта = одна попытка.

Если ``enabled`` выключен или ``AdWindows`` недоступен — работает только B
как эвристика (без «взвода»): любое новое окно Проводника со свежими
подходящими файлами, либо любой модальный диалог при свежих
``from_token``-файлах в ``last_folder``.

Ответил «Нет» по папке — она молчит ``DECLINE_QUIET`` сек; после любого
срабатывания — пауза ``REFIRE_GUARD``. Отключается целиком: Shift+клик по
кнопке «Переименование выгрузки» → «Сам замечать… : нет» (ключ
``watch_explorer``); выключение — сразу, включение — после перезагрузки
pyRevit. Проводник с вкладками (Win11): новую вкладку признак 1 не ловит.
"""

import os
import io
import time
import datetime

try:
    from lowlife import export_rename
except Exception:
    export_rename = None


LOG_NAME = "LowLifeExportRename_watcher.log"
_MAX_LOG_BYTES = 200 * 1024


def _log_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(appdata, "pyRevit")
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except Exception:
            pass
    return os.path.join(folder, LOG_NAME)


def _log(msg):
    """Диагностический след — чтобы понять, почему авто-режим молчит.
    Всё в один файл ``%APPDATA%\\pyRevit\\LowLifeExportRename_watcher.log``."""
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


# Как часто (не чаще) обрабатывать тик Idling, сек.
SCAN_INTERVAL = 2.0
# Считаем файл «только что выгруженным», если он моложе этого, сек.
FRESH_SECONDS = 1800.0
# Пауза между обработанными тиками больше этого = Idling был подавлен
# (открыт модальный диалог — например окно экспорта ModPlus — либо шла
# долгая команда). Момент закрытия такого диалога и есть сигнал
# «экспорт, возможно, только что закончился» → проверить папку.
GAP_THRESHOLD = 5.0
# На сколько секунд клик по кнопке экспорта ModPlus «взводит» переименование
# (запас на долгий пакетный экспорт).
ARM_WINDOW = 900.0
# Не срабатывать повторно чаще, чем раз в столько секунд.
REFIRE_GUARD = 20.0
# Пользователь ответил «Нет» по папке — не спрашивать про неё столько секунд.
DECLINE_QUIET = 600.0


_installed = False
_handler = None          # держим ссылку на делегат Idling, иначе GC его заберёт
_item_handler = None     # делегат ItemExecuted
_item_exec_ok = False    # удалось подписаться на ComponentManager.ItemExecuted
_ie_seen = 0             # сколько кликов по ленте залогировано (ограничитель)
_armed_until = 0.0       # до этого времени клик по кнопке экспорта «взвёл» нас
_last_scan = 0.0
_prev_tick = 0.0
_last_fire = 0.0
_ticks = 0               # сколько тиков Idling обработано (диагностика)
_seen_hwnds = set()
_declined = {}           # dir_key -> время отказа
_busy = False


def install(host_app):
    """Подписаться на Idling и ItemExecuted один раз. ``host_app`` —
    ``__revit__`` (UIControlledApplication/UIApplication) либо любой объект
    с событием ``Idling``. Вызывается из ``startup.py`` И из
    ``hooks/doc-opened.py`` — что-нибудь да отработает; повторные вызовы
    отсекает ``_installed``."""
    global _installed, _handler

    _log(u"install() called: host={} export_rename={} _installed={}".format(
        type(host_app).__name__ if host_app is not None else None,
        export_rename is not None, _installed))

    if _installed:
        return
    if export_rename is None:
        _log(u"install: export_rename не импортирован — выход")
        return
    if host_app is None:
        _log(u"install: host_app is None — выход")
        return

    try:
        cfg = export_rename.load_config()
    except Exception:
        _log(_exc(u"install: load_config упал"))
        return
    _log(u"install: watch_explorer={} enabled={} trigger_substrings={}".format(
        cfg.get("watch_explorer"), cfg.get("enabled"),
        cfg.get("trigger_substrings")))
    if not cfg.get("watch_explorer", True):
        _log(u"install: watch_explorer=выкл — авто-режим не ставим")
        return

    try:
        for hwnd, _path in _explorer_windows():
            _seen_hwnds.add(hwnd)
    except Exception:
        pass

    def _on_idling(sender, args):
        _tick()

    try:
        host_app.Idling += _on_idling
    except Exception:
        _log(_exc(u"install: подписка на Idling упала"))
        return

    _handler = _on_idling
    _installed = True
    _log(u"install: подписка на Idling ОК")

    _subscribe_item_executed()


def _subscribe_item_executed():
    """Подписка на статическое событие ленты — «взвод» по клику на кнопку
    экспорта ModPlus."""
    global _item_handler, _item_exec_ok

    try:
        import clr
        clr.AddReference("AdWindows")
        from Autodesk.Windows import ComponentManager
    except Exception:
        _log(_exc(u"ItemExecuted: AdWindows недоступен"))
        return

    def _on_item_executed(sender, e):
        global _armed_until
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
            _log(_exc(u"ItemExecuted: command_matches упал"))
        if matched and cfg.get("enabled", True):
            _armed_until = time.time() + ARM_WINDOW
            _log(u"ItemExecuted: ВЗВОД по «{}»".format(blob[:160]))
        elif matched:
            _log(u"ItemExecuted: совпало, но enabled=выкл — «{}»".format(blob[:120]))
        else:
            global _ie_seen
            _ie_seen += 1
            if _ie_seen <= 25:
                _log(u"ItemExecuted: {}".format(blob[:160]))

    try:
        ComponentManager.ItemExecuted += _on_item_executed
    except Exception:
        _log(_exc(u"ItemExecuted: подписка упала"))
        return

    _item_handler = _on_item_executed
    _item_exec_ok = True
    _log(u"ItemExecuted: подписка ОК")


def _tick():
    global _last_scan, _prev_tick, _last_fire, _armed_until, _busy, _ticks

    if _busy or export_rename is None:
        return

    now = time.time()
    if now - _last_scan < SCAN_INTERVAL:
        return

    gap = now - _last_scan if _last_scan else 0.0
    _last_scan = now
    _ticks += 1

    # Idling был подавлен дольше обычного → закрылся модальный диалог
    # (окно экспорта ModPlus?) или отработала долгая команда.
    dialog_just_closed = bool(_prev_tick) and gap >= GAP_THRESHOLD
    _prev_tick = now

    try:
        cfg = export_rename.load_config()
    except Exception:
        return
    if not cfg.get("watch_explorer", True):
        return

    try:
        windows = _explorer_windows()
    except Exception:
        windows = []

    # набор окон обновляем всегда, что бы дальше ни решили
    def _refresh_seen():
        _seen_hwnds.clear()
        _seen_hwnds.update(h for h, _p in windows)

    if now - _last_fire < REFIRE_GUARD:
        _refresh_seen()
        return

    # папки только что открытых окон Проводника со свежими подходящими файлами
    explorer_cands = []
    for hwnd, path in windows:
        if hwnd in _seen_hwnds:
            continue
        key = _dir_key(path)
        if key and _fresh_and_not_declined(key, path, cfg, now):
            explorer_cands.append((key, path, u"Открыта папка: {}".format(path)))
    _refresh_seen()

    precise = _item_exec_ok and cfg.get("enabled", True)

    if dialog_just_closed:
        _log(u"tick #{}: пауза {:.0f}с — модальное окно закрылось; "
             u"precise={} armed={} explorer_cands={}".format(
                 _ticks, gap, precise, now < _armed_until, len(explorer_cands)))
    elif explorer_cands:
        _log(u"tick #{}: новое окно Проводника {}; precise={} armed={}".format(
            _ticks, [c[1] for c in explorer_cands], precise, now < _armed_until))

    if precise:
        if now >= _armed_until:
            return  # клика по кнопке экспорта не было — не лезем
        if not (dialog_just_closed or explorer_cands):
            return  # экспорт, похоже, ещё идёт — ждём
        _armed_until = 0.0  # один клик = одна попытка
        _log(u"tick #{}: ВЗВЕДЕНО + признак завершения → пробуем переименовать".format(_ticks))
        _busy = True
        try:
            _do_after_export(cfg, now, explorer_cands, ask_if_unknown=True)
        finally:
            _busy = False
        return

    # --- эвристика без «взвода» (enabled выкл / нет AdWindows) ---
    candidates = list(explorer_cands)
    if dialog_just_closed:
        last = cfg.get("last_folder") or u""
        key = _dir_key(last)
        if (key and key not in [c[0] for c in candidates] and os.path.isdir(last)
                and _fresh_and_not_declined(key, last, cfg, now)):
            candidates.append((key, last, u"Похоже, экспорт завершился."))
    if not candidates:
        return
    _busy = True
    try:
        for key, path, label in candidates:
            _fire_folder(key, path, label, cfg)
    finally:
        _busy = False


def _do_after_export(cfg, now, explorer_cands, ask_if_unknown):
    """Взведённый режим: папка нового окна Проводника → last_folder → спросить."""
    if explorer_cands:
        for key, path, label in explorer_cands:
            _fire_folder(key, path, label, cfg)
        return

    last = cfg.get("last_folder") or u""
    key = _dir_key(last)
    if key and os.path.isdir(last) and _fresh_and_not_declined(key, last, cfg, now):
        _fire_folder(key, last, u"Экспорт ModPlus завершён.", cfg)
        return

    _log(u"_do_after_export: папка не определена (окон Проводника нет, "
         u"last_folder={!r} свежих файлов нет) → {}".format(
             last, u"спрашиваем" if ask_if_unknown else u"пропуск"))
    if ask_if_unknown:
        try:
            export_rename.run_after_export(
                command_id_text=u"ModPlus: экспорт листов")
        except Exception:
            _log(_exc(u"_do_after_export: run_after_export упал"))


def _fire_folder(key, path, label, cfg):
    global _last_fire
    _last_fire = time.time()
    try:
        res = export_rename.rename_folder_interactive(
            path, cfg=cfg, source_label=label, quiet_if_empty=True)
    except Exception:
        res = None
        _log(_exc(u"_fire_folder: rename_folder_interactive упал"))
    _log(u"_fire_folder: {} → {}".format(path, res))
    if res == "declined":
        _declined[key] = time.time()
    elif res == "renamed":
        _declined.pop(key, None)


def status_text():
    """Многострочная сводка состояния — для диагностической кнопки."""
    now = time.time()
    lines = [
        u"export_watcher:",
        u"  _installed={}  _item_exec_ok={}  тиков Idling обработано={}".format(
            _installed, _item_exec_ok, _ticks),
        u"  взведено={}  (осталось {:.0f}с)".format(
            now < _armed_until, max(0.0, _armed_until - now)),
        u"  последний тик {:.0f}с назад, последнее срабатывание {:.0f}с назад".format(
            now - _last_scan if _last_scan else -1,
            now - _last_fire if _last_fire else -1),
    ]
    try:
        cfg = export_rename.load_config()
        lines.append(u"  cfg: watch_explorer={} enabled={} trigger={} last_folder={!r}".format(
            cfg.get("watch_explorer"), cfg.get("enabled"),
            cfg.get("trigger_substrings"), cfg.get("last_folder")))
    except Exception:
        lines.append(u"  cfg: не прочитать")
    try:
        wins = _explorer_windows()
        lines.append(u"  окон Проводника сейчас: {}".format([w[1] for w in wins]))
    except Exception:
        lines.append(u"  окна Проводника: не перечислить")
    lines.append(u"  лог: {}".format(_log_path()))
    return u"\n".join(lines)


def _dir_key(path):
    try:
        return os.path.normcase(os.path.abspath(path))
    except Exception:
        return None


def _fresh_and_not_declined(key, folder, cfg, now):
    declined_at = _declined.get(key, 0)
    if declined_at and now - declined_at < DECLINE_QUIET:
        return False
    return _has_fresh_match(folder, cfg, now)


def _has_fresh_match(folder, cfg, now):
    """В папке есть хотя бы один подходящий файл (по ``plan_renames``),
    изменённый недавно."""
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


def _explorer_windows():
    """Список ``(hwnd, filesystem_path)`` открытых окон Проводника
    Windows. Пустой список — если COM недоступен."""
    out = []

    try:
        from System import Activator, Type
    except Exception:
        return out

    try:
        shell_type = Type.GetTypeFromProgID("Shell.Application")
        if shell_type is None:
            return out
        shell = Activator.CreateInstance(shell_type)
        windows = shell.Windows()
    except Exception:
        return out

    try:
        count = windows.Count
    except Exception:
        count = 0

    for i in range(count):
        try:
            w = windows.Item(i)
        except Exception:
            continue
        if w is None:
            continue

        # окно именно Проводника, а не Internet Explorer
        try:
            full = (w.FullName or u"").lower()
        except Exception:
            full = u""
        if not full.endswith(u"explorer.exe"):
            continue

        try:
            hwnd = int(w.HWND)
        except Exception:
            continue

        path = _window_path(w)
        if path and os.path.isdir(path):
            out.append((hwnd, path))

    return out


def _window_path(w):
    # 1) через shell-объект папки
    try:
        p = w.Document.Folder.Self.Path
        if p:
            return p
    except Exception:
        pass
    # 2) из LocationURL (file:///C:/...)
    try:
        url = w.LocationURL or u""
    except Exception:
        url = u""
    if url.startswith(u"file:"):
        try:
            from System import Uri
            return Uri(url).LocalPath
        except Exception:
            return None
    return None
