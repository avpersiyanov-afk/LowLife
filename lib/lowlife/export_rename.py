# -*- coding: utf-8 -*-
"""
Переименование файлов выгрузки после экспорта из Revit (ModPlus «Экспорт»
и т.п.): в имени каждого выгруженного файла заменяет одну подстроку на
другую — по умолчанию «0000» → «000».

Зачем: два листа должны идти под ОДНИМ номером, но с разными именами.
ModPlus/Revit собирает имя файла из «номер листа + имя листа», поэтому
одинаковый номер даёт конфликт имён. Обходной приём пользователя — дать
листам разные номера («0000» и «000») и после выгрузки привести «0000»
к «000», чтобы на диске оба файла отличались только именем листа.

Как это запускается:
- кнопка ``Tools.panel/RenameExportFiles`` — :func:`run_after_export`
  вручную (обычный клик) и настройки (Shift+клик, :func:`configure`);
- слежение за Проводником (``lib/lowlife/export_watcher.py`` из
  ``startup.py``): когда ModPlus в конце экспорта открывает папку
  выгрузки, watcher замечает новое окно Проводника со свежими файлами
  ``from_token`` и вызывает :func:`rename_folder_interactive` по этой
  папке. Ключ ``watch_explorer``;
- автозапуск из pyRevit-хука по команде — TODO: нужен точный
  идентификатор команды ModPlus для ``hooks/command-after-exec[<id>].py``
  (хук без ``[id]`` в имени эта сборка pyRevit не регистрирует). Способ
  достать id — в ``docs/rename-export-files.md``. Модуль готов:
  :func:`command_matches` и ключи ``enabled`` / ``trigger_substrings``.

Полуавтомат: определить папку, куда ModPlus сложил файлы, программно
нельзя (плагина в этой среде нет, его конфиг не читаем), поэтому
:func:`run_after_export` спрашивает папку — с уже подставленным прошлым
путём, подтверждается Enter'ом — и только переименовывает файлы. Ничего
в модели Revit не меняется, транзакция не нужна.

Настройки лежат в обычном JSON-файле
``%APPDATA%\\pyRevit\\LowLifeExportRename_settings.json`` — тот же подход,
что у ``scs_settings.py`` (не ``pyrevit.script.get_config()``).
"""

import os
import io
import json

try:
    from pyrevit import forms
except Exception:
    forms = None


SETTINGS_FILE_NAME = "LowLifeExportRename_settings.json"

DEFAULTS = {
    # автозапуск из хука после подходящей команды
    "enabled": True,
    # подстроки (регистр не важен) для сопоставления с идентификатором
    # выполненной команды Revit; пустой список — хук не срабатывает
    "trigger_substrings": [u"modplus"],
    # следить за открытием нового окна Проводника (export_watcher, startup.py):
    # окно на папке со свежими файлами «from_token» → предложить переименовать
    "watch_explorer": True,
    # что на что менять в имени файла (меняются ВСЕ вхождения)
    "from_token": u"0000",
    "to_token": u"000",
    # какие файлы трогаем (по расширению, регистр не важен)
    "extensions": [u".dwg", u".pdf"],
    # заходить ли в подпапки выбранной папки
    "recursive": True,
    # последняя использованная папка выгрузки (подставляется в диалоге)
    "last_folder": u"",
    # последний идентификатор команды, на котором сработал хук
    # (справочно, для настройки триггера)
    "last_seen_command": u"",
}


def _settings_file_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(appdata, "pyRevit")

    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except Exception:
            pass

    return os.path.join(folder, SETTINGS_FILE_NAME)


def _read_all():
    path = _settings_file_path()

    if not os.path.isfile(path):
        return {}

    try:
        with io.open(path, "r", encoding="utf-8") as f:
            text = f.read()
        if not text.strip():
            return {}
        return json.loads(text)
    except Exception:
        return {}


