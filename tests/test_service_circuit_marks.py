from lowlife.service_circuit_marks import mark_text, mark_key
from lowlife.service_circuit_adapters import CircuitRecord

def test_mark_text_for_failed_route():
    c=CircuitRecord("SPS", 4, 1, [2], "sequence")
    assert mark_text({"circuit":c,"status":"no_path"}) == "4 | ПУТЬ НЕ НАЙДЕН"

def test_mark_key_is_stable():
    assert mark_key("SCS", 4, 10) == "ServiceCircuit:SCS:4:10"
