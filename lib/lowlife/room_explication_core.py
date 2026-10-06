# -*- coding: utf-8 -*-
"""Экспликация фрагмента — часть без Revit API (`ToolsRooms.panel/FragmentExplication`).

Столбцы, их заголовки и ширины по умолчанию (форма 2 «Экспликация
помещений» ГОСТ 21.501), сортировка номеров «по-человечески», формат
площади, имена спецификации/ключевого параметра. Покрыто
`tests/test_room_explication_core.py`; идёт и под Python 3.
"""

import re

MM_IN_FOOT = 304.8
SQ_FT_TO_SQ_M = 0.09290304

# (ключ столбца, заголовок по умолчанию, ширина по умолчанию, мм).
# Заголовки — как в форме 2 ГОСТ 21.501; размеры граф ГОСТ оставляет
# разработчику, умолчания — привычные 15/60/20/15 мм (меняются в настройках).
COLUMNS = (
    ("number", u"Номер помещения", 15.0),
    ("name", u"Наименование", 60.0),
    ("area", u"Площадь, м²", 20.0),
    ("category", u"Кат. помещения", 15.0),
)

TITLE = u"Экспликация помещений"

# Символы, недопустимые в именах видов и параметров Revit.
_FORBIDDEN = u"\\:{}[]|;<>?`~"


def clean_name(text):
    """Убирает символы, которые Revit не принимает в именах видов/параметров."""
    text = u"".join(ch for ch in (text or u"") if ch not in _FORBIDDEN)
    return u" ".join(text.split())


def schedule_name(view_name):
    """Имя спецификации для фрагмента (по нему же повторный запуск её находит)."""
    return clean_name(u"Экспликация - {}".format(view_name))


def key_param_name(view_name):
    """Имя ключевого параметра помещений, который Revit заводит под спецификацию."""
    return clean_name(u"Экспликация ключ - {}".format(view_name))


def natural_key(text):
    """Ключ сортировки: числа внутри строки сравниваются как числа (1.2 < 1.10)."""
    parts = re.split(r"(\d+)", (text or u"").strip().lower())
    return [(0, int(p), u"") if p.isdigit() else (1, 0, p) for p in parts if p != u""]


def format_area(sq_m, decimals=2, separator=u","):
    """Площадь в м² текстом: фиксированное число знаков, запятая по ГОСТ."""
    decimals = max(0, int(decimals))
    text = u"{:.{}f}".format(float(sq_m), decimals)
    return text.replace(u".", separator)


def build_rows(rooms, decimals=2):
    """
    rooms — список dict {number, name, area_m2, category}. Возвращает
    список строк таблицы (кортежи текстов в порядке COLUMNS), по номеру
    помещения; одинаковые строки (помещение пришло дважды) — один раз.
    """
    rows = []
    seen = set()
    for r in sorted(rooms, key=lambda r: (natural_key(r.get("number")),
                                          natural_key(r.get("name")))):
        row = (
            (r.get("number") or u"").strip(),
            (r.get("name") or u"").strip(),
            format_area(r.get("area_m2") or 0.0, decimals),
            (r.get("category") or u"").strip(),
        )
        if row in seen:
            continue
        seen.add(row)
        rows.append(row)
    return rows


def key_names(count):
    """Ключевые имена строк: 001, 002, … — по ним сортируется спецификация."""
    width = max(3, len(str(count)))
    return [str(i + 1).zfill(width) for i in range(count)]


def in_rect(x, y, rect):
    xmin, ymin, xmax, ymax = rect
    return xmin <= x <= xmax and ymin <= y <= ymax