def _write_all(data):
    path = _settings_file_path()

    try:
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(unicode(json.dumps(data, ensure_ascii=False,
                                       indent=2, sort_keys=True)))
        return True
    except Exception:
        if forms is not None:
            forms.alert(
                u"Не удалось сохранить настройки переименования выгрузки "
                u"в файл:\n{}".format(path)
            )
        return False


def load_config():
    """Настройки из JSON-файла поверх :data:`DEFAULTS`."""
    cfg = dict(DEFAULTS)
    saved = _read_all()
    if isinstance(saved, dict):
        for key in DEFAULTS:
            if key in saved:
                cfg[key] = saved[key]

    # мягкая нормализация типов на случай ручной правки файла
    if not isinstance(cfg["trigger_substrings"], list):
        cfg["trigger_substrings"] = [cfg["trigger_substrings"]]
    cfg["trigger_substrings"] = [unicode(s).strip()
                                 for s in cfg["trigger_substrings"]
                                 if unicode(s).strip()]
    if not isinstance(cfg["extensions"], list):
        cfg["extensions"] = [cfg["extensions"]]
    cfg["extensions"] = [_norm_ext(e) for e in cfg["extensions"] if _norm_ext(e)]
    cfg["enabled"] = bool(cfg["enabled"])
    cfg["watch_explorer"] = bool(cfg["watch_explorer"])
    cfg["recursive"] = bool(cfg["recursive"])
    cfg["from_token"] = unicode(cfg["from_token"])
    cfg["to_token"] = unicode(cfg["to_token"])
    cfg["last_folder"] = unicode(cfg["last_folder"] or u"")
    cfg["last_seen_command"] = unicode(cfg["last_seen_command"] or u"")
    return cfg


def save_config(cfg):
    data = _read_all()
    if not isinstance(data, dict):
        data = {}
    for key in DEFAULTS:
        if key in cfg:
            data[key] = cfg[key]
    return _write_all(data)


def _norm_ext(ext):
    ext = unicode(ext or u"").strip().lower()
    if not ext:
        return u""
    if not ext.startswith(u"."):
        ext = u"." + ext
    return ext


def command_matches(command_id_text, cfg=None):
    """True, если текст идентификатора команды содержит любую из
    ``trigger_substrings`` (регистр не важен)."""
    if cfg is None:
        cfg = load_config()
    subs = cfg.get("trigger_substrings") or []
    if not subs or not command_id_text:
        return False
    low = unicode(command_id_text).lower()
    return any(s.lower() in low for s in subs)


# --- собственно переименование -------------------------------------------------

def plan_renames(folder, cfg=None):
    """Список ``(src_path, dst_path, status)`` для файлов в ``folder``.

    ``status``:
      - ``"ok"``       — можно переименовать;
      - ``"collision"``  — целевое имя уже занято другим файлом, пропуск.

    Файлы без ``from_token`` в имени и с неподходящим расширением в список
    не попадают. При ``cfg["recursive"]`` обходятся и подпапки.
    """
    if cfg is None:
        cfg = load_config()

    frm = cfg["from_token"]
    to = cfg["to_token"]
    exts = cfg["extensions"]
    recursive = cfg["recursive"]

    plans = []
    if not frm or frm == to:
        return plans
    if not folder or not os.path.isdir(folder):
        return plans

    if recursive:
        walk = os.walk(folder)
    else:
        walk = [(folder, [], [n for n in os.listdir(folder)
                              if os.path.isfile(os.path.join(folder, n))])]

    for root, _dirs, files in walk:
        for name in files:
            stem, ext = os.path.splitext(name)
            if exts and ext.lower() not in exts:
                continue
            if frm not in name:
                continue
            new_name = name.replace(frm, to)
            if new_name == name:
                continue
            src = os.path.join(root, name)
            dst = os.path.join(root, new_name)
            if os.path.exists(dst):
                plans.append((src, dst, "collision"))
            else:
                plans.append((src, dst, "ok"))

    plans.sort(key=lambda p: p[0].lower())
    return plans


