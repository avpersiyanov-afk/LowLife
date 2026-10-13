# -*- coding: utf-8 -*-
"""
Чистая логика кнопки «Виды по уровням» (Tools.panel/LevelViews), без
Revit API: группы видов из настроек, имя вида по маске, секущий диапазон
группы, выбор вида связанной модели для «По связанному виду».

Группа видов — один словарь настроек (см. GROUP_DEFAULTS): для каждого
выбранного уровня кнопка создаёт по одному виду каждой выбранной группы
(или обновляет уже существующий вид с тем же именем на том же уровне),
называет его по маске, назначает шаблон вида, секущий диапазон и, если
включено, показ связанных моделей «По связанному виду».

Секущий диапазон — смещения в мм; пустое значение (None) — плоскость не
трогается. Секущая плоскость, низ и глубина отсчитываются от уровня вида,
верх — от следующего этажа (как у «Секущего диапазона»; если выше уровней
нет — «Неограниченно»). Глубина без значения при заданном низе — равна
низу (Revit не пускает глубину выше низа).
"""

import re

try:
    _text = unicode  # IronPython / Python 2
except NameError:  # pragma: no cover - CPython 3 (тесты)
    _text = str

MM_IN_FOOT = 304.8

# Подстановки маски имени вида.
TOKEN_LEVEL = u"Уровень"
TOKEN_FLOOR = u"Этаж"
TOKEN_BUILDING = u"Корпус"
TOKEN_COMMENT = u"Комментарий"
TOKEN_ELEVATION = u"Отметка"
TOKEN_GROUP = u"Группа"
TOKENS = (TOKEN_LEVEL, TOKEN_FLOOR, TOKEN_BUILDING, TOKEN_COMMENT,
          TOKEN_ELEVATION, TOKEN_GROUP)

# Подстановки, разрешённые в фильтре имени вида связи (без {Группа}).
LINK_VIEW_TOKENS = (TOKEN_LEVEL, TOKEN_FLOOR, TOKEN_BUILDING, TOKEN_COMMENT,
                    TOKEN_ELEVATION)

_TOKEN_RE = re.compile(u"\\{([^{}]*)\\}", re.UNICODE)

# Ключи группы.
G_NAME = "name"
G_VIEW_TYPE = "view_type"          # имя ViewFamilyType плана; "" — первый тип «План этажа»
G_NAME_MASK = "name_mask"
G_TEMPLATE = "view_template"       # имя шаблона вида; "" — без шаблона
G_TOP = "top_mm"                   # от следующего этажа
G_CUT = "cut_mm"                   # от уровня вида
G_BOTTOM = "bottom_mm"
G_DEPTH = "depth_mm"
G_LINKS = "links_by_linked_view"   # связи «По связанному виду»
G_LINK_FILTER = "link_name_filter"  # какие связи: имя содержит (через запятую)
G_LINK_PICK_DIALOG = "link_view_pick_dialog"  # показывать окно выбора видов связи
G_LINK_VIEW_MODE = "link_view_mode"      # фильтр видов связи: LINK_VIEW_MODES
G_LINK_VIEW_FILTER = "link_view_filter"  # значение фильтра (с подстановками уровня)

RANGE_KEYS = (G_TOP, G_CUT, G_BOTTOM, G_DEPTH)

GROUP_DEFAULTS = {
    G_NAME: u"Планы",
    G_VIEW_TYPE: u"",
    G_NAME_MASK: u"{Уровень}",
    G_TEMPLATE: u"",
    G_TOP: -200.0,
    G_CUT: 1200.0,
    G_BOTTOM: 0.0,
    G_DEPTH: 0.0,
    G_LINKS: False,
    G_LINK_FILTER: u"",
    G_LINK_PICK_DIALOG: False,
    G_LINK_VIEW_MODE: "contains",
    G_LINK_VIEW_FILTER: u"",
}

# Насколько уровень вида связи может отличаться по отметке от уровня вида
# (уровни АР и инженерных разделов часто не совпадают: чистый пол / плита).
MAX_LINK_LEVEL_GAP_MM = 1500.0


def _str(value):
    if value is None:
        return u""
    return value if isinstance(value, _text) else _text(value)


