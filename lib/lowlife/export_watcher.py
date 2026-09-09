# -*- coding: utf-8 -*-
"""
Слежение за завершением экспорта ModPlus (без хука на команду).

Хук на команду ModPlus не завёлся (нет журналов Revit, чтобы достать её
id — см. ``docs/rename-export-files.md``), поэтому ``install(host_app)`` из
``startup.py`` подписывается на ``UIApplication.Idling`` (Revit дёргает его
в паузах между действиями — тот же механизм, что в
``route_preview.schedule_preview_cleanup``) и раз в ``SCAN_INTERVAL`` сек
проверяет два косвенных признака того, что экспорт только что закончился:

1. Новое окно Проводника. ModPlus в конце экспорта открывает папку с
   результатом. Обработчик перечисляет окна Проводника через COM
   ``Shell.Application``; появилось НОВОЕ окно — берём его папку.
2. Закрытие модального окна. Окно экспорта ModPlus модальное (пока оно
   открыто, другие команды недоступны) — значит и ``Idling`` при нём не
   вызывается. Если пауза между обработанными тиками вышла больше
   ``GAP_THRESHOLD`` — модальное окно только что закрылось; тогда
   дополнительно проверяем прошлую папку выгрузки (``last_folder``): ModPlus
   мог Проводник и не открыть, а экспорт часто идёт туда же.

В обоих случаях, если в папке есть файлы с ``from_token`` в имени моложе
``FRESH_SECONDS`` — вызывается ``rename_folder_interactive(...,
quiet_if_empty=True)``. Ответил «Нет» — папка молчит ``DECLINE_QUIET`` сек;
после любого срабатывания — пауза ``REFIRE_GUARD``.

Ограничения (осознанные):
- работает всю сессию Revit; лёгкий COM-поллинг окон;
- п.1 сработает на ЛЮБОМ новом окне Проводника со свежими подходящими
  файлами; п.2 — после любого модального диалога, но только если в
  ``last_folder`` лежат свежие ``from_token``-файлы;
- Проводник с вкладками (Win11): папку, открытую новой вкладкой в
  существующем окне, п.1 не ловит (остаётся п.2);
- отключается: Shift+клик по кнопке «Переименование выгрузки» → «Следить
  … : нет» (ключ ``watch_explorer``); выключение — сразу, включение —
  после перезагрузки pyRevit.
"""

import os
import time

try:
    from lowlife import export_rename
except Exception:
    export_rename = None


# Как часто (не чаще) обрабатывать тик Idling, сек.
SCAN_INTERVAL = 2.0
# Считаем файл «только что выгруженным», если он моложе этого, сек.
FRESH_SECONDS = 1800.0
# Пауза между обработанными тиками больше этого = Idling был подавлен
# (открыт модальный диалог — например окно экспорта ModPlus — либо шла
# долгая команда). Момент закрытия такого диалога и есть сигнал
# «экспорт, возможно, только что закончился» → проверить папку.
GAP_THRESHOLD = 5.0
# Не срабатывать повторно чаще, чем раз в столько секунд.
REFIRE_GUARD = 20.0
# Пользователь ответил «Нет» по папке — не спрашивать про неё столько секунд.
DECLINE_QUIET = 600.0


_installed = False
_handler = None          # держим ссылку на делегат, иначе GC его заберёт
_last_scan = 0.0
_prev_tick = 0.0
_last_fire = 0.0
_seen_hwnds = set()
_declined = {}           # dir_key -> время отказа
_busy = False


def install(host_app):
    """Подписаться на Idling один раз. ``host_app`` — ``__revit__`` из
    startup.py (UIControlledApplication) либо любой объект с событием
    ``Idling``."""
    global _installed, _handler

    if _installed or export_rename is None or host_app is None:
        return

    try:
        cfg = export_rename.load_config()
    except Exception:
        return
    if not cfg.get("watch_explorer", True):
        return

    # Уже открытые сейчас окна Проводника не считаем «новыми».
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
        return

    _handler = _on_idling
    _installed = True


def _tick():
    global _last_scan, _prev_tick, _last_fire, _busy

    if _busy or export_rename is None:
        return

    now = time.time()
    if now - _last_scan < SCAN_INTERVAL:
        return

    gap = now - _last_scan if _last_scan else 0.0
    _last_scan = now

    # Idling был подавлен дольше обычного → закрылся модальный диалог
    # (окно экспорта ModPlus?) или отработала долгая команда.
    dialog_just_closed = _prev_tick and gap >= GAP_THRESHOLD
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

    if now - _last_fire < REFIRE_GUARD:
        # обновить набор окон, но ничего не предлагать
        _seen_hwnds.clear()
        _seen_hwnds.update(h for h, _p in windows)
        return

    current_hwnds = set()
    candidates = []  # (dir_key, path, label)

    for hwnd, path in windows:
        current_hwnds.add(hwnd)
        if hwnd in _seen_hwnds:
            continue
        key = _dir_key(path)
        if key and _fresh_and_not_declined(key, path, cfg, now):
            candidates.append((key, path, u"Открыта папка: {}".format(path)))

    _seen_hwnds.clear()
    _seen_hwnds.update(current_hwnds)

    # После закрытия модального диалога — ещё и прошлая папка выгрузки:
    # ModPlus мог не открыть Проводник, но экспорт часто идёт в ту же папку.
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
            _last_fire = time.time()
            try:
                res = export_rename.rename_folder_interactive(
                    path, cfg=cfg, source_label=label, quiet_if_empty=True,
                )
            except Exception:
                res = None
            if res == "declined":
                _declined[key] = time.time()
            elif res == "renamed":
                _declined.pop(key, None)
    finally:
        _busy = False


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
