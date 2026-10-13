# -*- coding: utf-8 -*-
"""Тесты для lowlife.param_autocomplete — чистая логика контекстного поиска
имён параметров в окнах настроек (ранжирование, имя под кареткой,
подстановка). Сбор имён из модели и WPF-подсказка вне Revit не проверяются."""

from lowlife import param_autocomplete as pa

NAMES = [u"Адрес устройства", u"ADSK_Марка", u"Марка", u"Длина проводника",
         u"Длина проводника в лотке", u"Этаж", u"Номер помещения", u"Объём"]


def test_spec_for_key():
    assert pa.spec_for_key("addr_param_name") == pa.SINGLE
    assert pa.spec_for_key("circuit_panel_param") == pa.SINGLE
    assert pa.spec_for_key("offset_param_names") == pa.LIST
    assert pa.spec_for_key("load_name_source_params") == pa.LIST
    assert pa.spec_for_key("param_names_text") == pa.LIST
    assert pa.spec_for_key("route_param_value") is None
    assert pa.spec_for_key("room_mask") is None
    assert pa.spec_for_key(None) is None


def test_rank_order_and_case():
    # точное, начало имени, начало слова, вхождение
    assert pa.rank(NAMES, u"марка") == [u"Марка", u"ADSK_Марка"]
    assert pa.rank(NAMES, u"длина") == [u"Длина проводника", u"Длина проводника в лотке"]
    assert pa.rank(NAMES, u"лотк") == [u"Длина проводника в лотке"]
    assert pa.rank(NAMES, u"дрес") == [u"Адрес устройства"]


def test_rank_yo_and_words():
    assert pa.rank(NAMES, u"объем") == [u"Объём"]
    assert pa.rank(NAMES, u"помещ номер") == [u"Номер помещения"]
    assert pa.rank(NAMES, u"нет такого") == []


def test_rank_empty_query_all_sorted_and_limit():
    assert pa.rank(NAMES, u"") == sorted(NAMES, key=pa.normalize)
    assert len(pa.rank(NAMES, u"", limit=3)) == 3


def test_token_span_single():
    text = u"  Марка "
    assert pa.current_token(text, 4) == u"Марка"
    assert pa.token_span(text, 4) == (2, 7)


def test_token_span_list():
    text = u"Этаж, Мар, Секция"
    assert pa.current_token(text, 9, pa.LIST) == u"Мар"
    assert pa.current_token(text, 2, pa.LIST) == u"Этаж"
    assert pa.current_token(u"Этаж\nМар", 8, pa.LIST) == u"Мар"


def test_token_span_after_mark():
    spec = (u";", u"=")
    text = u"A=Этаж; B=Сек"
    assert pa.current_token(text, len(text), spec) == u"Сек"
    # каретка на букве до «=» — не имя параметра
    assert pa.token_span(text, 9, spec) is None
    assert pa.token_span(u"A", 1, spec) is None


def test_replace_token_single_and_list():
    assert pa.replace_token(u"мар", 3, u"Марка") == (u"Марка", 5)
    text, caret = pa.replace_token(u"Этаж, Мар, Секция", 9, u"Марка", pa.LIST)
    assert text == u"Этаж, Марка, Секция"
    assert caret == 11
    # после запятой без пробела — добавляется пробел
    assert pa.replace_token(u"Этаж,", 5, u"Марка", pa.LIST) == (u"Этаж, Марка", 11)


def test_replace_token_pairs():
    spec = (u";", u"=")
    assert pa.replace_token(u"A=Эт; B=", 8, u"Секция", spec) == (u"A=Эт; B=Секция", 14)
    assert pa.replace_token(u"A=Эт", 3, u"Этаж", spec) == (u"A=Этаж", 6)
    assert pa.replace_token(u"A", 1, u"Этаж", spec) is None
    # «Источник=Приёмник» — обе стороны имена
    pair_spec = (u",=", None)
    assert pa.replace_token(u"Марка=Ма", 8, u"Марка", pair_spec) == (u"Марка=Марка", 11)


def test_rank_wrong_keyboard_layout():
    # «марка» в английской раскладке, «ADSK» в русской
    assert pa.rank(NAMES, u"vfhrf") == [u"Марка", u"ADSK_Марка"]
    assert pa.rank(NAMES, u"фвыл") == [u"ADSK_Марка"]
    assert pa.rank(NAMES, u"J,]`v") == [u"Объём"]
    # совпадение в набранной раскладке выше, чем в другой
    names = [u"Cnf", u"Стандарт"]
    assert pa.rank(names, u"cnf") == [u"Cnf", u"Стандарт"]


def test_rule_for_key():
    assert pa.rule_for_key("addr_param_name") == ("params", pa.SINGLE, None)
    assert pa.rule_for_key("offset_param_names") == ("params", pa.LIST, None)
    assert pa.rule_for_key("room_mask") == ("params", pa.MASK, None)
    assert pa.rule_for_key("schematic_view_name")[0] == "views"
    assert pa.rule_for_key("view_name_prefixes") == ("view_prefixes", pa.LIST, None)
    assert pa.rule_for_key("family_filter")[0] == "families"
    assert pa.rule_for_key("circuit_system_type")[0] == "system_types"
    assert pa.rule_for_key("cabinet_category_name") == (
        "lines_of", pa.SINGLE, "schematic_device_categories_text")
    assert pa.rule_for_key("route_param_value_riser") == (
        "values_of", pa.SINGLE, "route_param_name")
    assert pa.rule_for_key("install_tray_key")[2] == "cable_param_name"
    # ключевые слова и маска маркировки из букв — без подсказки
    assert pa.rule_for_key("workset_filter_key") is None
    assert pa.rule_for_key("address_mask") is None


def test_mask_tokens():
    text = u"Имя (Ном)"
    assert pa.current_token(text, 8, pa.MASK) == u"Ном"
    assert pa.replace_token(text, 8, u"Номер", pa.MASK) == (u"Имя (Номер)", 10)
    assert pa.replace_token(u"Имя,", 4, u"Номер", pa.MASK) == (u"Имя, Номер", 10)
    assert pa.current_token(u"Им (Номер)", 2, pa.MASK) == u"Им"


def test_text_lines_and_view_prefix():
    assert pa.text_lines(u"Шкаф\r\n Розетка \n\nШкаф") == [u"Шкаф", u"Розетка"]
    assert pa.text_lines(None) == []
    assert pa.view_name_prefix(u"20_План 3 этажа") == u"20"
    assert pa.view_name_prefix(u"1 Этаж") == u"1"
    assert pa.view_name_prefix(u"План") == u"План"
    assert pa.view_name_prefix(u"") == u""


class _Box(object):
    def __init__(self, text):
        self.Text = text


def test_dependent_sources_from_boxes_and_values():
    boxes = {"schematic_device_categories_text": _Box(u"Шкаф\nРозетка")}
    source = pa.source_for_rule(pa.rule_for_key("cabinet_category_name"), None, boxes, {})
    assert source.names() == [u"Шкаф", u"Розетка"]
    boxes["schematic_device_categories_text"].Text = u"Панель"
    assert source.names() == [u"Панель"]
    # поля-зависимости нет в окне — берётся из сохранённых настроек
    source = pa.source_for_rule(pa.rule_for_key("cabinet_category_name"), None, {},
                                {"schematic_device_categories_text": u"Пульт"})
    assert source.names() == [u"Пульт"]


def test_params_rule_uses_window_source():
    params = pa.NameSource(names=[u"Марка"])
    assert pa.source_for_rule(pa.rule_for_key("room_mask"), params) is params