def parse_mm(value):
    """Число мм или None (пусто). ValueError — если это не число."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = _str(value).strip().replace(u",", u".").replace(u"−", u"-")
    if not text:
        return None
    return float(text)


def format_mm(value):
    """Число мм для поля ввода; None — пусто."""
    if value is None:
        return u""
    return u"{:g}".format(float(value))


def normalize_group(raw):
    """Группа из настроек с недостающими/битыми значениями по умолчанию."""
    raw = raw if isinstance(raw, dict) else {}
    group = {}
    for key, default in GROUP_DEFAULTS.items():
        value = raw.get(key, default)
        if key in RANGE_KEYS:
            try:
                value = parse_mm(value)
            except (TypeError, ValueError):
                value = default
        elif key in (G_LINKS, G_LINK_PICK_DIALOG):
            value = bool(value)
        elif key == G_LINK_VIEW_MODE:
            value = value if value in _MODE_KEYS else default
        else:
            value = _str(value).strip() if key != G_NAME_MASK else _str(value)
        group[key] = value
    if not group[G_NAME]:
        group[G_NAME] = GROUP_DEFAULTS[G_NAME]
    if not group[G_NAME_MASK].strip():
        group[G_NAME_MASK] = GROUP_DEFAULTS[G_NAME_MASK]
    return group


def normalize_groups(raw_list):
    """Список групп из настроек (не список — пусто)."""
    if not isinstance(raw_list, (list, tuple)):
        return []
    return [normalize_group(g) for g in raw_list if isinstance(g, dict)]


def unique_group_name(name, taken):
    """name, а если занято — «name (2)», «name (3)», ..."""
    taken = set(taken)
    candidate = name
    i = 2
    while candidate in taken:
        candidate = u"{} ({})".format(name, i)
        i += 1
    return candidate


def mask_tokens(mask):
    return [m.group(1).strip() for m in _TOKEN_RE.finditer(_str(mask))]


def validate_mask(mask, allowed=TOKENS):
    """Текст ошибки маски или None."""
    mask = _str(mask)
    if not mask.strip():
        return u"маска пустая"
    stripped = _TOKEN_RE.sub(u"", mask)
    if u"{" in stripped or u"}" in stripped:
        return u"в маске есть незакрытая фигурная скобка"
    unknown = [t for t in mask_tokens(mask) if t not in allowed]
    if unknown:
        return u"неизвестные подстановки: {} (доступны: {})".format(
            u", ".join(u"{%s}" % t for t in unknown),
            u", ".join(u"{%s}" % t for t in allowed))
    return None


def validate_group(group, existing_names=()):
    """Список ошибок группы (пусто — годится)."""
    errors = []
    if group[G_NAME] in existing_names:
        errors.append(u"группа с именем «{}» уже есть".format(group[G_NAME]))
    mask_error = validate_mask(group[G_NAME_MASK])
    if mask_error:
        errors.append(u"маска имени вида: " + mask_error)
    link_error = validate_link_view_filter(group[G_LINK_VIEW_MODE], group[G_LINK_VIEW_FILTER])
    if link_error:
        errors.append(u"фильтр видов связи: " + link_error)
    return errors


def format_elevation(elevation_mm):
    """Отметка в метрах по-строительному: «+3.300», «-2.700», «±0.000»."""
    meters = round(float(elevation_mm) / 1000.0, 3)
    if abs(meters) < 0.0005:
        return u"±0.000"
    return u"{}{:.3f}".format(u"+" if meters > 0 else u"-", abs(meters))


def level_tokens(level_name, elevation_mm, parsed=None):
    """
    Значения подстановок уровня. parsed — (корпус, этаж, комментарий) из
    level_name_template.parse (корпус/этаж там в нижнем регистре, поэтому
    они берутся заново из имени с исходным регистром) или None.
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


def _original_case(source, lowered):
    """Кусок source, совпадающий с lowered без учёта регистра."""
    if not lowered:
        return u""
    source = _str(source)
    idx = source.lower().find(lowered)
    if idx < 0:
        return lowered
    return source[idx:idx + len(lowered)]


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
    """Имя вида без символов, которые Revit не пускает, и лишних пробелов."""
    name = u"".join(ch for ch in _str(name) if ch not in _FORBIDDEN_NAME_CHARS)
    return u" ".join(name.split())


def build_view_name(group, level_values):
    values = dict(level_values)
    values[TOKEN_GROUP] = group[G_NAME]
    return clean_view_name(apply_mask(group[G_NAME_MASK], values))


# Фильтр видов связи: (ключ, подпись в окне). Значение — одно или несколько
# через запятую (подходит любое; для «Не содержит» — ни одного), без учёта
# регистра, с подстановками уровня ({Этаж}, ...).
MODE_STARTS = "starts"
MODE_CONTAINS = "contains"
MODE_ENDS = "ends"
MODE_NOT_CONTAINS = "not_contains"
MODE_EQUALS = "equals"
MODE_REGEX = "regex"
LINK_VIEW_MODES = (
    (MODE_STARTS, u"Начинается с"),
    (MODE_CONTAINS, u"Содержит"),
    (MODE_ENDS, u"Заканчивается на"),
    (MODE_NOT_CONTAINS, u"Не содержит"),
    (MODE_EQUALS, u"Равно"),
    (MODE_REGEX, u"Регулярное выражение"),
)
_MODE_KEYS = tuple(k for k, _l in LINK_VIEW_MODES)