def apply_renames(plans):
    """Переименовывает пары со статусом ``"ok"``.

    Возвращает ``(renamed, errors)`` — число успешных и список
    ``(src, dst, message)``.
    """
    renamed = 0
    errors = []
    for src, dst, status in plans:
        if status != "ok":
            continue
        try:
            os.rename(src, dst)
            renamed += 1
        except Exception as exc:
            errors.append((src, dst, unicode(exc)))
    return renamed, errors


# --- интерактивные сценарии ---------------------------------------------------

def _toast(msg, title=u"Переименование выгрузки"):
    if forms is None:
        return
    try:
        forms.toast(msg, title=title)
    except Exception:
        try:
            forms.alert(msg, title=title)
        except Exception:
            pass


def _ask_folder(cfg):
    """Папка выгрузки: подтвердить прошлую (Enter) или выбрать другую."""
    last = cfg.get("last_folder") or u""
    if forms is None:
        return last if last and os.path.isdir(last) else None

    if last and os.path.isdir(last):
        choice = forms.alert(
            u"Папка выгрузки:\n{}\n\n"
            u"Переименовать в ней «{}» → «{}»?".format(
                last, cfg["from_token"], cfg["to_token"]),
            title=u"Переименование выгрузки",
            options=[u"Да, эта папка", u"Выбрать другую…", u"Отмена"],
        )
        if choice == u"Да, эта папка":
            return last
        if choice == u"Выбрать другую…":
            pass
        else:
            return None

    try:
        picked = forms.pick_folder(title=u"Папка, куда ModPlus сложил файлы")
    except TypeError:
        picked = forms.pick_folder()

    if picked and os.path.isdir(picked):
        return picked
    return None


def rename_folder_interactive(folder, cfg=None, source_label=None,
                              quiet_if_empty=False):
    """Показать план по готовой папке, спросить подтверждение, переименовать.

    ``source_label`` — строка для показа в диалоге (id команды / «Проводник:
    …»). ``quiet_if_empty`` — не всплывать, если переименовывать нечего
    (для авто-режимов, чтобы не мешать).
    """
    if cfg is None:
        cfg = load_config()
    if not folder or not os.path.isdir(folder):
        return

    plans = plan_renames(folder, cfg)
    ok = [p for p in plans if p[2] == "ok"]
    collisions = [p for p in plans if p[2] == "collision"]

    if not ok and not collisions:
        if not quiet_if_empty:
            _toast(u"Файлов с «{}» в имени не найдено:\n{}".format(
                cfg["from_token"], folder))
        return

    sample = u"\n".join(u"  {}  →  {}".format(
        os.path.basename(s), os.path.basename(d)) for s, d, _ in ok[:12])
    if len(ok) > 12:
        sample += u"\n  … ещё {}".format(len(ok) - 12)

    msg = u"Папка: {}\n\n".format(folder)
    if source_label:
        msg += u"{}\n\n".format(source_label)
    msg += u"Переименовать «{}» → «{}» в {} файле(ах):\n{}".format(
        cfg["from_token"], cfg["to_token"], len(ok), sample or u"  —")
    if collisions:
        msg += u"\n\nПропущу {} — целевое имя уже занято:\n{}".format(
            len(collisions),
            u"\n".join(u"  {}".format(os.path.basename(s))
                       for s, _d, _ in collisions[:12]))

    if not ok:
        if not quiet_if_empty:
            _toast(msg)
        return

    if forms is not None and not forms.alert(msg, title=u"Переименование выгрузки",
                                             yes=True, no=True):
        return

    renamed, errors = apply_renames(ok)
    save_config({"last_folder": folder})

    result = u"Переименовано: {}".format(renamed)
    if collisions:
        result += u"\nПропущено (имя занято): {}".format(len(collisions))
    if errors:
        result += u"\nОшибок: {}\n{}".format(
            len(errors),
            u"\n".join(u"  {} — {}".format(os.path.basename(s), m)
                       for s, _d, m in errors[:8]))
    _toast(result)


