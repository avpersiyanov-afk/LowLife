# -*- coding: utf-8 -*-
from lowlife import parking_marks_core as core


def _words():
    return [(g.key, core.split_words(g.words)) for g in core.GROUPS]


def test_classify_by_comment_workset_family():
    words = _words()
    # зона светильников: в комментарии есть и «проезд» — побеждает первая группа
    assert core.classify(u"Зона светильников в зоне проезда | 2_Зона прокладки светильников",
                         words) == "lights"
    assert core.classify(u"2_Проезды | Парковка: Проезд", words) == "drive"
    assert core.classify(u"СО | 2_Технологические решения | SMNX_Р_т_Машиноместо: Элит_L",
                         words) == "parking"
    assert core.classify(u"Что-то ещё", words) is None
    assert core.classify(u"проезд", [("lights", []), ("drive", [u"проезд"])]) == "drive"


def test_label():
    assert core.label(u"Проезд: верх {top}", 2450.0, 0.0) == u"Проезд: верх +2,450"
    assert core.label(u"Светильники: низ {bottom}, верх {top}", 3200.0, 2800.0) == \
        u"Светильники: низ +2,800, верх +3,200"
    assert core.label(u"{h}", 0.0, -100.0) == u"±0,000"
    assert core.label(u"Верх", 2100.0, 0.0) == u"Верх +2,100"
    assert core.label(u"", -1200.0, 0.0) == u"-1,200"


def test_overlaps():
    assert core.overlaps(0.0, 10.0, 5.0, 20.0)
    assert core.overlaps(0.0, 10.0, None, None)
    assert not core.overlaps(25.0, 30.0, 5.0, 20.0)
    assert not core.overlaps(0.0, 4.0, 5.0, 20.0)
    assert core.overlaps(0.0, 4.0, None, 20.0)
    assert core.overlaps(25.0, 30.0, 5.0, None)


def test_cluster():
    points = [(0.0, 0.0), (10.0, 0.0), (0.5, 0.0), (10.0, 0.8), (50.0, 50.0)]
    assert core.cluster(points, 1.0) == [[0, 2], [1, 3], [4]]
    # цепочка: 0–1 и 1–2 рядом — одна группа
    assert core.cluster([(0.0, 0.0), (0.9, 0.0), (1.8, 0.0)], 1.0) == [[0, 1, 2]]
    assert core.cluster([], 1.0) == []


def test_settings_fields_per_group():
    from lowlife import parking_marks_settings as settings
    keys = [f.key for f in settings.SETTINGS.fields]
    for group in core.GROUPS:
        for suffix in ("_words", "_text_format", "_fill"):
            assert group.key + suffix in keys
    assert "other_text_format" in keys


def test_group_boxes():
    # две отдельные зоны светильников и машина внутри машиноместа
    boxes = [(0, 0, 10, 2), (20, 0, 30, 2), (40, 0, 45, 5), (41, 1, 44, 4)]
    assert core.group_boxes(boxes) == [[0], [1], [2, 3]]
    # Г-образная зона из двух касающихся тел — одна
    assert core.group_boxes([(0, 0, 10, 2), (10, 0, 12, 8)]) == [[0, 1]]
    assert core.group_boxes([(0, 0, 1, 1), (1.05, 0, 2, 1)], tol=0.1) == [[0, 1]]
    assert core.group_boxes([]) == []


def test_outer_boxes():
    assert core.outer_boxes([(40, 0, 45, 5), (41, 1, 44, 4)]) == [0]
    assert core.outer_boxes([(0, 0, 10, 2), (10, 0, 12, 8)]) == [0, 1]
    assert core.outer_boxes([(0, 0, 1, 1), (0, 0, 1, 1)]) == [0]