def mode_label(mode):
    return dict(LINK_VIEW_MODES).get(mode, LINK_VIEW_MODES[1][1])


def mode_by_label(label):
    for key, lbl in LINK_VIEW_MODES:
        if lbl == label:
            return key
    return MODE_CONTAINS


def link_view_filter_value(group, level_values=None):
    """Значение фильтра видов связи с подстановками уровня (если даны)."""
    text = _str(group.get(G_LINK_VIEW_FILTER))
    if level_values:
        text = apply_mask(text, level_values)
    return text.strip()


def validate_link_view_filter(mode, value):
    """Текст ошибки фильтра видов связи или None."""
    if mode not in _MODE_KEYS:
        return u"неизвестный вид фильтра «{}»".format(mode)
    value = _str(value)
    if not value.strip():
        return None
    stripped = _TOKEN_RE.sub(u"", value)
    if u"{" in stripped or u"}" in stripped:
        if mode != MODE_REGEX:
            return u"незакрытая фигурная скобка"
    unknown = [t for t in mask_tokens(value) if t not in LINK_VIEW_TOKENS]
    if mode == MODE_REGEX:
        try:
            re.compile(apply_mask(value, dict((t, u"1") for t in LINK_VIEW_TOKENS)),
                       re.UNICODE | re.IGNORECASE)
        except re.error as ex:
            return u"неверное регулярное выражение: {}".format(ex)
    elif unknown:
        return u"неизвестные подстановки: {} (доступны: {})".format(
            u", ".join(u"{%s}" % t for t in unknown),
            u", ".join(u"{%s}" % t for t in LINK_VIEW_TOKENS))
    return None


def link_view_matches(name, mode, value):
    """
    Подходит ли имя вида связи под фильтр. Пустое значение — подходит всё;
    неверное регулярное выражение — не подходит ничего.
    """
    value = _str(value).strip()
    if not value:
        return True
    name = _str(name)
    if mode == MODE_REGEX:
        try:
            return re.search(value, name, re.UNICODE | re.IGNORECASE) is not None
        except re.error:
            return False
    low = name.lower()
    parts = [p.strip().lower() for p in value.split(u",")]
    parts = [p for p in parts if p]
    if mode == MODE_STARTS:
        return any(low.startswith(p) for p in parts)
    if mode == MODE_ENDS:
        return any(low.endswith(p) for p in parts)
    if mode == MODE_EQUALS:
        return any(low.strip() == p for p in parts)
    if mode == MODE_NOT_CONTAINS:
        return not any(p in low for p in parts)
    return any(p in low for p in parts)


def filter_link_views(candidates, mode, value):
    """Кандидаты [(имя, отметка мм, ...)] под фильтр, по имени."""
    return sorted([c for c in candidates if link_view_matches(c[0], mode, value)],
                  key=lambda c: _str(c[0]).lower())


def default_link_view(candidates, level_z_mm, remembered=None, level_name=None,
                      level_key=None, max_gap_mm=MAX_LINK_LEVEL_GAP_MM):
    """
    Что подставить в список выбора вида связи для уровня: запомненный с
    прошлого раза (если он ещё в списке), иначе подобранный pick_link_view,
    иначе None — «не задавать».
    """
    if remembered:
        for c in candidates:
            if c[0] == remembered:
                return c
    return pick_link_view(candidates, level_z_mm, level_name, level_key, max_gap_mm)[0]


def split_filters(text):
    """«АР, КР» → [«ар», «кр»] — для «имя связи содержит»."""
    parts = [p.strip().lower() for p in _str(text).replace(u";", u",").split(u",")]
    return [p for p in parts if p]


def name_matches_any(name, filters):
    """Пустой список фильтров — подходит всё."""
    if not filters:
        return True
    name = _str(name).lower()
    return any(f in name for f in filters)


def range_plan(group):
    """
    {плоскость: смещение мм} для заданных плоскостей группы:
    "top" (от следующего этажа), "cut", "bottom", "depth" (от уровня вида).
    Глубина без значения при заданном низе — равна низу.
    """
    plan = {}
    for key, plane in ((G_TOP, "top"), (G_CUT, "cut"), (G_BOTTOM, "bottom"),
                       (G_DEPTH, "depth")):
        if group.get(key) is not None:
            plan[plane] = float(group[key])
    if "bottom" in plan and "depth" not in plan:
        plan["depth"] = plan["bottom"]
    return plan


