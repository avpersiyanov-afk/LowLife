# -*- coding: utf-8 -*-
"""
Разбор приложения «Требования к LOI» (таблица Excel, сохранённая как XML —
«Таблица XML 2003», SpreadsheetML) для кнопки «Проверка LOI»
(LOI.panel/CheckLOI, см. loi_check_settings.import_appendix).

Как устроено приложение (по нему и разбор):
  - заголовок таблицы из двух строк, повторяется на каждой странице:
    «Группа элементов | Класс элемента: Элемент (…) / Код (<параметр кода>)
    | Категория элемента в Revit | LOD | Уровень информации (LOI) | Стадия … :
    Подэтап проверки ПЧ / НЧ, …»;
  - строки-заголовки разделов (одна ячейка на всю ширину): дисциплина
    («Слаботочные системы, …») и подраздел («Элементы обязательные к
    моделированию» / «…на усмотрение исполнителя»);
  - элемент: группа и категория Revit (объединённые по вертикали ячейки),
    классы с кодами по классификатору и по строке на параметр LOI; в столбцах
    «Подэтап проверки ПЧ/НЧ» каждой стадии — с какого подэтапа параметр
    обязателен («Б-2», «ПЭ-3»; пусто или «не требуется на стадии …» — не
    требуется).

Имена параметров и категорий берутся из самого файла — в коде их нет
(это соглашения конкретного заказчика, см. CLAUDE.md).

Модуль без Revit API: чтение XML — через xml.etree (CPython, тесты) или
System.Xml (IronPython, если etree недоступен); разбор — на обычных списках,
покрыт tests/test_loi_appendix.py.
"""

import re

try:
    _text = unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3 (тесты)
    _text = str

SS_NS = "urn:schemas-microsoft-com:office:spreadsheet"

GROUP_HEADER = u"Группа элементов"
CATEGORY_HEADER = u"Категория элемента"
LOI_HEADER = u"Уровень информации"
CLASS_SUBHEADER = u"Элемент"
CODE_SUBHEADER = u"Код"
SUBSTAGE_SUBHEADER = u"Подэтап проверки"
STAGE_PREFIX = u"Стадия"
SUBSECTION_PREFIX = u"Элементы "

_LEVEL_RE = re.compile(u"^\\s*([^\\W\\d_]+)\\s*-\\s*(\\d+)\\s*$", re.UNICODE)


def clean(text):
    """Переводы строк и повторные пробелы -> один пробел."""
    return u" ".join(_text(text or u"").split())


# --- чтение SpreadsheetML ------------------------------------------------------

def _rows_etree(path):
    import xml.etree.ElementTree as ET
    ss = u"{%s}" % SS_NS
    root = ET.parse(path).getroot()
    sheet = root.find(ss + u"Worksheet")
    if sheet is None:
        return []
    rows = []
    for row in sheet.iter(ss + u"Row"):
        cells = []
        for c in row.findall(ss + u"Cell"):
            data = c.find(ss + u"Data")
            txt = u"".join(data.itertext()) if data is not None else u""
            cells.append((_int(c.get(ss + u"Index")), _int(c.get(ss + u"MergeAcross")) or 0,
                          _int(c.get(ss + u"MergeDown")) or 0, txt))
        rows.append((_int(row.get(ss + u"Index")), cells))
    return rows


def _rows_dotnet(path):
    import clr
    clr.AddReference("System.Xml")
    from System.Xml import XmlDocument, XmlNamespaceManager
    xml = XmlDocument()
    xml.Load(path)
    ns = XmlNamespaceManager(xml.NameTable)
    ns.AddNamespace("ss", SS_NS)
    sheet = xml.SelectSingleNode("//ss:Worksheet", ns)
    if sheet is None:
        return []

    def attr(node, name):
        a = node.Attributes.GetNamedItem(name, SS_NS)
        return a.Value if a is not None else None

    rows = []
    for row in sheet.SelectNodes(".//ss:Row", ns):
        cells = []
        for c in row.SelectNodes("ss:Cell", ns):
            data = c.SelectSingleNode("ss:Data", ns)
            txt = data.InnerText if data is not None else u""
            cells.append((_int(attr(c, "Index")), _int(attr(c, "MergeAcross")) or 0,
                          _int(attr(c, "MergeDown")) or 0, txt))
        rows.append((_int(attr(row, "Index")), cells))
    return rows


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def read_rows(path):
    """Строки первого листа: [(Index строки или None, [(Index, MergeAcross,
    MergeDown, текст)])]."""
    try:
        return _rows_etree(path)
    except ImportError:
        return _rows_dotnet(path)


