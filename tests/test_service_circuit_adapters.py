from lowlife.service_circuit_adapters import normalize_system_kind, CircuitRecord

def test_normalize_system_kind_aliases():
    assert normalize_system_kind("СКУД") == "SKUD"
    assert normalize_system_kind("СПС") == "SPS"

def test_circuit_record_accepts_multiple_devices():
    record = CircuitRecord("SKUD", 10, 20, [30, 31], "per_device")
    assert record.device_ids == [30, 31]
