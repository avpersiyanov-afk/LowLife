# -*- coding: utf-8 -*-
from lowlife import parking_marks_core as core


def test_is_zone():
    words = core.split_words(u"зона, ЗОНА безопасности")
    assert core.is_zone(u"Зона проезда", words)
    assert core.is_zone(u"тех. ЗОНА", words)
    assert not core.is_zone(u"Машиноместо", words)
    assert not core.is_zone(None, words)
    assert not core.is_zone(u"зона", [])


def test_label():
    assert core.label(u"{h}", 3150.0) == u"+3,150"
    assert core.label(u"Верх зоны {h}", 0.0) == u"Верх зоны ±0,000"
    assert core.label(u"Низ", -1200.0) == u"Низ -1,200"
    assert core.label(u"", 2100.0) == u"+2,100"
    assert core.zone_label(u"Верх {h}", u"Низ {h}", 2500.0, 0.0) == u"Верх +2,500\nНиз ±0,000"


def test_split_template():
    assert core.split_template(u"Верх зоны {h}") == (u"Верх зоны", u"")
    assert core.split_template(u"{h} (низ)") == (u"", u"(низ)")
    assert core.split_template(u"{h}") == (u"", u"")
    assert core.split_template(u"Низ") == (u"Низ", u"")
    assert core.split_template(None) == (u"", u"")


def test_elevation_mm():
    assert core.elevation_mm(5000.0, 1000.0) == 4000.0
    assert core.elevation_mm(5000.0, 1000.0, 150000.0) == 154000.0
    assert core.elevation_mm(0.0, 0.0, None) == 0.0


def test_overlaps():
    assert core.overlaps(0.0, 10.0, 5.0, 20.0)
    assert core.overlaps(0.0, 10.0, None, None)
    assert not core.overlaps(25.0, 30.0, 5.0, 20.0)
    assert not core.overlaps(0.0, 4.0, 5.0, 20.0)
    assert core.overlaps(0.0, 4.0, None, 20.0)
    assert core.overlaps(25.0, 30.0, 5.0, None)