def build_grid(rows):
    """
    Сетка значений с учётом объединённых ячеек. Возвращает (values, origins):
    values[r][c] — текст ячейки, для объединённых — текст их левой верхней
    ячейки; origins[r][c] — текст только в самой левой верхней ячейке
    (по ним видно, где начинается новый элемент), в остальных u"".
    """
    values, origins = [], []
    covered = {}  # строка -> {столбец: текст объединения}
    r = 0
    for row_index, cells in rows:
        if row_index:
            while r < row_index - 1:
                values.append(_dense(covered.pop(r, {})))
                origins.append([])
                r += 1
        here = covered.pop(r, {})
        vals, orig = {}, {}
        col = 0
        for index, across, down, txt in cells:
            if index:
                col = index - 1
            else:
                while col in here:
                    col += 1
            for dr in range(down + 1):
                target = here if dr == 0 else covered.setdefault(r + dr, {})
                for dc in range(across + 1):
                    if dr or dc:
                        target[col + dc] = txt
            vals[col] = txt
            orig[col] = txt
            col += across + 1
        for cc, txt in here.items():
            if cc not in vals:
                vals[cc] = txt
        values.append(_dense(vals))
        origins.append(_dense(orig))
        r += 1
    return values, origins


def _dense(cells):
    if not cells:
        return []
    return [cells.get(i, u"") for i in range(max(cells) + 1)]


def _cell(grid, r, c):
    row = grid[r] if r < len(grid) else []
    return clean(row[c]) if c < len(row) else u""


# --- разбор ------------------------------------------------------------------

def parse_level(text):
    """«ПЭ-3» -> (u"ПЭ", 3); пусто/«не требуется…» -> None."""
    m = _LEVEL_RE.match(_text(text or u""))
    if not m:
        return None
    return m.group(1), int(m.group(2))


def clean_category(text):
    """Категория Revit из ячейки приложения: без пояснений в скобках и после
    «Семейство:» (например «Обобщенные модели Семейство: …»)."""
    text = clean(text)
    for sep in (u"(", u" Семейство", u":"):
        i = text.find(sep)
        if i > 0:
            text = text[:i]
    return text.strip(u" ,.;")


def _param_in_parens(text):
    m = re.search(u"\\(([^)]*)\\)", text)
    return clean(m.group(1)) if m else u""


class Layout(object):
    """Номера столбцов таблицы, найденные по заголовку."""

    def __init__(self):
        self.group = self.cls = self.code = self.category = self.loi = None
        self.code_param = u""
        self.class_param = u""
        self.substages = []  # [(столбец, ключ, стадия, часть)]


def find_layout(values, header_row):
    head = values[header_row] if header_row < len(values) else []
    sub = values[header_row + 1] if header_row + 1 < len(values) else []
    lay = Layout()
    for c in range(max(len(head), len(sub))):
        h = _cell(values, header_row, c)
        s = _cell(values, header_row + 1, c)
        if h.startswith(GROUP_HEADER) and lay.group is None:
            lay.group = c
        elif h.startswith(CATEGORY_HEADER) and lay.category is None:
            lay.category = c
        elif h.startswith(LOI_HEADER) and lay.loi is None:
            lay.loi = c
        if s.startswith(CLASS_SUBHEADER) and lay.cls is None:
            lay.cls = c
            lay.class_param = _param_in_parens(s)
        elif s.startswith(CODE_SUBHEADER) and lay.code is None:
            lay.code = c
            lay.code_param = _param_in_parens(s)
        elif s.startswith(SUBSTAGE_SUBHEADER):
            part = clean(s[len(SUBSTAGE_SUBHEADER):])
            stage = h[len(STAGE_PREFIX):].strip() if h.startswith(STAGE_PREFIX) else h
            lay.substages.append((c, u"{}|{}".format(stage, part), stage, part))
    if None in (lay.group, lay.category, lay.loi) or not lay.substages:
        return None
    return lay


