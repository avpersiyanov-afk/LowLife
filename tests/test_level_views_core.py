# -*- coding: utf-8 -*-
"""Тесты для lowlife.level_views_core — кнопка «Виды по уровням»: группы
видов из настроек, имя вида по маске, секущий диапазон, выбор плана связи
для «По связанному виду»."""

import pytest

from lowlife import level_name_template
from lowlife import level_views_core as core


def test_normalize_group_fills_defaults_and_fixes_bad_values():
    g = core.normalize_group({core.G_NAME: u"  ЭОМ ", core.G_CUT: u"abc",
                              core.G_TOP: None, core.G_LINKS: 1, core.G_NAME_MASK: u" "})
    assert g[core.G_NAME] == u"ЭОМ"
    assert g[core.G_CUT] == core.GROUP_DEFAULTS[core.G_CUT]
    assert g[core.G_TOP] is None
    assert g[core.G_LINKS] is True
    assert g[core.G_NAME_MASK] == core.GROUP_DEFAULTS[core.G_NAME_MASK]


def test_normalize_groups_skips_garbage():
    assert core.normalize_groups(None) == []
    assert len(core.normalize_groups([{}, u"x", {core.G_NAME: u"A"}])) == 2


def test_parse_mm():
    assert core.parse_mm(u" ") is None
    assert core.parse_mm(u"1 200".replace(u" ", u"")) == 1200.0
    assert core.parse_mm(u"-200,5") == -200.5
    assert core.parse_mm(u"−200") == -200.0
    with pytest.raises(ValueError):
        core.parse_mm(u"верх")


@pytest.mark.parametrize("mm, text", [
    (0.0, u"±0.000"), (3300.0, u"+3.300"), (-2700.4, u"-2.700"), (0.2, u"±0.000"),
])
def test_format_elevation(mm, text):
    assert core.format_elevation(mm) == text


def test_build_view_name_with_level_template_parts():
    tpl = level_name_template.LevelNameTemplate(u"{Дисциплина}_{Корпус}_{Отметка}_{Этаж}_{Комментарий}")
    name = u"АР_К1_+3.300_02_Низ"
    values = core.level_tokens(name, 3300.0, tpl.parse(name))
    group = core.normalize_group({core.G_NAME: u"ЭОМ",
                                  core.G_NAME_MASK: u"{Группа} {Корпус} {Этаж} этаж ({Отметка}) {Комментарий}"})
    assert core.build_view_name(group, values) == u"ЭОМ К1 02 этаж (+3.300) Низ"


def test_build_view_name_unparsed_level_drops_parts_and_bad_chars():
    values = core.level_tokens(u"Уровень 1", 0.0, None)
    group = core.normalize_group({core.G_NAME: u"Г", core.G_NAME_MASK: u"{Уровень}: {Этаж} [план]"})
    assert core.build_view_name(group, values) == u"Уровень 1 план"


def test_validate_mask():
    assert core.validate_mask(u"{Уровень}_ЭОМ") is None
    assert u"неизвестные" in core.validate_mask(u"{Уровень}_{Марка}")
    assert u"скобка" in core.validate_mask(u"{Уровень")
    assert core.validate_mask(u"  ") == u"маска пустая"
    assert core.validate_mask(u"{Группа}", core.LINK_VIEW_TOKENS) is not None


def test_validate_groups_duplicate_names():
    groups = [core.normalize_group({core.G_NAME: u"A"}), core.normalize_group({core.G_NAME: u"A"})]
    problems = core.validate_groups(groups)
    assert [i for i, _e in problems] == [1]


def test_group_from_form_reports_bad_numbers():
    group, errors = core.group_from_form({core.G_NAME: u"A", core.G_TOP: u"", core.G_CUT: u"x",
                                          core.G_BOTTOM: u"0", core.G_DEPTH: u""})
    assert group[core.G_TOP] is None and group[core.G_CUT] is None
    assert len(errors) == 1 and u"секущая" in errors[0]


def test_range_plan_depth_follows_bottom():
    group = core.normalize_group({core.G_TOP: u"", core.G_CUT: 1200, core.G_BOTTOM: -100,
                                  core.G_DEPTH: u""})
    assert core.range_plan(group) == {"cut": 1200.0, "bottom": -100.0, "depth": -100.0}


def test_range_problem():
    assert core.range_problem({"cut": 1200.0, "bottom": 0.0, "depth": 0.0, "top": -200.0}, 3300.0) is None
    assert u"низ" in core.range_problem({"cut": 100.0, "bottom": 200.0}, None)
    assert u"глубина" in core.range_problem({"bottom": 0.0, "depth": 10.0}, None)
    assert u"верх" in core.range_problem({"cut": 1200.0, "top": -200.0}, 1300.0)
    assert core.range_problem({"cut": 1200.0, "top": -200.0}, None) is None


