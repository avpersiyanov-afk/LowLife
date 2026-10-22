# -*- coding: utf-8 -*-
"""«Избранное» — чистая логика без Revit API (тесты: tests/test_favorites_core.py).

Пользователь собирает свои панели из кнопок LowLife. Настройки — список панелей по порядку:

    {"panels": [{"title": "Мои цепи", "buttons": [{"panel": "SCS", "path": ["PlaceRouteNodes"]}, ...]}]}

Кнопка запоминается по папкам (`panel` — папка панели, `path` — папки от панели до кнопки, как в
`ribbon_catalog.list_buttons()`), а не по подписи: подписи меняются, папки — нет.

Revit-часть (панели на ленте, окно настройки) — `favorites.py` / `favorites_ui.py`.
"""

try:
    unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3
    unicode = str

# Имя панели избранного на ленте — PANEL_PREFIX + подпись: по префиксу видно, что панель наша,
# а имя никогда не совпадёт с панелью самого LowLife (Revit не даёт двух панелей с одним именем).
PANEL_PREFIX = u"LowLifeFav_"
# Имя кнопки в панели избранного — BUTTON_PREFIX + папки через точку (в именах папок точек нет:
# pyRevit отрезает расширение по первой точке). По нему статистика запусков узнаёт исходную кнопку.
BUTTON_PREFIX = u"LLFav."
MAX_TITLE = 40
# Панели LowLife, кнопки которых на свои панели не кладутся: сама «Мои панели» (её кнопка — это окно настройки)
EXCLUDED_PANELS = (u"Favorites",)


def can_add(entry_or_ref):
    """Можно ли положить кнопку на свою панель (entry из ribbon_catalog или ссылка из настроек)."""
    return entry_or_ref[u"panel"] not in EXCLUDED_PANELS


def _text(value):
    return u" ".join(unicode(value or u"").split())


def button_ref(entry):
    """{'panel', 'path'} кнопки из ribbon_catalog.list_buttons() — то, что хранится в настройках."""
    return {u"panel": unicode(entry[u"panel"]), u"path": [unicode(p) for p in entry[u"path"]]}


def button_key(ref):
    """Строка-ключ кнопки: «SCS/PlaceRouteNodes» (через выпадающий список — «Panel/List/Button»)."""
    return u"/".join([ref[u"panel"]] + list(ref[u"path"]))


def _clean_ref(raw):
    if not isinstance(raw, dict):
        return None
    panel = _text(raw.get(u"panel"))
    path = [_text(p) for p in (raw.get(u"path") or []) if _text(p)]
    if not panel or not path or panel in EXCLUDED_PANELS:
        return None
    return {u"panel": panel, u"path": path}


def normalize(data):
    """Настройки в каноническом виде: пустые подписи и кнопки отброшены, повторы убраны."""
    panels, titles = [], set()
    raw_panels = (data or {}).get(u"panels") if isinstance(data, dict) else None
    for raw in raw_panels or []:
        if not isinstance(raw, dict):
            continue
        title = _text(raw.get(u"title"))[:MAX_TITLE]
        if not title or title.lower() in titles:
            continue
        titles.add(title.lower())
        buttons, keys = [], set()
        for raw_ref in raw.get(u"buttons") or []:
            ref = _clean_ref(raw_ref)
            if ref is not None and button_key(ref) not in keys:
                keys.add(button_key(ref))
                buttons.append(ref)
        panels.append({u"title": title, u"buttons": buttons})
    return {u"panels": panels}


def panel_name(title):
    return PANEL_PREFIX + title


def is_favorite_panel(name):
    return unicode(name or u"").startswith(PANEL_PREFIX)


def button_name(ref):
    return BUTTON_PREFIX + u".".join([ref[u"panel"]] + list(ref[u"path"]))


def parse_button_name(name):
    """{'panel', 'path'} из имени кнопки избранного или None — не наша кнопка."""
    name = unicode(name or u"")
    if not name.startswith(BUTTON_PREFIX):
        return None
    parts = [p for p in name[len(BUTTON_PREFIX):].split(u".") if p]
    if len(parts) < 2:
        return None
    return {u"panel": parts[0], u"path": parts[1:]}


def title_problem(title, other_titles, reserved=()):
    """Почему подпись панели не годится (текст) или None.

    other_titles — подписи остальных панелей избранного, reserved — подписи панелей самого LowLife
    (две панели с одной подписью на вкладке не различить)."""
    title = _text(title)
    if not title:
        return u"Введите название панели."
    if len(title) > MAX_TITLE:
        return u"Название длиннее {} знаков.".format(MAX_TITLE)
    if u"%" in title:
        return u"Знак «%» в названии панели нельзя: Revit им разделяет имена на ленте."
    low = title.lower()
    if any(low == _text(t).lower() for t in other_titles):
        return u"Панель «{}» в избранном уже есть.".format(title)
    if any(low == _text(t).lower() for t in reserved):
        return u"Так называется панель LowLife — выберите другое название."
    return None


def find_entry(entries, ref):
    """Кнопка из ribbon_catalog.list_buttons() по ссылке из настроек или None (кнопку удалили)."""
    for entry in entries:
        if entry[u"panel"] == ref[u"panel"] and list(entry[u"path"]) == list(ref[u"path"]):
            return entry
    return None


def add_button(data, title, ref):
    """Новые настройки с кнопкой ref в конце панели title (панели нет — создаётся). False во втором
    значении — кнопка там уже была."""
    data = normalize(data)
    if _clean_ref(ref) is None:
        return data, False
    panel = next((p for p in data[u"panels"] if p[u"title"].lower() == _text(title).lower()), None)
    if panel is None:
        panel = {u"title": _text(title), u"buttons": []}
        data[u"panels"].append(panel)
    if any(button_key(r) == button_key(ref) for r in panel[u"buttons"]):
        return data, False
    panel[u"buttons"].append(_clean_ref(ref))
    return normalize(data), True


def move(items, index, step):
    """Сдвинуть элемент списка на step позиций (на месте); новый индекс."""
    if not 0 <= index < len(items):
        return index
    new = min(max(index + step, 0), len(items) - 1)
    if new != index:
        items.insert(new, items.pop(index))
    return new
