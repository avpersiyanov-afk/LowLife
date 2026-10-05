# -*- coding: utf-8 -*-
"""
Шаблон имени уровня — из какой части имени брать корпус, этаж и
комментарий (кнопка «Разрез по семейству»: следующий этаж того же корпуса,
скрытие уровней других корпусов).

Шаблон — текст с подстановками в фигурных скобках, например
«{Дисциплина}_{Корпус}_{Отметка}_{Этаж}_{Комментарий}» (по умолчанию) или
«{Корпус}-{Этаж}». Смысл имеют {Корпус}, {Этаж} и {Комментарий}; любые
другие имена в скобках ({Дисциплина}, {Отметка}, ...) — просто «здесь
что-то есть, пропустить». {Этаж} обязателен; без {Корпус} все уровни
считаются одним корпусом. {Комментарий}, если он стоит в самом конце, —
необязательный: «АР_К1_+0.000_01» и «АР_К1_+0.000_01_низ перекрытия»
подходят под шаблон по умолчанию оба.

Текст между подстановками сравнивается буквально. Каждое поле — самое
короткое, при котором совпадает остальное: «_» внутри комментария (он
последний) допустим, внутри корпуса/этажа — нет. Чистая логика, без
Revit API.
"""

import re

BUILDING = u"Корпус"
FLOOR = u"Этаж"
COMMENT = u"Комментарий"

DEFAULT_TEMPLATE = u"{Дисциплина}_{Корпус}_{Отметка}_{Этаж}_{Комментарий}"

_PLACEHOLDER_RE = re.compile(u"\\{([^{}]*)\\}", re.UNICODE)


class LevelNameTemplate(object):
    """
    Разобранный шаблон. error — текст ошибки (шаблон неверный) или None;
    при ошибке parse() всегда возвращает None.
    """

    def __init__(self, template):
        self.template = (template or u"").strip()
        self.error = None
        self._regex = None
        self._groups = {}
        self._compile()

    def _compile(self):
        if not self.template:
            self.error = u"шаблон имени уровня пустой"
            return

        # [(литерал перед подстановкой, имя подстановки)], хвост — отдельно.
        parts = []
        pos = 0
        for m in _PLACEHOLDER_RE.finditer(self.template):
            name = m.group(1).strip()
            if not name:
                self.error = u"в шаблоне есть пустые скобки {}"
                return
            parts.append((self.template[pos:m.start()], name))
            pos = m.end()
        tail = self.template[pos:]

        if u"{" in tail or u"}" in tail or any(u"{" in lit or u"}" in lit for lit, _ in parts):
            self.error = u"в шаблоне есть незакрытая фигурная скобка"
            return
        names = [name for _lit, name in parts]
        if FLOOR not in names:
            self.error = u"в шаблоне нет {%s}" % FLOOR
            return
        for key in (BUILDING, FLOOR, COMMENT):
            if names.count(key) > 1:
                self.error = u"{%s} встречается в шаблоне больше одного раза" % key
                return

        # Последнее поле — {Комментарий} без текста после него → необязательно.
        optional_last = (not tail and parts and parts[-1][1] == COMMENT
                         and bool(parts[-1][0]))

        pattern = u"^"
        for i, (lit, name) in enumerate(parts):
            group = u"(.*?)"
            if optional_last and i == len(parts) - 1:
                pattern += u"(?:" + re.escape(lit) + group + u")?"
            else:
                pattern += re.escape(lit) + group
            if name in (BUILDING, FLOOR, COMMENT):
                self._groups[name] = i + 1
        pattern += re.escape(tail) + u"$"
        self._regex = re.compile(pattern, re.UNICODE | re.DOTALL)

    def _field(self, match, key):
        idx = self._groups.get(key)
        if idx is None:
            return u""
        return (match.group(idx) or u"").strip()

    def parse(self, name):
        """
        (корпус, этаж, комментарий) — корпус и этаж в нижнем регистре
        (сравниваются без учёта регистра), без пробелов по краям; None,
        если имя не подходит под шаблон, этаж (или корпус, если он есть в
        шаблоне) пустой, или шаблон неверный.
        """
        if self._regex is None or name is None:
            return None
        m = self._regex.match(name)
        if m is None:
            return None
        building = self._field(m, BUILDING).lower()
        floor = self._field(m, FLOOR).lower()
        if not floor or (BUILDING in self._groups and not building):
            return None
        return building, floor, self._field(m, COMMENT)


def validate(template):
    """Текст ошибки шаблона или None, если шаблон годится."""
    return LevelNameTemplate(template).error
