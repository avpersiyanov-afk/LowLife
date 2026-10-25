# -*- coding: utf-8 -*-
"""Список панелей и кнопок вкладки LowLife по папкам расширения — для окон «Обратная связь» и «Поиск».

Без Revit API: читает `LowLife.tab/*.panel/*.pushbutton` и их `bundle.yaml` / `script.py`
так же, как их видит пользователь на ленте (заголовки, подсказки, порядок из `layout:`).
"""
import io
import os
import re

from lowlife import favorites_core, text_search

TAB_FOLDER = u"LowLife.tab"
BUTTON_EXTS = (u".pushbutton", u".pulldown", u".splitbutton", u".splitpushbutton", u".smartbutton",
               u".linkbutton", u".invokebutton", u".urlbutton", u".combobox")
STACK_EXTS = (u".stack",)

BUNDLE_TEXT_KEYS = (u"title", u"tooltip", u"title_en", u"tooltip_en")

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
    """{'title', 'tooltip', 'title_en', 'tooltip_en', 'layout'} из bundle.yaml папки (пустые, если нет).

    Разбирает только нужное подмножество YAML: однострочные или блочные (`>-`/`|`) `title:`/`tooltip:`
    (и их английские `title_en:`/`tooltip_en:` — их pyRevit не читает, ленту переводит
    lowlife.ribbon_language) и список `layout:`. Блочное значение склеивается в одну строку через пробел.
    """
    result = {u"title": u"", u"tooltip": u"", u"title_en": u"", u"tooltip_en": u"", u"layout": []}
    lines = _read(os.path.join(folder, u"bundle.yaml")).splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        key = next((k for k in BUNDLE_TEXT_KEYS if line.startswith(k + u":")), None)
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
    """Подпапки с нужными расширениями: при `layout:` — только перечисленные в нём и по его порядку
    (неперечисленные pyRevit не строит), без него — по алфавиту."""
    try:
        names = [n for n in os.listdir(folder)
                 if os.path.isdir(os.path.join(folder, n)) and os.path.splitext(n)[1].lower() in exts]
    except (IOError, OSError):
        return []
    names.sort(key=lambda n: n.lower())
    _, layout = read_bundle(folder)
    by_stem = dict((_stem(n), n) for n in names)
    if layout:
        return [by_stem[s] for s in layout if s in by_stem]
    return names


def item_title(folder):
    """Подпись кнопки/панели: title из bundle.yaml → __title__ из script.py → имя папки."""
    title, _ = read_bundle(folder)
    return _clean(title or _script_title(folder) or _stem(os.path.basename(folder)).lstrip(u"_"))


def raw_bundle_text(folder):
    """{'title', 'tooltip', 'title_en', 'tooltip_en'} из bundle.yaml как есть — с `\\n` в подписи,
    как её получает pyRevit (для перевода ленты: lowlife.ribbon_language)."""
    bundle = _parse_bundle(folder)
    return dict((k, bundle[k]) for k in BUNDLE_TEXT_KEYS)


def read_members_en(folder):
    """{id участника: {'text', 'tooltip'}} из блока `members_en:` bundle.yaml списка (.combobox) —
    английские подписи его участников. Формат — как `members:`::

        members_en:
        - id: SCS
          text: SCS
          tooltip: Structured cabling
    """
    result = {}
    lines = _read(os.path.join(folder, u"bundle.yaml")).splitlines()
    inside, current = False, None
    for line in lines:
        if not inside:
            inside = line.startswith(u"members_en:")
            continue
        if line.strip() and not (line.startswith(u" ") or line.startswith(u"-")):
            break  # следующий ключ верхнего уровня
        item = line.strip()
        if item.startswith(u"-"):
            current = {}
            item = item[1:].strip()
        if current is None or u":" not in item:
            continue
        key, value = item.split(u":", 1)
        current[key.strip()] = _unquote(value)
        if key.strip() == u"id":
            result[current[u"id"]] = current
    return result


def item_title_en(folder):
    """Английская подпись кнопки/панели (`title_en` из bundle.yaml) или u'', если перевода нет."""
    return _clean(_parse_bundle(folder)[u"title_en"])


def localized(entry, key, lang=None):
    """Поле записи list_buttons() на выбранном языке: `title`/`panel_title`/`tooltip` → их `_en`-пара,
    если выбран английский и перевод есть."""
    if lang is None:
        from lowlife import i18n
        lang = i18n.current()
    if lang == u"en":
        return entry.get(key + u"_en") or entry.get(key) or u""
    return entry.get(key) or u""


def _buttons(folder, lang=None):
    result = []
    for name in _ordered(folder, BUTTON_EXTS + STACK_EXTS):
        path = os.path.join(folder, name)
        if os.path.splitext(name)[1].lower() in STACK_EXTS:
            result.extend(_buttons(path, lang))  # стек — просто несколько кнопок столбиком
        else:
            result.append((item_title_en(path) if lang == u'en' else u'') or item_title(path))
    return result


def _panels(tab):
    """Папки панелей вкладки по порядку — без ячеек своих панелей пользователя («Мои панели»):
    там лишь копии кнопок LowLife."""
    return [n for n in _ordered(tab, (u".panel",)) if not favorites_core.is_slot(_stem(n))]


