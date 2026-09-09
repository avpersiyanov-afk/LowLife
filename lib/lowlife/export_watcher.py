# -*- coding: utf-8 -*-
"""
Слежение за открытием папки выгрузки в Проводнике.

ModPlus в конце экспорта листов открывает папку с результатом в Проводнике
Windows. Точную папку определить программно нельзя (плагина в среде
разработки нет, конфиг его не читаем), поймать команду ModPlus хуком тоже
не вышло (см. ``docs/rename-export-files.md``), поэтому ловим момент по
косвенному признаку — появлению нового окна Проводника.

``install(host_app)`` вызывается один раз из ``startup.py`` расширения. Он
подписывается на ``UIApplication.Idling`` (Revit сам дёргает его в паузах
между действиями пользователя — тот же механизм, что в
``route_preview.schedule_preview_cleanup``). Не чаще раза в
``SCAN_INTERVAL`` секунд обработчик перечисляет открытые окна Проводника
через COM ``Shell.Application`` и, если появилось НОВОЕ окно на папке, где
есть свежие (моложе ``FRESH_SECONDS``) файлы с ``from_token`` в имени,
вызывает ``export_rename.rename_folder_interactive`` по этой папке.

Ограничения (осознанные):
- работает всю сессию Revit; лёгкий COM-поллинг окон;
- сработает на ЛЮБОМ новом окне Проводника, если там окажутся свежие
  подходящие файлы (фильтр по свежести + «не спрашивать дважды про ту же
  папку» это почти исключает);
- Проводник с вкладками (Win11): если папку откроют новой вкладкой в
  существующем окне, а не отдельным окном — момент не поймается;
- отключается: Shift+клик по кнопке «Переименование выгрузки» → «Следить
  за открытием папки… : нет» (ключ ``watch_explorer``), применяется после
  перезагрузки pyRevit.
"""

import os
import time

try:
    from lowlife import export_rename
except Exception:
    export_rename = None


# Как часто (не чаще) перечислять окна Проводника, сек.
SCAN_INTERVAL = 2.0
# Считаем файл «только что выгруженным», если он моложе этого, сек.
FRESH_SECONDS = 1800.0


_installed = False
_handler = None          # держим ссылку на делегат, иначе GC его заберёт
_last_scan = 0.0
_seen_hwnds = set()
_handled_dirs = set()
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
    global _last_scan, _busy

    if _busy or export_rename is None:
        return

    now = time.time()
    if now - _last_scan < SCAN_INTERVAL:
        return
    _last_scan = now

    try:
        cfg = export_rename.load_config()
    except Exception:
        return
    if not cfg.get("watch_explorer", True):
        return

    try:
        windows = _explorer_windows()
    except Exception:
        return

    current_hwnds = set()
    fresh_dirs = []
    for hwnd, path in windows:
        current_hwnds.add(hwnd)
        if hwnd in _seen_hwnds:
            continue
        key = _dir_key(path)
        if key and key not in _handled_dirs and _has_fresh_match(path, cfg, now):
            fresh_dirs.append((key, path))

    # запомнить текущий набор окон (и убрать закрытые)
    _seen_hwnds.clear()
    _seen_hwnds.update(current_hwnds)

    if not fresh_dirs:
        return

    _busy = True
    try:
        for key, path in fresh_dirs:
            _handled_dirs.add(key)
            try:
                export_rename.rename_folder_interactive(
                    path, cfg=cfg,
                    source_label=u"Открыта папка: {}".format(path),
                    quiet_if_empty=True,
                )
            except Exception:
                pass
    finally:
        _busy = False


def _dir_key(path):
    try:
        return os.path.normcase(os.path.abspath(path))
    except Exception:
        return None


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
