# -*- coding: utf-8 -*-
"""Список панелей и кнопок вкладки LowLife по папкам расширения — для окна «Обратная связь».

Без Revit API: читает `LowLife.tab/*.panel/*.pushbutton` и их `bundle.yaml` / `script.py`
так же, как их видит пользователь на ленте (заголовки, порядок из `layout:`).
"""
import io
import os
import re

TAB_FOLDER = u"LowLife.tab"
BUTTON_EXTS = (u".pushbutton", u".pulldown", u".splitbutton", u".splitpushbutton", u".smartbutton",
               u".linkbutton", u".invokebutton", u".urlbutton", u".combobox")
STACK_EXTS = (u".stack",)

_SCRIPT_TITLE = re.compile(r'^__title__\s*=\s*u?(["\'])(.*?)\1', re.M)


def extension_root():
    """Корень расширения: lib/lowlife/ribbon_catalog.py → два уровня вверх от lib."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(path):
    try:
        with io.open(path, "r", encoding="utf-8-sig") as f:
            return f.read()
    except (IOError, OSError, UnicodeDecodeError):
        return u""


def _unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in u"\"'":
        value = value[1:-1]
    return value.strip()


def read_bundle(folder):
    """(title, layout) из bundle.yaml папки; title — u'' если нет, layout — список имён без расширения.

    Разбирает только нужное подмножество YAML: `title:` (однострочный или `>-`/`|`) и список `layout:`.
    """
    title, layout = u"", []
    lines = _read(os.path.join(folder, u"bundle.yaml")).splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(u"title:"):
            value = line[len(u"title:"):].strip()
            if value[:1] in (u">", u"|"):
                parts = []
                i += 1
                while i < len(lines) and (lines[i].startswith(u" ") or not lines[i].strip()):
                    if lines[i].strip():
                        parts.append(lines[i].strip())
                    i += 1
                title = u" ".join(parts)
                continue
            title = _unquote(value)
        elif line.startswith(u"layout:"):
            i += 1
            while i < len(lines) and (lines[i].startswith(u" ") or lines[i].startswith(u"-")
                                      or not lines[i].strip()):
                item = lines[i].strip()
                if item.startswith(u"-"):
                    layout.append(_unquote(item[1:]))
                i += 1
            continue
        i += 1
    return title, layout


def _script_title(folder):
    m = _SCRIPT_TITLE.search(_read(os.path.join(folder, u"script.py")))
    return m.group(2) if m else u""


def _clean(title):
    # «Цепи\nшлейфов СПА» → «Цепи шлейфов СПА»: так подпись читается в одну строку списка
    title = title.replace(u"\\n", u" ").replace(u"\n", u" ")
    return u" ".join(title.split())


def _stem(name):
    return os.path.splitext(name)[0]


def _ordered(folder, exts):
    """Подпапки с нужными расширениями: сначала по `layout:`, остальные — по алфавиту (как у pyRevit)."""
    try:
        names = [n for n in os.listdir(folder)
                 if os.path.isdir(os.path.join(folder, n)) and os.path.splitext(n)[1].lower() in exts]
    except (IOError, OSError):
        return []
    names.sort(key=lambda n: n.lower())
    _, layout = read_bundle(folder)
    by_stem = dict((_stem(n), n) for n in names)
    ordered = [by_stem.pop(s) for s in layout if s in by_stem]
    return ordered + [n for n in names if _stem(n) in by_stem]


def item_title(folder):
    """Подпись кнопки/панели: title из bundle.yaml → __title__ из script.py → имя папки."""
    title, _ = read_bundle(folder)
    return _clean(title or _script_title(folder) or _stem(os.path.basename(folder)).lstrip(u"_"))


def _buttons(folder):
    result = []
    for name in _ordered(folder, BUTTON_EXTS + STACK_EXTS):
        path = os.path.join(folder, name)
        if os.path.splitext(name)[1].lower() in STACK_EXTS:
            result.extend(_buttons(path))  # стек — просто несколько кнопок столбиком
        else:
            result.append(item_title(path))
    return result


def list_panels(root=None):
    """[(подпись панели, [подписи кнопок]), ...] в порядке ленты; панели без кнопок пропускаются."""
    tab = os.path.join(root or extension_root(), TAB_FOLDER)
    result = []
    for name in _ordered(tab, (u".panel",)):
        buttons = _buttons(os.path.join(tab, name))
        if buttons:
            result.append((item_title(os.path.join(tab, name)), buttons))
    return result
