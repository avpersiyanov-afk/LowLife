# -*- coding: utf-8 -*-
"""
Общие кирпичики снимка модели в JSON (json_snapshot и его модулей
json_snapshot_geometry / json_snapshot_rooms / json_snapshot_create):
единицы, отпечатки значений, имена элементов и класс правки Change.

Вынесено отдельно, чтобы модули-расширения не импортировали
json_snapshot (он сам их импортирует — был бы циклический импорт).
"""

import hashlib

from Autodesk.Revit.DB import Element, ElementId, XYZ

MM_IN_FOOT = 304.8


def fingerprint(text):
    u"""Короткий отпечаток значения (текстом, без краевых пробелов).
    Одинаково считается при выгрузке и при загрузке."""
    data = (text or u"").strip().encode("utf-8")
    return hashlib.md5(data).hexdigest()[:8]


def safe_name(el):
    if el is None:
        return u""
    try:
        return Element.Name.GetValue(el) or u""
    except Exception:
        try:
            return el.Name or u""
        except Exception:
            return u""


def category_name(el):
    try:
        cat = el.Category
        return cat.Name if cat is not None else u""
    except Exception:
        return u""


def xyz_mm(xyz, digits=1):
    u"""XYZ (футы) -> [x, y, z] в мм, округлённые."""
    return [round(xyz.X * MM_IN_FOOT, digits),
            round(xyz.Y * MM_IN_FOOT, digits),
            round(xyz.Z * MM_IN_FOOT, digits)]


def mm_xyz(values):
    u"""[x, y, z] в мм (числа или строки-числа) -> XYZ в футах.
    ValueError, если это не три числа."""
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise ValueError(u"ожидались три числа [x, y, z]")
    x, y, z = [float(unicode(v).replace(u",", u".")) for v in values]
    return XYZ(x / MM_IN_FOOT, y / MM_IN_FOOT, z / MM_IN_FOOT)


def find_element(doc, rec):
    u"""Элемент по записи снимка: сначала UniqueId, запасной — Id."""
    uid = rec.get("uid")
    if uid:
        try:
            el = doc.GetElement(unicode(uid))
            if el is not None:
                return el
        except Exception:
            pass
    try:
        return doc.GetElement(ElementId(int(rec.get("id"))))
    except Exception:
        return None


def short(text, limit=60):
    text = (text or u"").replace(u"\n", u" ")
    return text if len(text) <= limit else text[:limit - 3] + u"…"


class Change(object):
    u"""
    Одна правка из снимка: подпись для списка предпросмотра, признак
    конфликта и функция записи. apply() вызывается внутри транзакции и
    возвращает None при успехе или текст ошибки.
    """

    def __init__(self, label, apply_fn, conflict=False):
        self.label = label
        self.conflict = conflict
        self._apply_fn = apply_fn
        prefix = u"⚠ в модели изменён после выгрузки · " if conflict else u""
        self.name = prefix + label

    def apply(self):
        return self._apply_fn()

    def __str__(self):
        return self.name
