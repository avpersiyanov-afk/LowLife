# -*- coding: utf-8 -*-
"""Тесты для lowlife.level_views_settings — что запоминает окно «Видов по
уровням»: маска, значения шаблонов (дописываются), отмеченные шаблоны."""

import pytest

from lowlife import level_views_settings as lvs
from lowlife import level_views_core as core


@pytest.fixture
def appdata(tmpdir, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmpdir))
    return str(tmpdir)


def test_save_and_load(appdata):
    assert lvs.load()[core.MASK_KEY] == core.DEFAULT_MASK
    lvs.save(u"{Уровень} {Группа вида и назначение}", {u"A": u"Свет"}, [u"A"])
    lvs.save(u"{Уровень}-{Группа вида и назначение}", {u"B": u"Сила"}, [u"B"])
    s = lvs.load()
    assert s[core.MASK_KEY] == u"{Уровень}-{Группа вида и назначение}"
    assert s[core.VALUES_KEY] == {u"A": u"Свет", u"B": u"Сила"}
    assert s[core.CHECKED_KEY] == [u"B"]


def test_level_template_default(appdata):
    tpl = lvs.level_template()
    assert tpl.error is None


def test_align_range_saved(appdata):
    lvs.save(core.DEFAULT_MASK, {}, [], align_range=False)
    assert lvs.load()[core.ALIGN_RANGE_KEY] is False


def test_view_range_configured(appdata):
    from lowlife import view_range_settings as vrs
    assert lvs.view_range_configured() is False
    vrs.save_values({vrs.LEVEL_TEMPLATE_KEY: u"Этаж {Этаж}"})
    assert lvs.view_range_configured() is True
    assert lvs.level_template().template == u"Этаж {Этаж}"
