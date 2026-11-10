# -*- coding: utf-8 -*-
"""
Чистая логика кнопки «Внесение изменений» (Tools.panel/ChangeClouds):
маска имени типа, разбор существующих типов, подсказка следующего
номера изменения, дата по маске dd.mm.yy. Никаких импортов Revit —
модуль покрыт pytest-тестами (tests/test_change_clouds_core.py).
"""

try:
    unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3
    unicode = str

DEFAULT_TEMPLATE = u"{family}_{cipher}_{number}"


def today_text(now=None):
    """Сегодняшняя дата строкой «дд.мм.гг» (mask dd.mm.yy)."""
    import datetime
    if now is None:
        now = datetime.datetime.now()
    return u"{:02d}.{:02d}.{:02d}".format(now.day, now.month, now.year % 100)


def build_type_name(template, family, cipher, number):
    """Имя нового типа по маске. Пустая маска — DEFAULT_TEMPLATE."""
    mask = template.strip() if template and template.strip() else DEFAULT_TEMPLATE
    return mask.format(family=family, cipher=cipher, number=int(number))


def parse_type_name(name, family):
    """Разобрать имя типа «<family>_<шифр>_<номер>» → dict(cipher, number) или None.

    Шифр может содержать подчёркивания — номер берётся после последнего
    подчёркивания, так что нечисловой хвост имени просто не распознаётся.
    """
    name = unicode(name)
    family = unicode(family)
    prefix = family + u"_"
    if not name.startswith(prefix):
        return None
    rest = name[len(prefix):]
    if u"_" not in rest:
        return None
    cipher, _, tail = rest.rpartition(u"_")
    if not cipher:
        return None
    try:
        number = int(tail)
    except (ValueError, TypeError):
        return None
    if number <= 0:
        return None
    return {u"cipher": cipher, u"number": number}


def suggest_number(rows, cipher):
    """Следующий номер изменения для шифра: max(существующие) + 1, иначе 1.

    rows — итерация dict с ключами cipher/number (см. parse_type_name).
    """
    best = 0
    for row in rows:
        if row and row.get(u"cipher") == cipher:
            try:
                best = max(best, int(row.get(u"number") or 0))
            except (ValueError, TypeError):
                continue
    return best + 1


def parse_number(text):
    """Строку в положительный int; None при нечисловом/неположительном вводе."""
    try:
        value = int(unicode(text).strip())
    except (ValueError, TypeError):
        return None
    return value if value > 0 else None


def parse_date(text):
    """Проверить дату «дд.мм.гг»/«дд.мм.гггг» → каноническая «дд.мм.гг» или None."""
    parts = unicode(text).strip().split(u".")
    if len(parts) != 3:
        return None
    try:
        day, month, year = [int(p) for p in parts]
    except (ValueError, TypeError):
        return None
    if not (1 <= day <= 31 and 1 <= month <= 12):
        return None
    if year > 99:
        year = year % 100
    return u"{:02d}.{:02d}.{:02d}".format(day, month, year)
