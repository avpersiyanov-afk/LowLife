from lowlife.circuit_load import summarize


def test_summarize_load_and_limits():
    rows = [{"load_va": 2300, "reserve_a": -2, "voltage_drop_pct": 6},
            {"load_va": 1000, "reserve_a": 3, "voltage_drop_pct": 2}]
    assert summarize(rows) == {"count": 2, "load_va": 3300, "overloaded": 1, "drop_over_5": 1}
