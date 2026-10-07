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
        """statuses — список FILLED/EMPTY/ABSENT в порядке rows. Возвращает
        True, если у элемента есть хоть один незаполненный параметр."""
        self.total += 1
        bad = False
        for st, status in zip(self.stats, statuses):
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
    """Текст ячейки отчёта: значение, «—» для пустого, «нет параметра»."""
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