def test_split_filters_and_match():
    filters = core.split_filters(u"АР; КР , ")
    assert filters == [u"ар", u"кр"]
    assert core.name_matches_any(u"Проект_АР_К1.rvt", filters)
    assert not core.name_matches_any(u"ОВ.rvt", filters)
    assert core.name_matches_any(u"ОВ.rvt", [])


def test_link_view_filter_value_substitutes_level():
    group = core.normalize_group({core.G_LINK_VIEW_FILTER: u" План {Этаж} "})
    assert core.link_view_filter_value(group, {core.TOKEN_FLOOR: u"02"}) == u"План 02"
    assert core.link_view_filter_value(group) == u"План {Этаж}"


def test_normalize_group_link_view_mode():
    assert core.normalize_group({})[core.G_LINK_VIEW_MODE] == core.MODE_CONTAINS
    assert core.normalize_group({core.G_LINK_VIEW_MODE: u"xxx"})[core.G_LINK_VIEW_MODE] == core.MODE_CONTAINS
    assert core.normalize_group({core.G_LINK_VIEW_MODE: core.MODE_STARTS})[core.G_LINK_VIEW_MODE] == core.MODE_STARTS


@pytest.mark.parametrize("mode, value, name, ok", [
    (core.MODE_STARTS, u"2", u"2 этаж", True),
    (core.MODE_STARTS, u"2", u"12 этаж", False),
    (core.MODE_STARTS, u"2, 3", u"3_План", True),
    (core.MODE_CONTAINS, u"план", u"АР_ПЛАН_1", True),
    (core.MODE_ENDS, u"_эом", u"План 1_ЭОМ", True),
    (core.MODE_ENDS, u"_эом", u"План 1_ЭОМ копия", False),
    (core.MODE_NOT_CONTAINS, u"копия, старый", u"План 1 копия", False),
    (core.MODE_NOT_CONTAINS, u"копия, старый", u"План 1", True),
    (core.MODE_EQUALS, u"план 1", u"План 1", True),
    (core.MODE_EQUALS, u"план 1", u"План 10", False),
    (core.MODE_REGEX, u"^2\\d?_", u"21_План", True),
    (core.MODE_REGEX, u"^2\\d?_", u"3_План", False),
    (core.MODE_REGEX, u"(", u"любой", False),
    (core.MODE_STARTS, u"", u"любой", True),
])
def test_link_view_matches(mode, value, name, ok):
    assert core.link_view_matches(name, mode, value) is ok


def test_validate_link_view_filter():
    assert core.validate_link_view_filter(core.MODE_STARTS, u"2") is None
    assert core.validate_link_view_filter(core.MODE_STARTS, u"План {Этаж}") is None
    assert u"неизвестные" in core.validate_link_view_filter(core.MODE_CONTAINS, u"{Группа}")
    assert u"регулярное" in core.validate_link_view_filter(core.MODE_REGEX, u"(")
    assert core.validate_link_view_filter(core.MODE_REGEX, u"^2{1,2}") is None
    assert core.validate_link_view_filter("bad", u"") is not None


def test_filter_link_views_sorted():
    cands = [(u"2б", 0.0, 1), (u"1", 0.0, 2), (u"2а", 0.0, 3)]
    assert [c[2] for c in core.filter_link_views(cands, core.MODE_STARTS, u"2")] == [3, 1]


def test_default_link_view_prefers_remembered():
    cands = [(u"2 этаж", 3300.0, 1), (u"2 этаж копия", 0.0, 2)]
    assert core.default_link_view(cands, 3300.0, u"2 этаж копия")[2] == 2
    assert core.default_link_view(cands, 3300.0, u"пропал")[2] == 1
    assert core.default_link_view([], 0.0) is None


def test_pick_link_view_nearest_level():
    cands = [(u"План 1", 0.0, 1), (u"План 2", 3150.0, 2), (u"План 3", 6300.0, 3)]
    picked, note = core.pick_link_view(cands, 3300.0)
    assert picked[2] == 2
    assert u"150" in note


def test_pick_link_view_ambiguous():
    cands = [(u"Б план", 3300.0, 1), (u"А план", 3300.0, 2), (u"План 1", 0.0, 3)]
    picked, note = core.pick_link_view(cands, 3300.0)
    assert picked[2] == 2 and u"2 планов" in note


def test_pick_link_view_too_far_or_none():
    picked, note = core.pick_link_view([(u"План", 0.0, 1)], 6000.0)
    assert picked is None and u"допустимо" in note
    assert core.pick_link_view([], 0.0)[0] is None
