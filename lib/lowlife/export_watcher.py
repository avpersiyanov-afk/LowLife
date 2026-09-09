# -*- coding: utf-8 -*-
"""
Автозапуск переименования выгрузки после экспорта ModPlus.

``install(host_app)`` вызывается из ``startup.py``, ``hooks/doc-opened.py``
и из скриптов кнопок (``ensure_installed``) — что-нибудь да сработает;
дубли отсекает словарь в ``AppDomain.CurrentDomain`` (общий на весь
процесс Revit; у каждого движка pyRevit свой ``sys``, поэтому sys-глобал
не годился — каждый движок подписывался на статический ItemExecuted и
запускал свой поллер, окно спрашивало дважды).

Подписка на ``Autodesk.Windows.ComponentManager.ItemExecuted``: клик по
кнопке ленты, чьи ``Id``/``Text``/``Cookie`` подходят под
``trigger_substrings`` (по умолчанию ``mprSheetExport`` — «Экспорт листов»
ModPlus, нужен ``enabled``), СРАЗУ (ещё до открытия модального окна
экспорта) запускает фоновый STA-поток ``_poll_and_rename``. Тот раз в
``POLL_INTERVAL`` сек смотрит подпапки ``export_root`` / папки рядом с
``last_folder``, ждёт появления новой (созданной после клика) и её
«стабилизации» (``_folder_sig`` не меняется цикл — ModPlus дописал), затем
``plan_renames`` → WinForms ``MessageBox`` да/нет → ``apply_renames`` →
итоговый ``MessageBox``. Поиск идёт ПАРАЛЛЕЛЬНО экспорту, поэтому окно о
переименовании появляется почти сразу после закрытия окна ModPlus. Вся
работа с файлами и диалоги — вне UI-потока Revit (на сетевой шаре секунды;
на UI-потоке подвешивало Revit).

Idling-подписка осталась только для снятия зависшего флага
(``WORKER_STUCK_AFTER``) — логику переименования она больше не трогает.

Аварийный выключатель: файл ``%APPDATA%\\pyRevit\\LowLifeExportRename_OFF``
— ``install`` тогда ничего не делает. Штатно — ``watch_explorer`` в
настройках кнопки. Весь ход — в
``%APPDATA%\\pyRevit\\LowLifeExportRename_watcher.log``.
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


# Сколько секунд после клика по кнопке экспорта фоновый поллер ждёт папку
# выгрузки, прежде чем сдаться (и спросить папку вручную).
ARM_WINDOW = 900.0

LOG_NAME = "LowLifeExportRename_watcher.log"
OFF_NAME = "LowLifeExportRename_OFF"
_MAX_LOG_BYTES = 200 * 1024

# Состояние должно быть общим для ВСЕГО процесса Revit, а не для одного
# движка pyRevit: у каждого движка (startup.py / хук / кнопка / clean
# engine) — свой sys, поэтому sys-глобал НЕ годится (иначе каждый движок
# подпишется на статический ItemExecuted и запустит свой поллер — окно
# спрашивает дважды). Храним в AppDomain.CurrentDomain (один на процесс).
_SYS_KEY = "LowLife_ExportWatcher_State"
_PG_DEFAULTS = {
    "idling_installed": False, "item_installed": False,
    "idling_host": None, "idling_delegate": None, "item_delegate": None,
    "worker_running": False, "worker_started": 0.0,
}
_PG_FALLBACK = {}

_ticks = 0
_ie_seen = 0
# если фоновый поток завис/умер — через столько секунд снять флаг
WORKER_STUCK_AFTER = 600.0


def _pg():
    """Словарь состояния, общий на весь процесс Revit (через
    ``AppDomain.CurrentDomain``, а не sys — sys у каждого движка pyRevit
    свой). Защита от двойных подписок и двойного поллера."""
    try:
        from System import AppDomain
        dom = AppDomain.CurrentDomain
        d = dom.GetData(_SYS_KEY)
        if d is None:
            d = dict(_PG_DEFAULTS)
            dom.SetData(_SYS_KEY, d)
    except Exception:
        d = _PG_FALLBACK
    for k, v in _PG_DEFAULTS.items():
        if k not in d:
            d[k] = v
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


def _lock_path():
    return os.path.join(_appdata_pyrevit(), "LowLifeExportRename_worker.lock")


def _acquire_lock():
    """Атомарный файловый мьютекс поллера — на случай, если два движка
    pyRevit всё же попытаются стартовать одновременно. True — захватили."""
    path = _lock_path()
    try:
        if os.path.isfile(path) and \
                time.time() - os.path.getmtime(path) > WORKER_STUCK_AFTER:
            os.remove(path)  # протухший
    except Exception:
        pass
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except Exception:
        return False
    try:
        os.write(fd, str(int(time.time())).encode("ascii"))
    except Exception:
        pass
    try:
        os.close(fd)
    except Exception:
        pass
    return True


def _release_lock():
    try:
        os.remove(_lock_path())
    except Exception:
        pass


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
        global _ie_seen
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
            _log(u"ItemExecuted: ВЗВОД по «{}» → фоновое ожидание выгрузки".format(
                blob[:120]))
            # запускаем фоновый поллер ПРЯМО СЕЙЧАС (до открытия модального
            # окна экспорта) — поиск папки идёт параллельно самому экспорту,
            # поэтому окно о переименовании появляется почти сразу после него.
            _start_poller(cfg, time.time())
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
    """Idling больше не запускает переименование (это делает фоновый поллер
    из обработчика ItemExecuted). Здесь только снятие зависшего флага."""
    global _ticks
    _ticks += 1
    pg = _pg()
    if pg.get("worker_running") and \
            time.time() - pg.get("worker_started", 0) > WORKER_STUCK_AFTER:
        _log(u"фоновый поток завис ({}с) — снимаю флаг".format(WORKER_STUCK_AFTER))
        pg["worker_running"] = False


def _start_poller(cfg, armed_at):
    """Запустить фоновый STA-поток, который дождётся папки выгрузки и
    переименует. Двойной запуск отсекают: pg['worker_running'] (в пределах
    процесса) + файловый мьютекс _acquire_lock (между движками pyRevit)."""
    pg = _pg()
    if pg.get("worker_running"):
        _log(u"poller: уже работает (pg) — второй не запускаю")
        return
    if not _acquire_lock():
        _log(u"poller: уже запущен (lock-файл) — второй не запускаю")
        return
    pg["worker_running"] = True
    pg["worker_started"] = time.time()

    def _done():
        _pg()["worker_running"] = False
        _release_lock()

    def _run():
        try:
            _poll_and_rename(cfg, armed_at)
        except Exception:
            _log(_exc(u"_poll_and_rename упал"))
        finally:
            _done()

    try:
        from System.Threading import Thread, ThreadStart, ApartmentState
        t = Thread(ThreadStart(_run))
        t.IsBackground = True
        try:
            t.SetApartmentState(ApartmentState.STA)
        except Exception:
            pass
        t.Start()
    except Exception:
        _log(_exc(u"poller: поток не запустился — синхронно"))
        try:
            _poll_and_rename(cfg, armed_at)
        finally:
            _done()


def _msgbox(text, title, yesno=False):
    """WinForms MessageBox — работает из фонового потока, не блокирует UI
    Revit. Возвращает True/False для yesno, иначе None."""
    try:
        import clr
        clr.AddReference("System.Windows.Forms")
        from System.Windows.Forms import (
            MessageBox, MessageBoxButtons, MessageBoxIcon,
            MessageBoxDefaultButton, MessageBoxOptions, DialogResult)
        opts = MessageBoxOptions.DefaultDesktopOnly  # показать поверх, без владельца
        if yesno:
            r = MessageBox.Show(text, title, MessageBoxButtons.YesNo,
                                MessageBoxIcon.Question,
                                MessageBoxDefaultButton.Button1, opts)
            return r == DialogResult.Yes
        MessageBox.Show(text, title, MessageBoxButtons.OK,
                        MessageBoxIcon.Information,
                        MessageBoxDefaultButton.Button1, opts)
        return None
    except Exception:
        _log(_exc(u"_msgbox упал"))
        return None


def _pick_folder(start):
    try:
        import clr
        clr.AddReference("System.Windows.Forms")
        from System.Windows.Forms import FolderBrowserDialog, DialogResult
        dlg = FolderBrowserDialog()
        dlg.Description = u"Папка, куда ModPlus сложил файлы"
        if start and os.path.isdir(start):
            dlg.SelectedPath = start
        if dlg.ShowDialog() == DialogResult.OK and os.path.isdir(dlg.SelectedPath):
            return dlg.SelectedPath
    except Exception:
        _log(_exc(u"_pick_folder упал"))
    return None


POLL_INTERVAL = 2.0        # как часто фон опрашивает папку выгрузки, сек
NEW_FOLDER_GRACE = 20.0    # подпапка «этого экспорта» — не старше клика минус это
STABLE_CYCLES = 3          # столько опросов подряд без изменений = ModPlus дописал
MIN_SETTLE = 8.0           # но не раньше стольких секунд с появления папки


def _bases_to_watch(cfg):
    """Папки, в подпапках которых ищем результат экспорта."""
    out = []
    root = (cfg.get("export_root") or u"").strip()
    if root and os.path.isdir(root):
        out.append(root)
    last = (cfg.get("last_folder") or u"").strip()
    if last:
        parent = os.path.dirname(last.rstrip(u"\\/"))
        if parent and os.path.isdir(parent) and parent not in out:
            out.append(parent)
    return out


def _newest_subdir_since(bases, min_mtime):
    """Самая свежая подпапка 1-го уровня среди bases, если она не старше
    ``min_mtime``. Только listdir + stat на подпапку — дёшево."""
    best = None  # (mtime, path)
    for base in bases:
        try:
            names = os.listdir(base)
        except Exception:
            continue
        for name in names[:200]:
            p = os.path.join(base, name)
            try:
                if not os.path.isdir(p):
                    continue
                m = os.path.getmtime(p)
            except Exception:
                continue
            if best is None or m > best[0]:
                best = (m, p)
    if best and best[0] >= min_mtime:
        return best[1]
    return None


def _folder_sig(folder, cfg):
    """Быстрый «отпечаток» папки: mtime + число подходящих (`from_token` +
    расширение) и вообще всех файлов, в самой папке и в подпапках 1-го
    уровня. Возвращает ``(отпечаток, match_total, any_total)``:
    ``any_total`` > 0 = экспорт что-то положил; сравнение целых отпечатков
    = «папка перестала меняться»."""
    frm = cfg.get("from_token") or u"0000"
    exts = tuple((e or u"").lower() for e in (cfg.get("extensions") or ()))

    def _counts(d):
        match = any_n = 0
        try:
            for name in os.listdir(d)[:500]:
                if not os.path.isfile(os.path.join(d, name)):
                    continue
                any_n += 1
                if frm not in name:
                    continue
                if exts and os.path.splitext(name)[1].lower() not in exts:
                    continue
                match += 1
        except Exception:
            pass
        return match, any_n

    parts = []
    try:
        m, a = _counts(folder)
        parts.append((u"", os.path.getmtime(folder), m, a))
    except Exception:
        parts.append((u"", 0, 0, 0))
    try:
        for name in sorted(os.listdir(folder))[:20]:
            sub = os.path.join(folder, name)
            try:
                if os.path.isdir(sub):
                    m, a = _counts(sub)
                    parts.append((name, os.path.getmtime(sub), m, a))
            except Exception:
                continue
    except Exception:
        pass
    return (tuple(parts), sum(p[2] for p in parts), sum(p[3] for p in parts))


def _poll_and_rename(cfg, armed_at):
    """Фоновый поток: дождаться, пока ModPlus допишет папку выгрузки, и
    переименовать. Никакого Revit API — только os.* и WinForms-диалоги."""
    bases = _bases_to_watch(cfg)
    _log(u"poll: слежу за {}".format(bases or u"— (нет ни export_root, ни last_folder)"))
    deadline = armed_at + ARM_WINDOW
    min_mtime = armed_at - NEW_FOLDER_GRACE

    prev_sig = None
    stable = 0
    chosen = None
    folder = None
    folder_seen_at = 0.0
    last_rescan = 0.0
    hb = time.time()

    while time.time() < deadline:
        # полный обзор подпапок — только пока папка не найдена, потом раз в 10с
        if bases and (folder is None or time.time() - last_rescan > 10):
            last_rescan = time.time()
            nf = _newest_subdir_since(bases, min_mtime)
            if nf and nf != folder:
                folder = nf
                folder_seen_at = time.time()
                prev_sig = None
                stable = 0
                _log(u"poll: вижу папку {}".format(folder))

        if folder:
            sig = _folder_sig(folder, cfg)
            # экспорт что-то положил (any>0) И папка перестала меняться
            if sig[2] > 0 and sig == prev_sig:
                stable += 1
                if stable >= STABLE_CYCLES and \
                        time.time() - folder_seen_at >= MIN_SETTLE:
                    chosen = folder
                    break
            else:
                stable = 0
            prev_sig = sig

        if time.time() - hb >= 20:
            hb = time.time()
            _log(u"poll: жду… folder={} с«{}»={} всего={}".format(
                folder or u"—", cfg.get("from_token"),
                prev_sig[1] if prev_sig else 0,
                prev_sig[2] if prev_sig else 0))
        time.sleep(POLL_INTERVAL)

    if not chosen:
        chosen = folder or (_newest_subdir_since(bases, min_mtime) if bases else None)
    if not chosen:
        _log(u"poll: папку выгрузки не нашёл за {}с — спрошу вручную".format(
            int(ARM_WINDOW)))
        chosen = _pick_folder((cfg.get("export_root")
                               or cfg.get("last_folder") or u"").strip())
        if not chosen:
            _log(u"poll: папка не выбрана — выхожу")
            return

    _log(u"poll: папка выгрузки → {}".format(chosen))
    _do_rename(chosen, cfg)


def _do_rename(folder, cfg):
    try:
        plans = export_rename.plan_renames(folder, cfg)
    except Exception:
        _log(_exc(u"_do_rename: plan_renames упал"))
        return
    ok = [p for p in plans if p[2] == "ok"]
    coll = [p for p in plans if p[2] == "collision"]
    _log(u"_do_rename: {} — ok={} collision={}".format(folder, len(ok), len(coll)))
    for s, d, _st in coll:
        _log(u"  collision: {}  ->  {}".format(os.path.basename(s), os.path.basename(d)))

    if not ok and not coll:
        _log(u"_do_rename: файлов с «{}» нет".format(cfg["from_token"]))
        if cfg.get("notify_nothing", False):
            _msgbox(u"Папка: {}\n\nВ выгрузке нет файлов с «{}» — "
                    u"переименовывать нечего.".format(folder, cfg["from_token"]),
                    u"Переименование выгрузки")
        return

    if not ok:
        clist = u"\n".join(u"  {}".format(os.path.basename(s)) for s, _d, _ in coll[:20])
        _msgbox(
            u"Папка: {}\n\nПереименовать нечего: у всех {} файла(ов) с «{}» "
            u"целевое имя «{}…» уже занято другим файлом в этой папке "
            u"(перезаписывать не стал — потеряется второй лист):\n{}\n\n"
            u"Если это два РАЗНЫХ листа — дайте им разные имена листа.".format(
                folder, len(coll), cfg["from_token"], cfg["to_token"], clist),
            u"Переименование выгрузки")
        return

    sample = u"\n".join(u"  {}  →  {}".format(
        os.path.basename(s), os.path.basename(d)) for s, d, _ in ok[:15])
    if len(ok) > 15:
        sample += u"\n  … ещё {}".format(len(ok) - 15)
    msg = u"Папка: {}\n\nПереименовать «{}» → «{}» в {} файле(ах)?\n{}".format(
        folder, cfg["from_token"], cfg["to_token"], len(ok), sample)
    if coll:
        msg += u"\n\nПропущу {} (целевое имя занято).".format(len(coll))

    if not _msgbox(msg, u"Переименование выгрузки", yesno=True):
        _log(u"_do_rename: пользователь отказался")
        return

    # пока висел диалог, файлы могли уже переименоваться (другой запуск /
    # ручная кнопка) — берём только то, что всё ещё валидно
    try:
        fresh_ok = [p for p in export_rename.plan_renames(folder, cfg)
                    if p[2] == "ok"]
    except Exception:
        fresh_ok = ok
    if not fresh_ok:
        _log(u"_do_rename: после диалога переименовывать уже нечего")
        return

    renamed, errors = export_rename.apply_renames(fresh_ok)
    try:
        export_rename.save_config({"last_folder": folder})
    except Exception:
        pass
    _log(u"_do_rename: переименовано {} ошибок {}".format(renamed, len(errors)))
    res = u"Переименовано: {}".format(renamed)
    if coll:
        res += u"\nПропущено (имя занято): {}".format(len(coll))
    if errors:
        res += u"\nОшибок: {}".format(len(errors))
    _msgbox(res, u"Переименование выгрузки")


def status_text():
    """Сводка состояния — для диагностической кнопки. Всё в int/строках:
    IronPython 2.7 роняет ``{:.0f}`` на int («Precision not allowed in
    integer format specifier»)."""
    pg = _pg()
    lines = [
        u"export_watcher (поллер из ItemExecuted, без Idling-логики):",
        u"  Idling подписан={}  ItemExecuted подписан={}".format(
            pg.get("idling_installed"), pg.get("item_installed")),
        u"  тиков Idling={}  кликов по ленте залогировано={}".format(
            _ticks, _ie_seen),
        u"  фоновый поллер работает={}".format(pg.get("worker_running")),
        u"  файл-выключатель {}: {}".format(
            OFF_NAME, u"ЕСТЬ (авто выкл)" if os.path.isfile(_off_file()) else u"нет"),
    ]
    try:
        cfg = export_rename.load_config()
        lines.append(
            u"  cfg: watch_explorer={} enabled={} trigger={}".format(
                cfg.get("watch_explorer"), cfg.get("enabled"),
                cfg.get("trigger_substrings")))
        lines.append(u"  export_root={!r}".format(cfg.get("export_root")))
        lines.append(u"  last_folder={!r}".format(cfg.get("last_folder")))
    except Exception:
        lines.append(u"  cfg: не прочитать")
    lines.append(u"  лог: {}".format(_log_path()))
    return u"\n".join(lines)
