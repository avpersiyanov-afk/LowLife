# -*- coding: utf-8 -*-
"""Тесты для lowlife.link_datums_core — сравнение осей и уровней модели со
связью КФП (кнопка «Оси и уровни КФП», Tools.panel/CompareLinkDatums)."""

from lowlife import link_datums_core as core


def lvl(name, elevation, id_=None):
    return {"name": name, "elevation": elevation, "id": id_ or name}


def line(name, p0, p1):
    return {"name": name, "id": name, "line": (p0, p1)}


def arc(name, center, radius):
    return {"name": name, "id": name, "arc": (center, radius)}


def statuses(rows):
    return [(r.model and r.model["name"], r.link and r.link["name"], r.status) for r in rows]


def test_levels_match_moved_missing():
    rows = core.compare_levels(
        [lvl(u"Этаж 1", 0.0), lvl(u"Этаж 2", 3300.0), lvl(u"Кровля", 9000.0)],
        [lvl(u"Этаж 1", 0.4), lvl(u"Этаж 2", 3305.0), lvl(u"Этаж 3", 6600.0)],
        tolerance=1.0)
    assert statuses(rows) == [
        (u"Этаж 1", u"Этаж 1", core.OK),
        (u"Этаж 2", u"Этаж 2", core.MOVED),
        (None, u"Этаж 3", core.MISSING_IN_MODEL),
        (u"Кровля", None, core.MISSING_IN_LINK),
    ]
    assert abs(rows[1].delta - 5.0) < 1e-9


def test_levels_renamed_by_case_and_by_elevation():
    rows = core.compare_levels(
        [lvl(u"этаж  1", 0.0), lvl(u"Уровень 2", 3300.0)],
        [lvl(u"Этаж 1", 0.0), lvl(u"02_Этаж", 3300.5)],
        tolerance=1.0)
    assert statuses(rows) == [
        (u"этаж  1", u"Этаж 1", core.RENAMED),
        (u"Уровень 2", u"02_Этаж", core.RENAMED),
    ]


def test_level_far_away_not_paired_by_elevation():
    rows = core.compare_levels([lvl(u"А", 0.0)], [lvl(u"Б", 10.0)], tolerance=1.0)
    assert sorted(r.status for r in rows) == sorted([core.MISSING_IN_LINK, core.MISSING_IN_MODEL])


def test_parallel_grid_shift_and_extent_ignored():
    # та же линия, но длиннее — совпадает; сдвиг на 3 мм — расходится
    rows = core.compare_grids(
        [line(u"1", (0, 0), (0, 10000)), line(u"2", (6000, 0), (6000, 10000))],
        [line(u"1", (0, -2000), (0, 20000)), line(u"2", (6003, 0), (6003, 10000))],
        tolerance=1.0)
    assert statuses(rows) == [(u"1", u"1", core.OK), (u"2", u"2", core.MOVED)]
    assert abs(rows[1].delta - 3.0) < 1e-9
    assert rows[1].angle == 0.0


def test_rotated_grid_reports_angle():
    rows = core.compare_grids([line(u"А", (0, 0), (10000, 0))],
                              [line(u"А", (0, 0), (10000, 100))], tolerance=1.0)
    assert rows[0].status == core.MOVED
    assert rows[0].angle > 0.5


def test_reversed_direction_is_same_grid():
    rows = core.compare_grids([line(u"А", (0, 0), (10000, 0))],
                              [line(u"А", (10000, 0), (0, 0))], tolerance=1.0)
    assert rows[0].status == core.OK


def test_grid_renamed_by_position_and_missing():
    rows = core.compare_grids(
        [line(u"1", (0, 0), (0, 10000)), line(u"Б", (0, 5000), (9000, 5000))],
        [line(u"A1", (0, 0), (0, 10000)), line(u"В", (0, 8000), (9000, 8000))],
        tolerance=1.0)
    assert set(statuses(rows)) == set([
        (u"1", u"A1", core.RENAMED),
        (None, u"В", core.MISSING_IN_MODEL),
        (u"Б", None, core.MISSING_IN_LINK),
    ])


def test_arcs_and_mixed_shapes():
    rows = core.compare_grids(
        [arc(u"Д1", (0, 0), 5000.0), line(u"Д2", (0, 0), (1, 0)), {"name": u"Д3", "id": 3}],
        [arc(u"Д1", (0, 0.5), 5000.3), arc(u"Д2", (0, 0), 10.0), {"name": u"Д3", "id": 4}],
        tolerance=1.0)
    by_name = dict((r.name, r) for r in rows)
    assert by_name[u"Д1"].status == core.OK
    assert by_name[u"Д2"].status == core.MOVED and by_name[u"Д2"].delta is None
    assert by_name[u"Д3"].note == u"форма оси не распознана"


def test_duplicate_names_pair_nearest():
    rows = core.compare_grids(
        [line(u"1", (0, 0), (0, 10)), line(u"1", (100, 0), (100, 10))],
        [line(u"1", (100, 0), (100, 10)), line(u"1", (0, 0), (0, 10))],
        tolerance=1.0)
    assert [r.status for r in rows] == [core.OK, core.OK]


def test_grids_sorted_naturally():
    rows = core.compare_grids([line(n, (0, 0), (0, 1)) for n in (u"10", u"2", u"1")], [],
                              tolerance=1.0)
    assert [r.name for r in rows] == [u"1", u"2", u"10"]


def test_problems_first_and_summary():
    rows = [core.Row({"name": u"a"}, {"name": u"a"}, core.OK),
            core.Row(None, {"name": u"b"}, core.MISSING_IN_MODEL),
            core.Row({"name": u"c"}, {"name": u"c"}, core.MOVED)]
    assert [r.name for r in core.problems_first(rows)] == [u"b", u"c", u"a"]
    assert core.summary_text(core.count_by_status(rows)) == \
        u"совпадает 1, расходится 1, нет в модели 1"
    assert core.summary_text({}) == u"нет"


def test_formatting_and_link_match():
    assert core.format_mm(1234.56) == u"1234,6"
    assert core.format_mm(-0.01) == u"0,0"
    assert core.format_mm(None) == u""
    assert core.format_angle(0.0) == u""
    assert core.format_angle(0.25) == u"0,250°"
    assert core.link_matches(u"Проект_кфп.rvt : 1", u"КФП")
    assert not core.link_matches(u"АР.rvt", u"КФП")
    assert core.link_matches(u"АР.rvt", u"")