def run_after_export(command_id_text=None, cfg=None):
    """Основной сценарий кнопки/хука: спросить папку, показать план,
    переименовать. ``command_id_text`` — только для показа/записи."""
    if cfg is None:
        cfg = load_config()

    if command_id_text:
        save_config({"last_seen_command": unicode(command_id_text)})

    folder = _ask_folder(cfg)
    if not folder:
        return

    label = u"Команда: {}".format(command_id_text) if command_id_text else None
    rename_folder_interactive(folder, cfg=cfg, source_label=label)


def configure():
    """Окно настроек (Shift+клик по кнопке)."""
    if forms is None:
        return
    cfg = load_config()

    watch_explorer = forms.alert(
        u"Следить за открытием папки выгрузки в Проводнике и сразу "
        u"предлагать переименование?\n\n"
        u"Работает всю сессию Revit (startup.py). Сейчас: {}".format(
            u"да" if cfg["watch_explorer"] else u"нет"),
        title=u"Переименование выгрузки — настройки",
        yes=True, no=True,
    )

    enabled = forms.alert(
        u"Запускать переименование автоматически после команды ModPlus "
        u"(нужен id команды, см. docs/rename-export-files.md)?\n\n"
        u"Сейчас: {}".format(u"да" if cfg["enabled"] else u"нет"),
        title=u"Переименование выгрузки — настройки",
        yes=True, no=True,
    )

    hint = u""
    if cfg.get("last_seen_command"):
        hint = u"\n\nПоследняя пойманная команда:\n{}".format(cfg["last_seen_command"])
    subs = forms.ask_for_string(
        default=u", ".join(cfg["trigger_substrings"]),
        prompt=u"Подстроки идентификатора команды-триггера (через запятую, "
               u"регистр не важен). Пусто — авто-запуск выключен.{}".format(hint),
        title=u"Триггер",
    )
    if subs is None:
        return
    trigger_substrings = [s.strip() for s in subs.split(u",") if s.strip()]

    frm = forms.ask_for_string(
        default=cfg["from_token"],
        prompt=u"Что искать в имени файла:",
        title=u"Заменять",
    )
    if frm is None:
        return
    to = forms.ask_for_string(
        default=cfg["to_token"],
        prompt=u"На что заменять (меняются все вхождения):",
        title=u"Заменять",
    )
    if to is None:
        return

    exts = forms.ask_for_string(
        default=u", ".join(cfg["extensions"]),
        prompt=u"Расширения файлов через запятую (пусто — любые):",
        title=u"Файлы",
    )
    if exts is None:
        return
    extensions = [_norm_ext(e) for e in exts.split(u",") if _norm_ext(e)]

    recursive = forms.alert(
        u"Заходить в подпапки выбранной папки?\n\nСейчас: {}".format(
            u"да" if cfg["recursive"] else u"нет"),
        title=u"Подпапки",
        yes=True, no=True,
    )

    cfg.update({
        "watch_explorer": bool(watch_explorer),
        "enabled": bool(enabled),
        "trigger_substrings": trigger_substrings,
        "from_token": frm,
        "to_token": to,
        "extensions": extensions,
        "recursive": bool(recursive),
    })
    if save_config(cfg):
        forms.alert(
            u"Сохранено.\n\nСлежение за Проводником: {}\nАвтозапуск по команде: "
            u"{}\nТриггер: {}\nЗамена: «{}» → «{}»\nФайлы: {}\nПодпапки: {}\n\n"
            u"Слежение за Проводником применится после перезагрузки pyRevit.".format(
                u"да" if cfg["watch_explorer"] else u"нет",
                u"да" if cfg["enabled"] else u"нет",
                u", ".join(trigger_substrings) or u"—",
                cfg["from_token"], cfg["to_token"],
                u", ".join(extensions) or u"любые",
                u"да" if cfg["recursive"] else u"нет"),
            title=u"Переименование выгрузки — настройки",
        )