def _is_header(values, r):
    return _cell(values, r, 0).startswith(GROUP_HEADER) or any(
        _cell(values, r, c) == GROUP_HEADER for c in range(len(values[r])))


def _title_of(origins, r):
    """Текст строки-заголовка раздела (одна ячейка на строке) или None."""
    row = origins[r] if r < len(origins) else []
    filled = [clean(x) for x in row if clean(x)]
    return filled[0] if len(filled) == 1 and clean(row[0]) else None


def parse(values, origins):
    """
    Разбор сетки build_grid. Возвращает словарь (сохраняется в настройках
    как есть):
      {"code_param": параметр кода по классификатору,
       "columns": [{"key", "stage", "part", "prefix", "levels": [n, …]}],
       "sections": [имена разделов по порядку],
       "rules": [{"section", "subsection", "group", "category",
                  "classes": [[класс, код], …],
                  "params": [{"name", "levels": {ключ столбца: n}}]}]}
    """
    layout = None
    header_row = None
    for r in range(len(values)):
        if values[r] and _is_header(values, r):
            layout = find_layout(values, r)
            header_row = r
            if layout:
                break
    if layout is None:
        raise ValueError(u"Не найден заголовок таблицы требований LOI "
                         u"(«{}», «{}», «Подэтап проверки …»).".format(GROUP_HEADER, LOI_HEADER))

    prefixes, levels = {}, {}
    rules, sections = [], []
    section = subsection = u""
    rule = None
    skip_next = False

    for r in range(header_row, len(values)):
        if skip_next:
            skip_next = False
            continue
        if values[r] and _is_header(values, r):
            skip_next = True
            continue

        title = _title_of(origins, r)
        if title is not None and not _cell(origins, r, layout.loi) \
                and not _cell(origins, r, layout.code):
            if title.startswith(SUBSECTION_PREFIX):
                subsection = title
            else:
                section = title
                subsection = u""
                if section not in sections:
                    sections.append(section)
            rule = None
            continue

        if _cell(origins, r, layout.category) or _cell(origins, r, layout.group):
            rule = {
                "section": section, "subsection": subsection,
                "group": _cell(values, r, layout.group),
                "category": clean_category(_cell(values, r, layout.category)),
                "classes": [], "params": [],
            }
            rules.append(rule)
        if rule is None:
            continue

        code = _cell(origins, r, layout.code) if layout.code is not None else u""
        if code:
            name = _cell(values, r, layout.cls) if layout.cls is not None else u""
            rule["classes"].append([name, code])

        param = _cell(origins, r, layout.loi)
        if param:
            row_levels = {}
            for col, key, _stage, _part in layout.substages:
                lv = parse_level(_cell(values, r, col))
                if lv is not None:
                    prefixes.setdefault(key, lv[0])
                    levels.setdefault(key, set()).add(lv[1])
                    row_levels[key] = lv[1]
            rule["params"].append({"name": param, "levels": row_levels})

    columns = []
    for _col, key, stage, part in layout.substages:
        if key in levels:
            columns.append({"key": key, "stage": stage, "part": part,
                            "prefix": prefixes[key], "levels": sorted(levels[key])})

    rules = [x for x in rules if x["params"] and x["category"]]
    return {
        "code_param": layout.code_param,
        "columns": columns,
        "sections": [s for s in sections if any(x["section"] == s for x in rules)],
        "rules": rules,
    }


def read_appendix(path):
    """Файл приложения -> словарь parse()."""
    values, origins = build_grid(read_rows(path))
    return parse(values, origins)


def select_sections(appendix, section_names):
    """Копия appendix только с правилами выбранных разделов."""
    wanted = set(section_names)
    result = dict(appendix)
    result["rules"] = [x for x in appendix["rules"] if x["section"] in wanted]
    result["sections"] = [s for s in appendix["sections"] if s in wanted]
    return result
