# -*- coding: utf-8 -*-
"""
Чистая логика кнопки «Виды по уровням» (Tools.panel/LevelViews), без
Revit API: имя вида по маске и сохранённые настройки окна.

Кнопка: в окне отмечаются шаблоны видов, у каждого — своя «Группа вида и
назначение»;
для каждого отмеченного шаблона и каждого уровня модели создаётся план с
этим шаблоном, имя — по общей маске.

Подстановки маски:
  {Уровень}     — имя уровня;
  {Этаж}, {Корпус}, {Комментарий} — части имени уровня по шаблону имени
                  уровня из настроек «Секущего диапазона» (не подходит —
                  пусто);
  {Отметка}     — отметка уровня, «+3.300»;
  {Шаблон}      — имя шаблона вида;
  {Группа вида и назначение} — вписанное в окне для этого шаблона
                  (прежнее имя подстановки {Значение} тоже понимается).
"""

import re

try:
    _text = unicode  # IronPython / Python 2
except NameError:  # pragma: no cover - CPython 3 (тесты)
    _text = str

MM_IN_FOOT = 304.8

TOKEN_LEVEL = u"Уровень"
TOKEN_FLOOR = u"Этаж"
TOKEN_BUILDING = u"Корпус"
TOKEN_COMMENT = u"Комментарий"
TOKEN_ELEVATION = u"Отметка"
TOKEN_TEMPLATE = u"Шаблон"
TOKEN_VALUE = u"Группа вида и назначение"
# Прежнее имя подстановки: в сохранённой маске заменяется на TOKEN_VALUE.
TOKEN_VALUE_OLD = u"Значение"
TOKENS = (TOKEN_LEVEL, TOKEN_FLOOR, TOKEN_BUILDING, TOKEN_COMMENT,
          TOKEN_ELEVATION, TOKEN_TEMPLATE, TOKEN_VALUE)

DEFAULT_MASK = u"{Группа вида и назначение}_{Корпус}_{Этаж}_{Отметка}"
# Прежняя маска по умолчанию: сохранённая без изменений — заменяется новой.
_OLD_DEFAULT_MASK = u"{Уровень}_{Значение}"

# Ключи файла настроек.
MASK_KEY = "name_mask"
VALUES_KEY = "template_values"    # {имя шаблона: значение}
CHECKED_KEY = "checked_templates"  # [имена шаблонов, отмеченных в прошлый раз]
ALIGN_RANGE_KEY = "align_view_range"  # выравнивать секущий диапазон (как «Секущий диапазон»)
PICK_LEVELS_KEY = "pick_levels"        # спрашивать уровни для каждого шаблона
TEMPLATE_LEVELS_KEY = "template_levels"  # {имя шаблона: [имена уровней, выбранных в прошлый раз]}

_TOKEN_RE = re.compile(u"\\{([^{}]*)\\}", re.UNICODE)


def _str(value):
    if value is None:
        return u""
    return value if isinstance(value, _text) else _text(value)


def normalize_settings(saved):
    """Настройки окна из файла; битые значения — по умолчанию."""
    saved = saved if isinstance(saved, dict) else {}
    mask = _str(saved.get(MASK_KEY))
    if validate_mask(mask) or mask == _OLD_DEFAULT_MASK:
        mask = DEFAULT_MASK
    mask = upgrade_mask(mask)
    values = saved.get(VALUES_KEY)
    values = values if isinstance(values, dict) else {}
    checked = saved.get(CHECKED_KEY)
    checked = checked if isinstance(checked, (list, tuple)) else []
    return {
        MASK_KEY: mask,
        VALUES_KEY: dict((_str(k), _str(v)) for k, v in values.items()
                         if isinstance(v, (_text, str))),
        CHECKED_KEY: [_str(n) for n in checked if isinstance(n, (_text, str))],
        ALIGN_RANGE_KEY: bool(saved.get(ALIGN_RANGE_KEY, True)),
        PICK_LEVELS_KEY: bool(saved.get(PICK_LEVELS_KEY, False)),
        TEMPLATE_LEVELS_KEY: _template_levels(saved.get(TEMPLATE_LEVELS_KEY)),
    }


def _template_levels(value):
    """{шаблон: [уровни]} из файла — битые части отбрасываются."""
    if not isinstance(value, dict):
        return {}
    result = {}
    for name, levels in value.items():
        if isinstance(levels, (list, tuple)):
            result[_str(name)] = [_str(l) for l in levels if isinstance(l, (_text, str))]
    return result


def preselected_levels(all_names, remembered):
    """
    Какие уровни отметить в списке выбора: выбранные в прошлый раз (если
    шаблон уже спрашивали), иначе все.
    """
    if remembered is None:
        return list(all_names)
    remembered = set(remembered)
    return [n for n in all_names if n in remembered]


def upgrade_mask(mask):
    """{Значение} → {Группа вида и назначение} (прежнее имя подстановки)."""
    return _str(mask).replace(u"{%s}" % TOKEN_VALUE_OLD, u"{%s}" % TOKEN_VALUE)


