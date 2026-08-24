# -*- coding: utf-8 -*-
"""Тесты для lowlife.scs_circuits — граф по адресам, A*, расчёт длин по
способу прокладки, округление. Требует Python 2 (модуль использует
встроенную unicode()). Логика используется SyncCircuitsAndLengths (СКС) и
CalcSkudLengths (СКУД, через прямой импорт тех же функций)."""

import pytest

from lowlife import scs_circuits as sc
from helpers import FakeXYZ


def test_norm():
    assert sc.norm(None) is None
    assert sc.norm(u"  F1.2  ") == u"F1.2"
    assert sc.norm(u"   ") is None


def test_clean_text_value_drops_placeholder_values():
    assert sc.clean_text_value(u"0") is None
    assert sc.clean_text_value(u"-") is None
    assert sc.clean_text_value(None) is None
    assert sc.clean_text_value(u"F1.2") == u"F1.2"


def test_split_multi_value():
    assert sc.split_multi_value(u"F1.2, F1.3") == [u"F1.2", u"F1.3"]
    assert sc.split_multi_value(u"F1.2") == [u"F1.2"]
    assert sc.split_multi_value(None) == []


@pytest.mark.parametrize(
    "addr,expected",
    [
        (u"F1.P3", True),
        (u"F1.R2", True),
        (u"F1.3", False),
        (u"", False),
        (None, False),
        (u"F1.", False),
    ],
)
def test_is_root_address(addr, expected):
    assert sc.is_root_address(addr) is expected


def test_parse_route_path():
    assert sc.parse_route_path(u"F1.2 -> F1.3 -> F1.4") == [u"F1.2", u"F1.3", u"F1.4"]
    assert sc.parse_route_path(u"F1.2") == [u"F1.2"]
    assert sc.parse_route_path(u"") == []
    assert sc.parse_route_path(None) == []


def test_build_graph_links_nodes_and_reports_broken_links():
    segments = {"a": {}, "b": {}, "c": {}}
    parents_by_id = {
        "b": ["a"],
        "c": ["b"],
        "d": ["missing"],       # ссылка на несуществующий узел — ошибка
        "e": [u"F1.P1"],        # ссылка на адрес корня — НЕ ошибка (is_root_address)
    }

    graph, broken = sc.build_graph(segments, parents_by_id)

    assert broken == [u"d -> missing"]
    assert set(graph["a"]) == set(["b"])
    assert set(graph["b"]) == set(["a", "c"])
    assert set(graph["c"]) == set(["b"])
    assert "d" not in graph


def test_bfs_component():
    graph = {"a": ["b"], "b": ["a", "c"], "c": ["b"], "d": ["e"], "e": ["d"]}
    assert sc.bfs_component(graph, "a") == set(["a", "b", "c"])


def _chain_segments():
    return {
        "a": {"pt": FakeXYZ(0, 0, 0)},
        "b": {"pt": FakeXYZ(1, 0, 0)},
        "c": {"pt": FakeXYZ(2, 0, 0)},
        "d": {"pt": FakeXYZ(3, 0, 0)},
        "e": {"pt": FakeXYZ(1, 5, 0)},  # длинный обходной путь
    }


def _chain_graph():
    return {
        "a": ["b", "e"],
        "b": ["a", "c"],
        "c": ["b", "d"],
        "d": ["c", "e"],
        "e": ["a", "d"],
    }


def test_astar_path_picks_the_shorter_route():
    segments = _chain_segments()
    graph = _chain_graph()

    path = sc.astar_path(segments, graph, "a", "d")

    assert path == ["a", "b", "c", "d"]


def test_astar_path_start_equals_end():
    segments = _chain_segments()
    graph = _chain_graph()
    assert sc.astar_path(segments, graph, "a", "a") == ["a"]


def test_astar_path_no_route_returns_empty_list():
    segments = {"a": {"pt": FakeXYZ(0, 0, 0)}, "b": {"pt": FakeXYZ(1, 0, 0)}, "c": {"pt": FakeXYZ(2, 0, 0)}}
    graph = {"a": ["b"], "b": ["a"], "c": []}
    assert sc.astar_path(segments, graph, "a", "c") == []


def test_calc_lengths_uses_install_of_the_departure_node():
    # Способ прокладки отрезка path[i]->path[i+1] берётся у path[i]
    # (узел ближе к панели), а не у path[i+1] — так стык труба/лоток
    # относится к правильному отрезку.
    segments = {
        "a": {"pt": FakeXYZ(0, 0, 0), "install": u"Труба"},
        "b": {"pt": FakeXYZ(1, 0, 0), "install": u"Лоток"},
        "c": {"pt": FakeXYZ(2, 0, 0), "install": u"Лоток"},
    }
    path = ["a", "b", "c"]

    total_m, tray_m, pipe_m, pipe_open_m = sc.calc_lengths(
        segments, path,
        install_tray_key=u"Лоток",
        install_pipe_key=u"Труба",
        install_pipe_open_key=u"Труба открыто",
    )

    assert total_m == pytest.approx(2 * sc.FT_TO_M)
    assert pipe_m == pytest.approx(1 * sc.FT_TO_M)   # a->b, способ прокладки от "a"
    assert tray_m == pytest.approx(1 * sc.FT_TO_M)   # b->c, способ прокладки от "b"
    assert pipe_open_m == pytest.approx(0.0)


def test_balance_round_parts_no_remainder():
    assert sc.balance_round_parts(10.0, [3.2, 3.2, 3.6]) == [10, 3, 3, 4]


def test_balance_round_parts_assigns_remainder_to_largest_part():
    # rounded_parts=[3,3,3], sum=9, total_round=10 -> недостающая единица
    # уходит в первую по порядку часть при равенстве исходных значений.
    assert sc.balance_round_parts(10.0, [3.4, 3.4, 3.4]) == [10, 4, 3, 3]


def test_classify_circuit_type():
    assert sc.classify_circuit_type(u"Оптика магистральная", u"оптика", u"utp", u"питание") == "FO"
    assert sc.classify_circuit_type(u"UTP кабель", u"оптика", u"utp", u"питание") == "UTP"
    assert sc.classify_circuit_type(None, u"оптика", u"utp", u"питание") is None
    assert sc.classify_circuit_type(u"неизвестно", u"оптика", u"utp", u"питание") is None


def test_make_load_name():
    assert sc.make_load_name(u"К1", u"3") == u"К1.3"
    assert sc.make_load_name(u"К1", None) == u"К1"
    assert sc.make_load_name(None, u"3") == u"3"
    assert sc.make_load_name(None, None) is None


def test_build_segment_list_text():
    text = sc.build_segment_list_text([u"a", u"b", u"a", None, u""], fo_count=2, utp_count=3)
    assert text == u"a\nb\nВсего кабелей:\nFO-2 шт.\nUTP-3 шт."


def test_build_segment_list_text_no_cables():
    assert sc.build_segment_list_text([], fo_count=0, utp_count=0) == u"Всего кабелей:"
