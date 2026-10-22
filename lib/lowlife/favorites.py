# -*- coding: utf-8 -*-
"""«Мои панели»: свои панели пользователя из кнопок LowLife — обычные панели pyRevit.

Настройки (`%APPDATA%\\pyRevit\\LowLifeFavorites_settings.json`) — список панелей и их кнопок,
логика — `favorites_core`. Здесь — раскладка по папкам:

- панель — ячейка `LowLife.tab/MyPanel<N>.panel` (N — порядок панели, до `favorites_core.MAX_PANELS`);
  ячейки перечислены в `layout:` вкладки (pyRevit создаёт только перечисленные панели, а
  несуществующие пропускает), в git их нет (`.gitignore`) — у каждого пользователя свои;
- кнопка — копия папки исходной кнопки (скрипт, bundle.yaml, иконки, xaml) под именем
  `favorites_core.button_folder`: та же подпись, тот же Shift+клик и движок, настройки кнопки общие;
- темы ячейки не трогают (их нет в `panel_themes.THEMES`) — свои панели видны при любой теме.

Панели появляются на ленте после перезагрузки pyRevit (`reload_pyrevit`). `startup.py` при каждой
загрузке заново раскладывает копии (`restore_on_load`): после обновления LowLife в них новые скрипты.
"""

try:
    unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3
    unicode = str

import io
import os
import shutil

from lowlife import favorites_core, ribbon_catalog

TAB_NAME = u"LowLife"

_STORE = None


def _store():
    global _STORE
    if _STORE is None:
        from lowlife import settings_core
        _STORE = settings_core.JsonStore("LowLifeFavorites_settings.json", u"своих панелей", share=False)
    return _STORE


def load():
    return favorites_core.normalize(_store().read())


def save(data):
    """True — записано (иначе JsonStore уже показал ошибку)."""
    return _store().write(favorites_core.normalize(data))


def reserved_titles():
    """Подписи панелей самого LowLife — свою панель так называть нельзя."""
    titles = [title for title, _buttons in ribbon_catalog.list_panels()]
    return titles + [TAB_NAME]


# ---------------------------------------------------------------- папки

def tab_folder(root=None):
    return os.path.join(root or ribbon_catalog.extension_root(), ribbon_catalog.TAB_FOLDER)


def _same_file(a, b):
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        with io.open(a, "rb") as fa, io.open(b, "rb") as fb:
            return fa.read() == fb.read()
    except (IOError, OSError):
        return False


def _write_text(path, text):
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            if f.read() == text:
                return
    except (IOError, OSError, UnicodeDecodeError):
        pass
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _remove(path):
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.exists(path):
        try:
            os.remove(path)
        except (IOError, OSError):
            pass


def _mirror(src, dst):
    """dst — точная копия папки src; меняются только отличающиеся файлы (pyRevit не перечитывает
    лишнего, а занятые файлы не трогаются, если не изменились)."""
    if not os.path.isdir(dst):
        os.makedirs(dst)
    names = set(n for n in os.listdir(src) if n != u"__pycache__" and not n.endswith(u".pyc"))
    for name in os.listdir(dst):
        if name not in names:
            _remove(os.path.join(dst, name))
    for name in names:
        s, d = os.path.join(src, name), os.path.join(dst, name)
        if os.path.isdir(s):
            if os.path.exists(d) and not os.path.isdir(d):
                _remove(d)
            _mirror(s, d)
        elif not _same_file(s, d):
            if os.path.isdir(d):
                _remove(d)
            shutil.copy2(s, d)


def write_panels(data=None, root=None):
    """Раскладывает свои панели по ячейкам (data — по умолчанию сохранённые), лишние ячейки убирает.

    Возвращает (изменилось ли что-нибудь на диске — нужна перезагрузка pyRevit, список проблем)."""
    tab = tab_folder(root)
    entries = ribbon_catalog.list_buttons(root)
    panels, problems = favorites_core.plan(data if data is not None else load(), entries)
    before = _snapshot(tab)
    used = set()
    for slot, title, buttons in panels:
        folder = os.path.join(tab, slot + u".panel")
        used.add(slot + u".panel")
        if not os.path.isdir(folder):
            os.makedirs(folder)
        names = []
        keep = set([u"bundle.yaml"])
        for name, entry in buttons:
            ext = os.path.splitext(entry[u"folder"])[1]
            try:
                _mirror(entry[u"folder"], os.path.join(folder, name + ext))
                names.append(name)
                keep.add(name + ext)
            except (IOError, OSError) as ex:
                problems.append(u"«{}»: не удалось скопировать «{}» — {}".format(title, entry[u"title"], ex))
        for name in os.listdir(folder):
            if name not in keep:
                _remove(os.path.join(folder, name))
        _write_text(os.path.join(folder, u"bundle.yaml"), favorites_core.panel_bundle(title, names))
    for name in os.listdir(tab):
        if name.endswith(u".panel") and favorites_core.is_slot(name[:-len(u".panel")]) and name not in used:
            _remove(os.path.join(tab, name))
    return _snapshot(tab) != before, problems


def _snapshot(tab):
    """Отпечаток ячеек (пути, размеры, время изменения) — изменилось ли что-нибудь."""
    result = []
    for name in sorted(os.listdir(tab)):
        if not (name.endswith(u".panel") and favorites_core.is_slot(name[:-len(u".panel")])):
            continue
        for dirpath, dirnames, filenames in os.walk(os.path.join(tab, name)):
            dirnames.sort()
            for fname in sorted(filenames):
                path = os.path.join(dirpath, fname)
                try:
                    stat = os.stat(path)
                    result.append((path, stat.st_size, int(stat.st_mtime)))
                except OSError:
                    result.append((path, None, None))
    return result


def reload_pyrevit():
    """Перезагрузить pyRevit — как его кнопка «Reload»: только так новые панели попадут на ленту."""
    from pyrevit.loader import sessionmgr
    sessionmgr.reload_pyrevit()


def restore_on_load():
    """Из startup.py: обновить копии кнопок по настройкам (после обновления LowLife в них старые
    скрипты; после переустановки ячеек нет совсем — тогда панели появятся со следующей загрузки)."""
    try:
        write_panels()
    except Exception:
        pass