def range_problem(plan, height_mm):
    """
    Почему Revit не примет диапазон (текст) или None. height_mm — от уровня
    вида до следующего этажа (None — выше уровней нет, верх неограничен).
    """
    cut = plan.get("cut")
    bottom = plan.get("bottom")
    depth = plan.get("depth")
    if cut is not None and bottom is not None and bottom > cut:
        return u"низ ({:g} мм) выше секущей плоскости ({:g} мм)".format(bottom, cut)
    if bottom is not None and depth is not None and depth > bottom:
        return u"глубина ({:g} мм) выше низа ({:g} мм)".format(depth, bottom)
    if "top" in plan and height_mm is not None:
        top_abs = float(height_mm) + plan["top"]
        if cut is not None and top_abs <= cut:
            return (u"верх ({:g} мм от уровня) не выше секущей плоскости "
                    u"({:g} мм)".format(top_abs, cut))
    return None


def _norm_level_name(name):
    return u" ".join(_str(name).lower().split())


def _norm_floor(floor):
    """«02» и «2» — один этаж; нечисловые этажи сравниваются как текст."""
    floor = _str(floor).strip().lower()
    digits = floor.lstrip(u"0")
    if floor.isdigit():
        return digits or u"0"
    return floor


def level_match_key(parsed):
    """(корпус, этаж) из level_name_template.parse для сравнения этажей; None — нет."""
    if not parsed:
        return None
    return (_str(parsed[0]).strip().lower(), _norm_floor(parsed[1]))


def pick_link_view(candidates, level_z_mm, level_name=None, level_key=None,
                   max_gap_mm=MAX_LINK_LEVEL_GAP_MM):
    """
    Вид связи для уровня вида — «такой же уровень» в связи.

    candidates — [(имя вида, отметка его уровня в координатах основной
    модели мм, Id, имя его уровня, ключ этажа level_match_key или None)],
    уже отфильтрованные (filter_link_views); последние два поля
    необязательны. Уровень ищется по очереди:
      1. уровень связи с тем же именем, что и уровень вида (без регистра);
      2. тот же корпус и этаж по шаблону имени уровня (level_key);
      3. ближайший по отметке, не дальше max_gap_mm.
    Несколько видов на найденном уровне — первый по имени.

    Возвращает (кандидат или None, пояснение или None).
    """
    pool = list(candidates)
    if not pool:
        return None, u"нет планов под фильтр"

    def first(items, how):
        items = sorted(items, key=lambda c: _str(c[0]).lower())
        note = None
        if len(items) > 1:
            note = u"уровень найден {}, на нём {} планов — взят «{}»".format(
                how, len(items), items[0][0])
        return items[0], note

    if level_name:
        target = _norm_level_name(level_name)
        same = [c for c in pool if len(c) > 3 and _norm_level_name(c[3]) == target]
        if same:
            return first(same, u"по имени")

    if level_key is not None:
        same = [c for c in pool if len(c) > 4 and c[4] is not None and c[4] == level_key]
        if same:
            # У этажа может быть несколько уровней — берётся ближайший по отметке.
            gap = min(abs(c[1] - level_z_mm) for c in same)
            same = [c for c in same if abs(c[1] - level_z_mm) - gap < 1.0]
            return first(same, u"по этажу")

    best_gap = min(abs(c[1] - level_z_mm) for c in pool)
    if best_gap > max_gap_mm:
        return None, (u"нет уровня с тем же именем или этажом, а ближайший план связи "
                      u"на уровне в {:.0f} мм от уровня вида (допустимо до {:.0f} мм)".format(
                          float(best_gap), float(max_gap_mm)))
    same = [c for c in pool if abs(c[1] - level_z_mm) - best_gap < 1.0]
    picked, note = first(same, u"по отметке")
    if note is None and best_gap >= 1.0:
        note = u"уровень найден по отметке, отличается на {:.0f} мм".format(float(best_gap))
    return picked, note


_RANGE_LABELS = {
    G_TOP: u"верх",
    G_CUT: u"секущая плоскость",
    G_BOTTOM: u"низ",
    G_DEPTH: u"глубина",
}


def group_from_form(fields):
    """
    Группа из значений окна настроек: поля диапазона — текст (пусто — не
    менять). Возвращает (группа, [ошибки]); при ошибке в числе поле берётся
    пустым.
    """
    errors = []
    raw = dict(fields)
    for key in RANGE_KEYS:
        try:
            raw[key] = parse_mm(fields.get(key))
        except (TypeError, ValueError):
            errors.append(u"{} — «{}» не число".format(_RANGE_LABELS[key], fields.get(key)))
            raw[key] = None
    group = normalize_group(raw)
    if not _str(fields.get(G_NAME)).strip():
        errors.append(u"не задано имя группы")
    return group, errors


def validate_groups(groups):
    """[(индекс группы, текст ошибки)] по всему списку групп."""
    problems = []
    seen = set()
    for i, group in enumerate(groups):
        for error in validate_group(group, seen):
            problems.append((i, error))
        seen.add(group[G_NAME])
    return problems
