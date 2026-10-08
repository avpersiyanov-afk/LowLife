# -*- coding: utf-8 -*-
"""
Чистая логика кнопки «Проверка LOI» (LOI.panel/CheckLOI.pushbutton) — без
Revit API, покрыта tests/test_loi_check_core.py.

Настройка параметров — в два шага (см. loi_check_settings.py): сначала
список строк (как они записаны в требованиях LOI, по одной на строке), потом
для каждой строки — имя параметра модели, в котором это значение лежит.
Пустое имя параметра — берётся сама строка списка (частый случай, когда
строка требований и есть имя параметра).
"""

try:
    _text = unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3 (тесты)
    _text = str


def parse_labels(text):
    """Строки списка параметров — по одной на строке, без пустых и повторов,
    в исходном порядке."""
    labels = []
    seen = set()
    for line in _text(text or u"").splitlines():
        label = line.strip()
        if label and label not in seen:
            seen.add(label)
            labels.append(label)
    return labels


def build_rows(labels, param_map):
    """[(строка списка, имя параметра)] — имя параметра из param_map
    ({строка: параметр}), пустое — сама строка."""
    param_map = param_map or {}
    rows = []
    for label in labels:
        param = _text(param_map.get(label) or u"").strip()
        rows.append((label, param or label))
    return rows


def clean_param_map(labels, param_map):
    """param_map только для текущих строк списка и только с непустыми
    значениями — то, что сохраняется в файл настроек."""
    param_map = param_map or {}
    result = {}
    for label in labels:
        param = _text(param_map.get(label) or u"").strip()
        if param:
            result[label] = param
    return result


def is_blank(value):
    """Пустое значение параметра: None или строка из одних пробелов."""
    if value is None:
        return True
    return not _text(value).strip()


# Состояние параметра у элемента
FILLED = "filled"
EMPTY = "empty"      # параметр есть, значение пустое
ABSENT = "absent"    # у элемента (и его типа) нет такого параметра


def status_of(found, value):
    """FILLED/EMPTY/ABSENT по тому, нашёлся ли параметр и что в нём."""
    if not found:
        return ABSENT
    return EMPTY if is_blank(value) else FILLED


class LabelStats(object):
    def __init__(self, label, param_name):
        self.label = label
        self.param_name = param_name
        self.filled = 0
        self.empty = 0
        self.absent = 0


class CategorySummary(object):
    """Итог проверки одной категории: сколько элементов, сколько с
    пропусками, разбивка по строкам списка."""

    def __init__(self, category_name, rows):
        self.category_name = category_name
        self.total = 0
        self.incomplete = 0
        self.stats = [LabelStats(label, param) for label, param in rows]

    def add(self, statuses):
        """statuses — список FILLED/EMPTY/ABSENT (None — параметр у этого
        элемента не требуется) в порядке rows. Возвращает True, если у
        элемента есть хоть один незаполненный обязательный параметр."""
        self.total += 1
        bad = False
        for st, status in zip(self.stats, statuses):
            if status is None:
                continue
            if status == FILLED:
                st.filled += 1
            elif status == EMPTY:
                st.empty += 1
                bad = True
            else:
                st.absent += 1
                bad = True
        if bad:
            self.incomplete += 1
        return bad


def status_text(status, value):
    """Текст ячейки отчёта: значение, «—» для пустого, «нет параметра»;
    u"" — параметр у элемента не требуется."""
    if status is None:
        return u""
    if status == FILLED:
        return _text(value).strip()
    if status == EMPTY:
        return u"—"
    return u"нет параметра"


def schedule_name(prefix, category_name):
    """Имя спецификации для категории (без запрещённых в Revit символов)."""
    name = u"{} — {}".format(prefix, category_name)
    for ch in u"{}[]|;<>?`~:\\":
        name = name.replace(ch, u"_")
    return name


# --- этапы проверки по приложению LOI (loi_appendix.parse) ----------------------

class Stage(object):
    """Этап проверки: столбец «Подэтап проверки» стадии и номер подэтапа.
    Обязательны параметры, у которых в этом столбце подэтап <= level."""

    def __init__(self, column, level):
        self.key = column["key"]
        self.level = level
        self.title = u"{} · {} · {}-{}".format(
            column["stage"], column["part"], column["prefix"], level)

    def __str__(self):
        return self.title


