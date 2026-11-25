from lowlife.service_circuit_lengths import classify_lengths

def test_unknown_length_is_retained():
    result = classify_lengths([(10, "tray"), (5, "mystery")], unknown_as="pipe")
    assert result.total == 15
    assert result.unknown == 5
    assert result.pipe == 5