def list_panels(root=None, lang=None):
    """Panel/button captions in ribbon order. Default: original values; lang='en': display labels."""
    tab = os.path.join(root or extension_root(), TAB_FOLDER)
    result = []
    for name in _panels(tab):
        folder = os.path.join(tab, name)
        buttons = _buttons(folder, lang)
        if buttons:
            result.append(((item_title_en(folder) if lang == u'en' else u'') or item_title(folder), buttons))
    return result


# ---------------------------------------------------------------- поиск кнопок (кнопка «Поиск»)

CONTAINER_EXTS = (u".pulldown", u".splitbutton", u".splitpushbutton")
NOT_RUNNABLE_EXTS = (u".combobox",)  # у списка нет команды — запускать нечего


def _script_doc(folder):
    m = _SCRIPT_DOC.search(_read(os.path.join(folder, u"script.py")))
    return m.group(2) if m else u""


def _collect(folder, panel, panel_title, path, out, panel_title_en=u""):
    for name in _ordered(folder, BUTTON_EXTS + STACK_EXTS):
        full = os.path.join(folder, name)
        ext = os.path.splitext(name)[1].lower()
        if ext in STACK_EXTS:
            _collect(full, panel, panel_title, path, out, panel_title_en)  # кнопки стека на ленте — прямо в панели
        elif ext in CONTAINER_EXTS:
            _collect(full, panel, panel_title, path + [_stem(name)], out, panel_title_en)
        elif ext not in NOT_RUNNABLE_EXTS:
            bundle = _parse_bundle(full)
            out.append({
                u"panel": panel,
                u"panel_title": panel_title,
                u"button": _stem(name),
                u"path": path + [_stem(name)],  # имена папок от панели вниз (через выпадающие списки)
                u"title": item_title(full),
                u"tooltip": _clean(bundle[u"tooltip"] or _script_doc(full)),
                u"title_en": _clean(bundle[u"title_en"]),
                u"panel_title_en": panel_title_en,
                u"tooltip_en": _clean(bundle[u"tooltip_en"]),
                u"folder": full,  # папка кнопки на диске — её копирует «Мои панели»
            })


def list_buttons(root=None):
    """Все запускаемые кнопки вкладки в порядке ленты — для кнопки «Поиск».

    Каждая — dict: panel/button (имена папок без расширения, как их видит pyRevit),
    path (папки от панели до кнопки), title/panel_title (подписи на ленте), tooltip и их английские
    title_en/panel_title_en/tooltip_en (u'', если перевода нет; см. localized).
    """
    tab = os.path.join(root or extension_root(), TAB_FOLDER)
    result = []
    for name in _panels(tab):
        folder = os.path.join(tab, name)
        _collect(folder, _stem(name), item_title(folder), [], result, item_title_en(folder))
    return result


def _norm(text):
    return text_search.normalize(text)


def switch_layout(text):
    """Текст, набранный в английской раскладке вместо русской: «wtgb» → «цепи»."""
    return text_search.switch_layout(_norm(text), text_search.EN_TO_RU)


_ENDING_CHARS = u"аеиоуыэюяйь"


def _root(token):
    """Слово без гласного окончания — чтобы «цепи» находило «цепей», а «длины» — «длина»."""
    while len(token) > 3 and token[-1] in _ENDING_CHARS:
        token = token[:-1]
    return token


def _score(entry, query, tokens):
    # подписи на обоих языках: кнопку находит и русский, и английский запрос
    titles = [t for t in (_norm(entry[u"title"]), _norm(entry.get(u"title_en") or u"")) if t]
    title = u" ".join(titles)
    names = _norm(u" ".join(entry[u"path"]))
    head = (title + u" " + _norm(entry[u"panel_title"]) + u" " + _norm(entry.get(u"panel_title_en") or u"")
            + u" " + names)
    everything = head + u" " + _norm(entry[u"tooltip"]) + u" " + _norm(entry.get(u"tooltip_en") or u"")
    if not all(t in everything for t in tokens):
        return None
    if any(one.startswith(query) for one in titles):
        return 0
    if any(all(t in one for t in tokens) for one in titles):
        return 1
    if all(t in head for t in tokens):
        return 2
    return 3  # нашлось только в подсказке


def _scores(entries, query):
    """{индекс кнопки: оценка _score} для подходящих под запрос."""
    query = u" ".join(_norm(query).split())
    tokens = [_root(t) for t in query.split()]
    result = {}
    for i, entry in enumerate(entries):
        score = _score(entry, query, tokens)
        if score is not None:
            result[i] = score
    return result


def search(entries, query):
    """Кнопки, где есть все слова запроса — хотя бы частью слова (без учёта регистра, ё/е и гласного
    окончания): сначала совпадения в подписи кнопки, потом в названии панели, потом в подсказке; внутри —
    порядок ленты. Запрос пробуется и в другой раскладке («wtgb» → «цепи», «вцп» → «dwg»); такое
    совпадение — сразу после совпадения того же уровня в набранной. Пустой запрос — все кнопки."""
    variants = text_search.query_variants(query)
    if not variants:
        return list(entries)
    best = {}
    for layout, variant in enumerate(variants):
        for i, score in _scores(entries, variant).items():
            key = (score, layout)  # то же место совпадения в набранной раскладке — выше
            if i not in best or key < best[i]:
                best[i] = key
    return [entries[i] for i in sorted(best, key=lambda i: (best[i], i))]
