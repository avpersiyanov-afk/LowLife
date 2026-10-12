# -*- coding: utf-8 -*-
"""Тесты для lowlife.view_range_settings — шаблон имени уровня кнопки
«Секущий диапазон»: проверка при сохранении/загрузке и запасной шаблон из
настроек «Разреза по семейству»."""

import io
import json
import os

import pytest

from lowlife import level_name_template, view_range_settings as vrs


@pytest.fixture
def appdata(tmpdir, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmpdir))
    return str(tmpdir)


def _write(appdata, name, data):
    folder = os.path.join(appdata, "pyRevit")
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with io.open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False))


def test_default_template_when_nothing_saved(appdata):
    values = vrs.get_settings_silent()
    assert values[vrs.LEVEL_TEMPLATE_KEY] == level_name_template.DEFAULT_TEMPLATE


def test_falls_back_to_family_section_template(appdata):
    _write(appdata, "LowLifeFamilySection_settings.json",
           {"level_name_template": u"{Корпус}-{Этаж}"})
    assert vrs.get_settings_silent()[vrs.LEVEL_TEMPLATE_KEY] == u"{Корпус}-{Этаж}"


def test_own_template_wins_over_family_section(appdata):
    _write(appdata, "LowLifeFamilySection_settings.json",
           {"level_name_template": u"{Корпус}-{Этаж}"})
    vrs.save_values({vrs.LEVEL_TEMPLATE_KEY: u"Этаж {Этаж}"})
    assert vrs.get_settings_silent()[vrs.LEVEL_TEMPLATE_KEY] == u"Этаж {Этаж}"


def test_broken_saved_template_gives_default(appdata):
    _write(appdata, "LowLifeViewRange_settings.json",
           {"level_name_template": u"{Корпус}"})
    assert (vrs.get_settings_silent()[vrs.LEVEL_TEMPLATE_KEY]
            == level_name_template.DEFAULT_TEMPLATE)


def test_form_rejects_invalid_template(appdata):
    values, errors = vrs.SETTINGS.parse_form({vrs.LEVEL_TEMPLATE_KEY: u"{Корпус}_"})
    assert values == {} and len(errors) == 1


def test_form_accepts_and_trims_valid_template(appdata):
    values, errors = vrs.SETTINGS.parse_form({vrs.LEVEL_TEMPLATE_KEY: u"  Этаж {Этаж} "})
    assert errors == [] and values == {vrs.LEVEL_TEMPLATE_KEY: u"Этаж {Этаж}"}
