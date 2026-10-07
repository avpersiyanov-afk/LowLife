# -*- coding: utf-8 -*-
"""Тесты для lowlife.cable_tray_settings — настройки кнопок «Лоток ...»:
своя подстрока типа у каждой кнопки и общий рабочий набор в одном файле."""

import pytest

from lowlife import cable_tray_settings as cts


@pytest.fixture
def appdata(tmpdir, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmpdir))
    return str(tmpdir)


def _sb():
    return cts.button_settings("TrayLadder", "TraySB", u"Лоток СБ (Лестничный лоток)", u"СБ_ЛЛ_1.5_СЦ")


def _ss():
    return cts.button_settings("TrayLadder", "TraySS", u"Лоток СС (Лестничный лоток)", u"СС_ЛЛ_1.5_СЦ")


def test_defaults_are_the_former_hardcoded_values(appdata):
    values = _sb().get_settings_silent()
    assert values == {
        "tray_type_TrayLadder_TraySB": u"СБ_ЛЛ_1.5_СЦ",
        "workset_filter": u"КНК",
    }


def test_type_is_per_button_and_workset_is_shared(appdata):
    sb, ss = _sb(), _ss()
    sb.save_values({"tray_type_TrayLadder_TraySB": u"Мой_лоток", "workset_filter": u"Лотки"})

    assert sb.get_settings_silent()["tray_type_TrayLadder_TraySB"] == u"Мой_лоток"
    # тип другой кнопки не тронут, рабочий набор — общий
    assert ss.get_settings_silent() == {
        "tray_type_TrayLadder_TraySS": u"СС_ЛЛ_1.5_СЦ",
        "workset_filter": u"Лотки",
    }


def test_saving_one_button_keeps_other_buttons_values(appdata):
    sb, ss = _sb(), _ss()
    ss.save_values({"tray_type_TrayLadder_TraySS": u"Другой"})
    sb.save_values({"tray_type_TrayLadder_TraySB": u"Мой_лоток", "workset_filter": u"КНК"})
    assert ss.get_settings_silent()["tray_type_TrayLadder_TraySS"] == u"Другой"


def test_same_button_name_on_different_panels_gets_different_keys():
    assert cts.tray_type_key("TrayLadder", "TraySB") != cts.tray_type_key("TrayRoof", "TraySB")
