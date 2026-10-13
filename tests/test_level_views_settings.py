# -*- coding: utf-8 -*-
"""Тесты для lowlife.level_views_settings — хранение групп видов кнопки
«Виды по уровням» и запасной шаблон имени уровня из «Секущего диапазона»."""

import io
import json
import os

import pytest

from lowlife import level_name_template, level_views_settings as lvs
from lowlife import level_views_core as core


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


def test_empty_settings(appdata):
    values = lvs.get_settings_silent()
    assert values[lvs.GROUPS_KEY] == []
    assert values[lvs.LEVEL_TEMPLATE_KEY] == level_name_template.DEFAULT_TEMPLATE


def test_level_template_falls_back_to_view_range(appdata):
    _write(appdata, "LowLifeViewRange_settings.json", {"level_name_template": u"Этаж {Этаж}"})
    assert lvs.get_settings_silent()[lvs.LEVEL_TEMPLATE_KEY] == u"Этаж {Этаж}"


def test_round_trip_and_remember_choice(appdata):
    group = core.normalize_group({core.G_NAME: u"ЭОМ", core.G_TOP: None})
    lvs.save_values({lvs.GROUPS_KEY: [group], lvs.LEVEL_TEMPLATE_KEY: u"{Этаж}"})
    lvs.remember_choice([u"Этаж 1"], [u"ЭОМ"])
    values = lvs.get_settings_silent()
    assert values[lvs.GROUPS_KEY] == [group]
    assert values[lvs.LEVEL_TEMPLATE_KEY] == u"{Этаж}"
    assert values[lvs.LAST_LEVELS_KEY] == [u"Этаж 1"]
    assert values[lvs.LAST_GROUPS_KEY] == [u"ЭОМ"]


def test_remember_link_choices_merges_and_updates_filter(appdata):
    group = core.normalize_group({core.G_NAME: u"ЭОМ", core.G_LINKS: True})
    lvs.save_values({lvs.GROUPS_KEY: [group]})
    lvs.remember_link_choices({u"ЭОМ": {u"АР.rvt": {u"Этаж 1": u"1 этаж", u"Этаж 2": u""}}},
                              {u"ЭОМ": (core.MODE_STARTS, u"2")})
    lvs.remember_link_choices({u"ЭОМ": {u"АР.rvt": {u"Этаж 2": u"2 этаж"}}}, {})
    values = lvs.get_settings_silent()
    assert values[lvs.LINK_CHOICES_KEY] == {u"ЭОМ": {u"АР.rvt": {u"Этаж 1": u"1 этаж",
                                                                  u"Этаж 2": u"2 этаж"}}}
    g = values[lvs.GROUPS_KEY][0]
    assert (g[core.G_LINK_VIEW_MODE], g[core.G_LINK_VIEW_FILTER]) == (core.MODE_STARTS, u"2")
