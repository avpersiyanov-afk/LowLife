# -*- coding: utf-8 -*-
"""Список панелей и кнопок вкладки LowLife по папкам расширения — для окон «Обратная связь» и «Поиск».

Без Revit API: читает `LowLife.tab/*.panel/*.pushbutton` и их `bundle.yaml` / `script.py`
так же, как их видит пользователь на ленте (заголовки, подсказки, порядок из `layout:`).
"""
import io
import os
import re

TAB_FOLDER = u"LowLife.tab"
BUTTON_EXTS = (u".pushbutton", u".pulldown", u".splitbutton", u".splitpushbutton", u".smartbutton",
               u".linkbutton", u".invokebutton", u".urlbutton", u".combobox")
STACK_EXTS = (u".stack",)

_SCRIPT_TITLE = re.compile(r'^__title__\s*=\s*u?(["\'])(.*?)\1', re.M)
_SCRIPT_DOC = re.compile(r'^__doc__\s*=\s*u?(["\'])(.*?)\1', re.M)


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


def _parse_bundle(folder):
    """{'title', 'tooltip', 'layout'} из bundle.yaml папки (пустые, если нет).

    Разбирает только нужное подмножество YAML: однострочные или блочные (`>-`/`|`) `title:`/`tooltip:`
    и список `layout:`. Блочное значение склеивается в одну строку через пробел.
    """
    result = {u"title": u"", u"tooltip": u"", u"layout": []}
    lines = _read(os.path.join(folder, u"bundle.yaml")).splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        key = next((k for k in (u"title", u"tooltip") if line.startswith(k + u":")), None)
        if key:
            value = line[len(key) + 1:].strip()
            if value[:1] in (u">", u"|"):
                parts = []
                i += 1
                while i < len(lines) and (lines[i].startswith(u" ") or not lines[i].strip()):
                    if lines[i].strip():
                        parts.append(lines[i].strip())
                    i += 1
                result[key] = u" ".join(parts)
                continue
            result[key] = _unquote(value)
        elif line.startswith(u"layout:"):
            i += 1
            while i < len(lines) and (lines[i].startswith(u" ") or lines[i].startswith(u"-")
                                      or not lines[i].strip()):
                item = lines[i].strip()
                if item.startswith(u"-"):
                    result[u"layout"].append(_unquote(item[1:]))
                i += 1
            continue
        i += 1
    return result


def read_bundle(folder):
    """(title, layout) из bundle.yaml папки; title — u'' если нет, layout — список имён без расширения."""
    bundle = _parse_bundle(folder)
    return bundle[u"title"], bundle[u"layout"]


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


# ---------------------------------------------------------------- поиск кнопок (кнопка «Поиск»)

CONTAINER_EXTS = (u".pulldown", u".splitbutton", u".splitpushbutton")
NOT_RUNNABLE_EXTS = (u".combobox",)  # у списка нет команды — запускать нечего


def _script_doc(folder):
    m = _SCRIPT_DOC.search(_read(os.path.join(folder, u"script.py")))
    return m.group(2) if m else u""


def _collect(folder, panel, panel_title, path, out):
    for name in _ordered(folder, BUTTON_EXTS + STACK_EXTS):
        full = os.path.join(folder, name)
        ext = os.path.splitext(name)[1].lower()
        if ext in STACK_EXTS:
            _collect(full, panel, panel_title, path, out)  # кнопки стека на ленте — прямо в панели
        elif ext in CONTAINER_EXTS:
            _collect(full, panel, panel_title, path + [_stem(name)], out)
        elif ext not in NOT_RUNNABLE_EXTS:
            bundle = _parse_bundle(full)
            out.append({
                u"panel": panel,
                u"panel_title": panel_title,
                u"button": _stem(name),
                u"path": path + [_stem(name)],  # имена папок от панели вниз (через выпадающие списки)
                u"title": item_title(full),
                u"tooltip": _clean(bundle[u"tooltip"] or _script_doc(full)),
            })


def list_buttons(root=None):
    """Все запускаемые кнопки вкладки в порядке ленты — для кнопки «Поиск».

    Каждая — dict: panel/button (имена папок без расширения, как их видит pyRevit),
    path (папки от панели до кнопки), title/panel_title (подписи на ленте), tooltip.
    """
    tab = os.path.join(root or extension_root(), TAB_FOLDER)
    result = []
    for name in _ordered(tab, (u".panel",)):
        folder = os.path.join(tab, name)
        _collect(folder, _stem(name), item_title(folder), [], result)
    return result


_EN = u"qwertyuiop[]asdfghjkl;'zxcvbnm,.`"
_RU = u"йцукенгшщзхъфывапролджэячсмитьбюё"
_EN_TO_RU = dict(zip(_EN, _RU))


def _norm(text):
    return (text or u"").lower().replace(u"ё", u"е")


def switch_layout(text):
    """Текст, набранный в английской раскладке вместо русской: «wtgb» → «цепи»."""
    return u"".join(_EN_TO_RU.get(ch, ch) for ch in _norm(text))


_ENDING_CHARS = u"аеиоуыэюяйь"


def _root(token):
    """Слово без гласного окончания — чтобы «цепи» находило «цепей», а «длины» — «длина»."""
    while len(token) > 3 and token[-1] in _ENDING_CHARS:
        token = token[:-1]
    return token


def _score(entry, query, tokens):
    title = _norm(entry[u"title"])
    names = _norm(u" ".join(entry[u"path"]))
    head = title + u" " + _norm(entry[u"panel_title"]) + u" " + names
    everything = head + u" " + _norm(entry[u"tooltip"])
    if not all(t in everything for t in tokens):
        return None
    if title.startswith(query):
        return 0
    if all(t in title for t in tokens):
        return 1
    if all(t in head for t in tokens):
        return 2
    return 3  # нашлось только в подсказке


def _search(entries, query):
    query = u" ".join(_norm(query).split())
    tokens = [_root(t) for t in query.split()]
    scored = []
    for i, entry in enumerate(entries):
        score = _score(entry, query, tokens)
        if score is not None:
            scored.append((score, i, entry))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [entry for _, _, entry in scored]


def search(entries, query):
    """Кнопки, где есть все слова запроса (без учёта регистра, ё/е и гласного окончания): сначала совпадения
    в подписи кнопки, потом в названии панели, потом в подсказке; внутри — порядок ленты.
    Пустой запрос — все кнопки. Если ничего не нашлось, пробует запрос в русской раскладке."""
    if not (query or u"").strip():
        return list(entries)
    found = _search(entries, query)
    if not found:
        switched = switch_layout(query)
        if switched != _norm(query):
            found = _search(entries, switched)
    return found
