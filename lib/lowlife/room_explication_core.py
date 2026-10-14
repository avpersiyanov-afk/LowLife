# -*- coding: utf-8 -*-
"""Экспликация фрагмента — часть без Revit API (`ToolsRooms.panel/FragmentExplication`,
`UpdateExplication`).

Столбцы, их заголовки и ширины по умолчанию (форма 2 «Экспликация
помещений» ГОСТ 21.501), сортировка номеров «по-человечески», формат
площади, имена спецификации/ключевого параметра, ключевые имена строк. Покрыто
`tests/test_room_explication_core.py`; идёт и под Python 3.
"""

import re

MM_IN_FOOT = 304.8
SQ_FT_TO_SQ_M = 0.09290304

# (ключ столбца, заголовок по умолчанию, ширина по умолчанию, мм).
# Заголовки и размеры — форма 2 «Экспликация помещений» ГОСТ 21.501:
# графы 15/80/20/10 мм (итого 125), шапка 20 мм, строка 8 мм. Меняются в
# настройках кнопки.
COLUMNS = (
    ("number", u"Номер помещения", 15.0),
    ("name", u"Наименование", 80.0),
    ("area", u"Площадь, м²", 20.0),
    ("category", u"Кат. помещения", 10.0),
)
HEADER_HEIGHT_MM = 20.0
ROW_HEIGHT_MM = 8.0

# Умолчания ширин до сверки с формой ГОСТ — сохранённые с ними настройки
# переводятся на новые (room_explication_settings._migrate).
OLD_DEFAULT_WIDTHS = {"name": 60.0, "category": 15.0}

TITLE = u"Экспликация помещений"  # строка названия над таблицей

# Вид таблицы экспликации (настройка «Вид таблицы»).
KIND_HEADER = "header"  # «Ручная спецификация»: таблица текстом в шапке спецификации
KIND_KEY = "key"        # ключевая спецификация (room_explication_key)

# Символы, недопустимые в именах видов и параметров Revit.
_FORBIDDEN = u"\\:{}[]|;<>?`~"


def clean_name(text):
    """Убирает символы, которые Revit не принимает в именах видов/параметров."""
    text = u"".join(ch for ch in (text or u"") if ch not in _FORBIDDEN)
    return u" ".join(text.split())


def schedule_name(view_name):
    """Имя спецификации для фрагмента (занятое — дополняется unique_name)."""
    return clean_name(u"Экспликация - {}".format(view_name))


def key_param_name(schedule_name_text):
    """Имя ключевого параметра помещений, который Revit заводит под ключевую
    спецификацию (вид таблицы «ключевая спецификация»)."""
    return clean_name(u"Ключ - {}".format(schedule_name_text))


def key_names(count):
    """Ключевые имена строк ключевой спецификации: 001, 002, … — по ним сортировка."""
    width = max(3, len(str(count)))
    return [str(i + 1).zfill(width) for i in range(count)]


def unique_name(name, existing):
    """name, а если занято — «name (2)», «name (3)», …"""
    if name not in existing:
        return name
    i = 2
    while u"{} ({})".format(name, i) in existing:
        i += 1
    return u"{} ({})".format(name, i)


def natural_key(text):
    """Ключ сортировки: числа внутри строки сравниваются как числа (1.2 < 1.10)."""
    parts = re.split(r"(\d+)", (text or u"").strip().lower())
    return [(0, int(p), u"") if p.isdigit() else (1, 0, p) for p in parts if p != u""]


def format_area(sq_m, decimals=2, separator=u","):
    """Площадь в м² текстом: фиксированное число знаков, запятая по ГОСТ."""
    decimals = max(0, int(decimals))
    text = u"{:.{}f}".format(float(sq_m), decimals)
    return text.replace(u".", separator)


def area_text(value, decimals=2):
    """Площадь для таблицы: число (м²) — форматом ГОСТ; текст из своего
    параметра — тоже, если это число («12.5» -> «12,50»), иначе как есть."""
    if value is None:
        return u""
    if isinstance(value, (int, float)):
        return format_area(value, decimals)
    text = u"{}".format(value).strip()
    try:
        return format_area(float(text.replace(u",", u".").replace(u" ", u"")), decimals)
    except ValueError:
        return text


# Заголовок группы для помещений, у которых параметр группы пустой.
NO_GROUP = u"Без группы"


def _row_sort_key(r):
    """Внутри группы: по параметру сортировки (если задан), затем по номеру."""
    sort_value = r.get("sort")
    return (natural_key(sort_value if sort_value is not None else r.get("number")),
            natural_key(r.get("number")), natural_key(r.get("name")))


def build_rows(rooms, decimals=2):
    """
    rooms — список dict {number, name, area_m2, category[, sort]}; area_m2 —
    число в м² или текст из параметра площади (см. area_text); sort —
    значение параметра сортировки (нет — сортировка по номеру). Возвращает
    список строк таблицы (кортежи текстов в порядке COLUMNS);
    одинаковые строки (помещение пришло дважды) — один раз.
    """
    rows = []
    seen = set()
    for r in sorted(rooms, key=_row_sort_key):
        row = (
            (r.get("number") or u"").strip(),
            (r.get("name") or u"").strip(),
            area_text(r.get("area_m2"), decimals),
            (r.get("category") or u"").strip(),
        )
        if row in seen:
            continue
        seen.add(row)
        rows.append(row)
    return rows


def build_table(rooms, decimals=2, grouped=False):
    """
    Таблица экспликации: список ("group", заголовок) и ("row", строка).
    grouped — помещения группируются по значению "group" (dict помещения):
    группы по возрастанию (числа внутри — как числа), пустое значение —
    группа NO_GROUP в конце; внутри группы — как build_rows. Без группировки —
    только строки.
    """
    if not grouped:
        return [("row", row) for row in build_rows(rooms, decimals)]
    groups = {}
    for r in rooms:
        title = (r.get("group") or u"").strip()
        groups.setdefault(title, []).append(r)
    order = sorted((t for t in groups if t), key=natural_key)
    if u"" in groups:
        order.append(u"")
    table = []
    for title in order:
        table.append(("group", title or NO_GROUP))
        table.extend(("row", row) for row in build_rows(groups[title], decimals))
    return table


def table_rows(table):
    """Только строки помещений из build_table."""
    return [item for kind, item in table if kind == "row"]


def in_rect(x, y, rect):
    xmin, ymin, xmax, ymax = rect
    return xmin <= x <= xmax and ymin <= y <= ymax
