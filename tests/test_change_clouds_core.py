# -*- coding: utf-8 -*-
"""Тесты для lowlife.change_clouds_core — чистая логика кнопки «Внесение
изменений»: маска имени типа, разбор существующих имён, подсказка следующего
номера изменения по шифру, разбор даты «дд.мм.гг»."""

import datetime

from lowlife import change_clouds_core as cc


def test_today_text_uses_dd_mm_yy_mask():
    assert cc.today_text(datetime.datetime(2026, 11, 9)) == u"09.11.26"
    assert cc.today_text(datetime.datetime(2026, 1, 2)) == u"02.01.26"


def test_build_type_name_default_template():
    assert cc.build_type_name(u"", u"ОИ", u"ЭО", 3) == u"ОИ_ЭО_3"
    assert cc.build_type_name(None, u"ОИ", u"ЭО", 1) == u"ОИ_ЭО_1"


def test_build_type_name_custom_template():
    template = u"{family}-{cipher}-{number}изм"
    assert cc.build_type_name(template, u"ОИ", u"ЭО", 12) == u"ОИ-ЭО-12изм"
    # номер приходит строкой — приводится к int
    assert cc.build_type_name(u"", u"ОИ", u"ЭО", u"4") == u"ОИ_ЭО_4"


def test_parse_type_name_round_trip():
    parsed = cc.parse_type_name(u"ОИ_ЭО_3", u"ОИ")
    assert parsed == {u"cipher": u"ЭО", u"number": 3}
    # шифр может содержать подчёркивания
    assert cc.parse_type_name(u"ОИ_Э_М_2", u"ОИ") == {u"cipher": u"Э_М", u"number": 2}


def test_parse_type_name_rejects_foreign_names():
    assert cc.parse_type_name(u"ОИ_ЭО_3", u"Другой") is None       # другой префикс
    assert cc.parse_type_name(u"ОИ_ЭО", u"ОИ") is None            # нет номера
    assert cc.parse_type_name(u"ОИ__3", u"ОИ") is None            # пустой шифр
    assert cc.parse_type_name(u"ОИ_ЭО_X", u"ОИ") is None          # нечисловой номер
    assert cc.parse_type_name(u"ОИ_ЭО_0", u"ОИ") is None          # неположительный номер
    assert cc.parse_type_name(u"ОИ_ЭО_-1", u"ОИ") is None         # отрицательный хвост


def test_suggest_number_takes_max_plus_one_per_cipher():
    rows = [
        {u"cipher": u"ЭО", u"number": 2},
        {u"cipher": u"АР", u"number": 5},
        {u"cipher": u"ЭО", u"number": 7},
    ]
    assert cc.suggest_number(rows, u"ЭО") == 8
    assert cc.suggest_number(rows, u"АР") == 6
    assert cc.suggest_number(rows, u"Новый") == 1
    assert cc.suggest_number([], u"ЭО") == 1


def test_suggest_number_ignores_garbage():
    rows = [{u"cipher": u"ЭО", u"number": u"x"}, {u"cipher": u"ЭО"}]
    assert cc.suggest_number(rows, u"ЭО") == 1


def test_parse_number_accepts_positive_ints_only():
    assert cc.parse_number(u" 12 ") == 12
    assert cc.parse_number(3) == 3
    assert cc.parse_number(u"2.5") is None
    assert cc.parse_number(u"") is None
    assert cc.parse_number(u"0") is None
    assert cc.parse_number(u"-2") is None
    assert cc.parse_number(None) is None


def test_parse_date_normalizes_to_dd_mm_yy():
    assert cc.parse_date(u"9.11.26") == u"09.11.26"
    assert cc.parse_date(u"09.11.2026") == u"09.11.26"
    assert cc.parse_date(u" 1.2.25 ") == u"01.02.25"


def test_parse_date_rejects_invalid():
    assert cc.parse_date(u"") is None
    assert cc.parse_date(u"9.11") is None            # нет года
    assert cc.parse_date(u"32.11.26") is None        # день
    assert cc.parse_date(u"9.13.26") is None         # месяц
    assert cc.parse_date(u"дата") is None
