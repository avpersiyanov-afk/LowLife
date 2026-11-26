import io
import os

from lowlife.circuit_load import summarize, equipment_type_summary, filter_records


def test_summarize_load_and_limits():
    rows = [{"load_va": 2300, "reserve_a": -2, "voltage_drop_pct": 6},
            {"load_va": 1000, "reserve_a": 3, "voltage_drop_pct": 2}]
    assert summarize(rows) == {"count": 2, "load_va": 3300, "overloaded": 1, "drop_over_5": 1}


def test_equipment_types_and_filtering():
    rows = [{"number": "L1", "panel": "ЩР-1", "name": "Освещение", "equipment": [
        {"category": "Электрические приборы", "type": "Светильник"},
        {"category": "Электрические приборы", "type": "Светильник"}]}]
    assert equipment_type_summary(rows[0]["equipment"]) == u"Электрические приборы / Светильник (2)"
    assert filter_records(rows, u"светильник") == rows
    assert filter_records(rows, u"нет такого") == []


def test_window_xaml_declares_x_namespace_and_named_controls():
    root = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(root, "LowLife.tab", "ToolsCables.panel", "CircuitLoad.pushbutton", "script.py")
    with io.open(path, "r", encoding="utf-8") as stream:
        source = stream.read()
    assert 'xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"' in source
    for name in ("filter", "circuits", "equipment"):
        assert 'x:Name="{}"'.format(name) in source