def list_stages(appendix):
    """Все этапы приложения по порядку столбцов и подэтапов."""
    stages = []
    for column in (appendix or {}).get("columns") or []:
        for level in column.get("levels") or []:
            stages.append(Stage(column, level))
    return stages


def find_stage(appendix, title):
    for stage in list_stages(appendix):
        if stage.title == title:
            return stage
    return None


def required_params(rule, stage):
    """Имена параметров правила, обязательных на этапе (в порядке приложения)."""
    names = []
    for p in rule.get("params") or []:
        level = (p.get("levels") or {}).get(stage.key)
        if level is not None and level <= stage.level and p["name"] not in names:
            names.append(p["name"])
    return names


def norm_name(text):
    """Для сравнения имён категорий: регистр, «ё», пробелы."""
    return u" ".join(_text(text or u"").lower().replace(u"ё", u"е").split())


def code_matches(element_code, class_code):
    """Код элемента относится к классу: совпадает или уточняет его
    («А.05.10.20» относится к классу «А.05.10»)."""
    element_code = _text(element_code or u"").strip()
    class_code = _text(class_code or u"").strip()
    if not element_code or not class_code:
        return False
    return element_code == class_code or element_code.startswith(class_code + u".")


class CategoryPlan(object):
    """
    Что проверять у элементов одной категории Revit на этапе: столбцы
    (объединение обязательных параметров всех классов категории) и
    обязательные параметры конкретного элемента по его коду классификатора.

    Элемент без кода: если у категории один класс — проверяется по нему,
    иначе — по параметрам, обязательным для всех классов категории сразу
    (из тех, которым на этапе вообще что-то требуется)
    (параметр кода среди них обычно есть, так что элемент и так попадёт в
    незаполненные). Элемент с кодом, которого нет в загруженных разделах
    приложения, не проверяется — это элемент другой дисциплины (в одной
    категории, например «Электрооборудование», бывают элементы разных
    разделов); такие коды перечисляются в отчёте.
    """

    MATCHED = "matched"
    NO_CODE = "no_code"
    UNKNOWN = "unknown"


    def __init__(self, category, rules, stage):
        self.category = category
        self.entries = []  # [(коды, [обязательные параметры])]
        self.columns = []
        for rule in rules:
            req = required_params(rule, stage)
            codes = [code for _name, code in rule.get("classes") or [] if code]
            self.entries.append((codes, req))
            for name in req:
                if name not in self.columns:
                    self.columns.append(name)
        # общие — только по классам, которым на этапе что-то требуется
        sets = [set(req) for _codes, req in self.entries if req]
        common = set.intersection(*sets) if sets else set()
        self.fallback = [n for n in self.columns if n in common]

    def required_for(self, element_code):
        """(обязательные параметры или None — не проверять, MATCHED/NO_CODE/
        UNKNOWN)."""
        element_code = _text(element_code or u"").strip()
        if not element_code:
            if len(self.entries) == 1:
                return self.entries[0][1], self.NO_CODE
            return self.fallback, self.NO_CODE
        best, best_len = None, -1
        for codes, req in self.entries:
            for code in codes:
                if code_matches(element_code, code) and len(code) > best_len:
                    best, best_len = req, len(code)
        if best is not None:
            return best, self.MATCHED
        return None, self.UNKNOWN


def plans_for_stage(appendix, stage):
    """[CategoryPlan] по категориям приложения (в порядке появления), только
    с обязательными на этом этапе параметрами."""
    order, by_cat = [], {}
    for rule in (appendix or {}).get("rules") or []:
        key = norm_name(rule.get("category"))
        if not key:
            continue
        if key not in by_cat:
            by_cat[key] = (rule["category"], [])
            order.append(key)
        by_cat[key][1].append(rule)
    plans = []
    for key in order:
        name, rules = by_cat[key]
        plan = CategoryPlan(name, rules, stage)
        if plan.columns:
            plans.append(plan)
    return plans
