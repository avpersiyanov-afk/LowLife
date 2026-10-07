# -*- coding: utf-8 -*-
"""Тесты для lowlife.cable_tray_settings — общее окно настроек всех кнопок
«Лоток ...»: рабочий набор и подстроки типов 20 кнопок в одном файле."""

import os

import pytest

from lowlife import cable_tray_settings as cts

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def appdata(tmpdir, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmpdir))
    return str(tmpdir)


def test_defaults_are_the_former_hardcoded_values(appdata):
    values = cts.get_settings_silent()
    assert len(values) == 1 + 5 * 4
    assert values["workset_filter"] == u"КНК"
    assert values["tray_type_TrayLadder_TraySB"] == u"СБ_ЛЛ_1.5_СЦ"
    assert values["tray_type_TrayRoof_TraySPZo"] == u"СПЗо_ЛП_1.5_ГЦ"
    assert values["tray_type_TrayWire_TraySS"] == u"СС_ЛВ_1.5_СЦ"


def test_every_catalog_entry_has_a_button_folder():
    for panel, _title, _suffix in cts.PANELS:
        for button, _system in cts.SYSTEMS:
            folder = os.path.join(_ROOT, "LowLife.tab", panel + ".panel", button + ".pushbutton")
            assert os.path.isdir(folder), folder


def test_saved_values_override_defaults_and_keep_the_rest(appdata):
    cts.save_values({"tray_type_TrayLadder_TraySB": u"Мой_лоток", "workset_filter": u"Лотки"})
    values = cts.get_settings_silent()
    assert values["tray_type_TrayLadder_TraySB"] == u"Мой_лоток"
    assert values["workset_filter"] == u"Лотки"
    assert values["tray_type_TrayLadder_TraySS"] == u"СС_ЛЛ_1.5_СЦ"


def test_missing_reports_empty_fields(appdata):
    values = cts.get_settings_silent()
    values["tray_type_TrayLadder_TraySB"] = u"  "
    assert cts.missing(values, ["tray_type_TrayLadder_TraySB", "workset_filter"]) == \
        [u"Лоток СБ — часть имени типа"]


def test_button_title_and_keys():
    assert cts.button_title("TrayRoof", "TraySB") == u"Лоток СБ (Лотки на кровле)"
    assert cts.tray_type_key("TrayLadder", "TraySB") != cts.tray_type_key("TrayRoof", "TraySB")
