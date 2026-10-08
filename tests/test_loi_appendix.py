# -*- coding: utf-8 -*-
"""Тесты разбора приложения «Требования к LOI» (lowlife/loi_appendix.py) и
этапов проверки (loi_check_core: Stage/CategoryPlan) — кнопка «Проверка LOI».
Таблица синтетическая, в том же формате (SpreadsheetML, объединённые ячейки)."""
import io

from lowlife import loi_appendix as A
from lowlife import loi_check_core as core

HEAD = (
    u'<Row><Cell ss:MergeDown="1"><Data ss:Type="String">Группа элементов</Data></Cell>'
    u'<Cell><Data ss:Type="String">Класс элемента</Data></Cell><Cell/>'
    u'<Cell ss:MergeDown="1"><Data ss:Type="String">Категория элемента в Revit</Data></Cell>'
    u'<Cell ss:MergeDown="1"><Data ss:Type="String">Уровень информации (LOI)</Data></Cell>'
    u'<Cell ss:MergeAcross="1"><Data ss:Type="String">Стадия П</Data></Cell>'
    u'<Cell ss:MergeAcross="1"><Data ss:Type="String">Стадия Р</Data></Cell></Row>'
    u'<Row><Cell ss:Index="2"><Data ss:Type="String">Элемент (Описание)</Data></Cell>'
    u'<Cell><Data ss:Type="String">Код (Код класса)</Data></Cell>'
    u'<Cell ss:Index="6"><Data ss:Type="String">Подэтап проверки ПЧ</Data></Cell>'
    u'<Cell><Data ss:Type="String">Подэтап проверки НЧ</Data></Cell>'
    u'<Cell><Data ss:Type="String">Подэтап проверки ПЧ</Data></Cell>'
    u'<Cell><Data ss:Type="String">Подэтап проверки НЧ</Data></Cell></Row>'
)


def _title(text):
    return (u'<Row><Cell ss:MergeAcross="8"><Data ss:Type="String">{}</Data></Cell></Row>'
            .format(text))


def _row(cells):
    out = []
    for c in cells:
        if c is None:
            out.append(u'<Cell/>')
        elif isinstance(c, tuple):
            attrs, txt = c
            out.append(u'<Cell {}><Data ss:Type="String">{}</Data></Cell>'.format(attrs, txt))
        else:
            out.append(u'<Cell><Data ss:Type="String">{}</Data></Cell>'.format(c))
    return u'<Row>' + u''.join(out) + u'</Row>'


BODY = (
    HEAD
    + _title(u"Раздел А")
    + _title(u"Элементы обязательные к моделированию")
    # элемент 1: два класса, категория с пояснением; П не требуется (объединено)
    + _row([(u'ss:MergeDown="2"', u"Шкафы"), u"Шкаф", u"X.10.05",
            (u'ss:MergeDown="2"', u"Оборудование Семейство: любое"), u"P_Код",
            (u'ss:MergeAcross="1" ss:MergeDown="2"', u"не требуется на стадии П"),
            u"ПЭ-1", u"ПЭ-3"])
    + _row([(u'ss:Index="2"', u"Пульт"), u"X.10.15", (u'ss:Index="5"', u"P_Марка"),
            (u'ss:Index="8"', u"ПЭ-2"), u"ПЭ-4"])
    + _row([(u'ss:Index="5"', u"P_Ширина\nшкафа"), (u'ss:Index="8"', u""), u"ПЭ-2"])
    # элемент 2: та же категория, другой класс
    + _row([(u'ss:MergeDown="1"', u"Датчики"), u"Датчик", u"X.20",
            (u'ss:MergeDown="1"', u"Оборудование"), u"P_Код", u"Б-2", u"Б-3",
            (u'ss:MergeDown="1"', u"ПЭ-1"), u"ПЭ-1"])
    + _row([(u'ss:Index="5"', u"P_Марка"), u"", u"Б-1", (u'ss:Index="9"', u"ПЭ-2")])
    + HEAD
    + _title(u"Раздел Б")
    + _row([u"Лотки", u"Лоток", u"Y.01", u"Лотки", u"P_Код", u"Б-1", u"Б-1", u"ПЭ-1", u"ПЭ-1"])
)

XML = (
    u'<?xml version="1.0" encoding="UTF-8"?>'
    u'<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" '
    u'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">'
    u'<Worksheet ss:Name="Table 1"><Table>' + BODY + u'</Table></Worksheet></Workbook>'
)