def validate_mask(mask):
    """Текст ошибки маски или None."""
    mask = _str(mask)
    if not mask.strip():
        return u"маска пустая"
    if u"{" in _TOKEN_RE.sub(u"", mask) or u"}" in _TOKEN_RE.sub(u"", mask):
        return u"в маске есть незакрытая фигурная скобка"
    unknown = [m.group(1).strip() for m in _TOKEN_RE.finditer(mask)
               if m.group(1).strip() not in TOKENS + (TOKEN_VALUE_OLD,)]
    if unknown:
        return u"неизвестные подстановки: {} (доступны: {})".format(
            u", ".join(u"{%s}" % t for t in unknown),
            u", ".join(u"{%s}" % t for t in TOKENS))
    return None


def split_values(text):
    """
    Группы вида и назначения шаблона — по одной на строке (пустые строки
    отбрасываются). Ничего не вписано — [""]: один вид без этой части имени.
    """
    lines = [l.strip() for l in _str(text).replace(u"\r", u"\n").split(u"\n")]
    return [l for l in lines if l] or [u""]


def join_values(values):
    """Список групп → текст для поля ввода и файла настроек."""
    return u"\n".join(v for v in values if v)


def mask_warning(mask, pairs):
    """
    Предупреждение (не ошибка) о совпадающих именах: без {Уровень}/{Этаж}/
    {Отметка} — у видов разных уровней; одинаковые имена у видов одного
    уровня — у пар (имя шаблона, группа вида и назначение) из pairs.
    """
    tokens = set(m.group(1).strip() for m in _TOKEN_RE.finditer(_str(mask)))
    if not tokens & set((TOKEN_LEVEL, TOKEN_FLOOR, TOKEN_ELEVATION)):
        return u"в маске нет {Уровень} — у видов разных уровней совпадут имена"
    stub = dict((t, u"x") for t in (TOKEN_LEVEL, TOKEN_FLOOR, TOKEN_BUILDING,
                                    TOKEN_COMMENT, TOKEN_ELEVATION))
    names = [build_view_name(mask, stub, t, v) for t, v in pairs]
    if len(set(names)) < len(names):
        return (u"у некоторых видов одного уровня совпадут имена — проверьте, что в маске "
                u"есть {Группа вида и назначение} (и {Шаблон}, если группы у шаблонов "
                u"повторяются), а группы у шаблона не повторяются")
    return None


def format_elevation(elevation_mm):
    """Отметка в метрах по-строительному: «+3.300», «-2.700», «±0.000»."""
    meters = round(float(elevation_mm) / 1000.0, 3)
    if abs(meters) < 0.0005:
        return u"±0.000"
    return u"{}{:.3f}".format(u"+" if meters > 0 else u"-", abs(meters))


def _original_case(source, lowered):
    """Кусок source, совпадающий с lowered без учёта регистра."""
    if not lowered:
        return u""
    source = _str(source)
    idx = source.lower().find(lowered)
    if idx < 0:
        return lowered
    return source[idx:idx + len(lowered)]


def level_tokens(level_name, elevation_mm, parsed=None):
    """
    Подстановки уровня. parsed — (корпус, этаж, комментарий) из
    level_name_template.parse (корпус/этаж там в нижнем регистре — берутся
    из имени с исходным регистром) или None.
    """
    values = {
        TOKEN_LEVEL: _str(level_name),
        TOKEN_ELEVATION: format_elevation(elevation_mm),
        TOKEN_FLOOR: u"",
        TOKEN_BUILDING: u"",
        TOKEN_COMMENT: u"",
    }
    if parsed is not None:
        building, floor, comment = parsed
        values[TOKEN_BUILDING] = _original_case(level_name, building)
        values[TOKEN_FLOOR] = _original_case(level_name, floor)
        values[TOKEN_COMMENT] = _str(comment)
    return values


def apply_mask(mask, values):
    """Подставляет {Имя} из values; неизвестные подстановки остаются как есть."""
    def repl(m):
        key = m.group(1).strip()
        if key in values:
            return _str(values[key])
        return m.group(0)
    return _TOKEN_RE.sub(repl, _str(mask))


_FORBIDDEN_NAME_CHARS = u"\\:{}[]|;<>?`~"


def clean_view_name(name):
    """Имя вида без символов, которые Revit не пускает, и лишних пробелов/«_»."""
    name = u"".join(ch for ch in _str(name) if ch not in _FORBIDDEN_NAME_CHARS)
    name = u" ".join(name.split())
    # Пустая подстановка между разделителями: «02__Свет» → «02_Свет».
    name = re.sub(u"_{2,}", u"_", name)
    return name.strip(u" _")


def build_view_name(mask, level_values, template_name, value):
    values = dict(level_values)
    values[TOKEN_TEMPLATE] = _str(template_name)
    values[TOKEN_VALUE] = _str(value)
    values[TOKEN_VALUE_OLD] = _str(value)
    return clean_view_name(apply_mask(mask, values))
