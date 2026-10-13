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
