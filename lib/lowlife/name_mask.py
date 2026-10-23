# -*- coding: utf-8 -*-
"""
Маска имени из значений двух параметров — для кнопок «Имя нагрузки» и
«Имя панели» (CircuitsGeneric.panel). Чистая логика, без Revit API.

Маска — обычный текст, в котором {1} заменяется значением первого
параметра, {2} — второго: «{1}-{2}», «Щ{1} (эт. {2})», «{2}». Каждый
маркер может встречаться сколько угодно раз; остальной текст переносится
как есть.
"""

import re

TOKEN_RE = re.compile(r"\{([12])\}")
DEFAULT_MASK = u"{1}-{2}"


def mask_tokens(mask):
    """Номера параметров (1, 2), которые использует маска, по возрастанию."""
    return sorted(set(int(m) for m in TOKEN_RE.findall(mask or u"")))


def validate_mask(mask):
    """None — маска годится, иначе текст ошибки."""
    if not (mask or u"").strip():
        return u"маска пустая"
    if not mask_tokens(mask):
        return u"в маске нет ни {1}, ни {2} — значения параметров некуда подставить"
    return None


def missing_tokens(mask, values):
    """Номера маркеров маски, для которых нет значения (None/пусто)."""
    return [i for i in mask_tokens(mask) if not (values.get(i) or u"").strip()]


def render_mask(mask, values):
    """
    Текст по маске. values — {1: значение, 2: значение}; отсутствующее
    значение подставляется пустой строкой. Пробелы по краям результата
    обрезаются.
    """
    def _sub(match):
        value = values.get(int(match.group(1)))
        return u"" if value is None else value
    return TOKEN_RE.sub(_sub, mask or u"").strip()