def _appendix(tmp_path):
    path = tmp_path / "loi.xml"
    with io.open(str(path), "w", encoding="utf-8") as f:
        f.write(XML)
    return A.read_appendix(str(path))


def test_build_grid_merges():
    rows = [(None, [(None, 1, 1, u"A"), (None, 0, 0, u"B")]),
            (None, [(None, 0, 0, u"C")])]
    values, origins = A.build_grid(rows)
    assert values == [[u"A", u"A", u"B"], [u"A", u"A", u"C"]]
    assert origins == [[u"A", u"", u"B"], [u"", u"", u"C"]]


def test_parse_level_and_category():
    assert A.parse_level(u"ПЭ-3") == (u"ПЭ", 3)
    assert A.parse_level(u" Б - 2 ") == (u"Б", 2)
    assert A.parse_level(u"не требуется на стадии П") is None
    assert A.parse_level(u"") is None
    assert A.clean_category(u"Обобщенные модели Семейство: Единое") == u"Обобщенные модели"
    assert A.clean_category(u"Стены (Сист. семейство)") == u"Стены"


def test_parse_structure(tmp_path):
    ap = _appendix(tmp_path)
    assert ap["code_param"] == u"Код класса"
    assert ap["sections"] == [u"Раздел А", u"Раздел Б"]
    assert [(c["key"], c["prefix"], c["levels"]) for c in ap["columns"]] == [
        (u"П|ПЧ", u"Б", [1, 2]), (u"П|НЧ", u"Б", [1, 3]),
        (u"Р|ПЧ", u"ПЭ", [1, 2]), (u"Р|НЧ", u"ПЭ", [1, 2, 3, 4])]
    r1, r2, r3 = ap["rules"]
    assert r1["category"] == u"Оборудование"
    assert r1["subsection"] == u"Элементы обязательные к моделированию"
    assert r1["classes"] == [[u"Шкаф", u"X.10.05"], [u"Пульт", u"X.10.15"]]
    assert [p["name"] for p in r1["params"]] == [u"P_Код", u"P_Марка", u"P_Ширина шкафа"]
    assert r1["params"][0]["levels"] == {u"Р|ПЧ": 1, u"Р|НЧ": 3}
    assert r1["params"][2]["levels"] == {u"Р|НЧ": 2}
    assert r2["group"] == u"Датчики"
    # «ПЭ-1» объединено по вертикали — действует и на вторую строку
    assert r2["params"][1]["levels"] == {u"П|НЧ": 1, u"Р|ПЧ": 1, u"Р|НЧ": 2}
    assert r3["section"] == u"Раздел Б"


def test_select_sections(tmp_path):
    ap = A.select_sections(_appendix(tmp_path), [u"Раздел Б"])
    assert ap["sections"] == [u"Раздел Б"]
    assert [r["category"] for r in ap["rules"]] == [u"Лотки"]


def test_stages_and_plans(tmp_path):
    ap = _appendix(tmp_path)
    titles = [s.title for s in core.list_stages(ap)]
    assert titles[0] == u"П · ПЧ · Б-1"
    assert u"Р · НЧ · ПЭ-3" in titles
    stage = core.find_stage(ap, u"Р · НЧ · ПЭ-3")
    plans = core.plans_for_stage(A.select_sections(ap, [u"Раздел А"]), stage)
    assert [p.category for p in plans] == [u"Оборудование"]
    plan = plans[0]
    assert plan.columns == [u"P_Код", u"P_Ширина шкафа", u"P_Марка"]
    assert plan.required_for(u"X.10.05") == ([u"P_Код", u"P_Ширина шкафа"], plan.MATCHED)
    assert plan.required_for(u"X.10.05.77")[1] == plan.MATCHED
    assert plan.required_for(u"X.20") == ([u"P_Код", u"P_Марка"], plan.MATCHED)
    assert plan.required_for(u"") == ([u"P_Код"], plan.NO_CODE)
    assert plan.required_for(u"Z.99") == (None, plan.UNKNOWN)


def test_stage_without_requirements_is_skipped(tmp_path):
    ap = A.select_sections(_appendix(tmp_path), [u"Раздел А"])
    stage = core.find_stage(ap, u"П · ПЧ · Б-1")
    assert core.plans_for_stage(ap, stage) == []


def test_code_matches():
    assert core.code_matches(u"A.05.10", u"A.05")
    assert not core.code_matches(u"A.050", u"A.05")
    assert not core.code_matches(u"", u"A.05")
