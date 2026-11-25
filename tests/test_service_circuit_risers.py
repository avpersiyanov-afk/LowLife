from lowlife.service_circuit_risers import direction_for_path, shaft_matches_type

def test_direction_for_path():
    assert direction_for_path([1, 2, 3], {1: 0, 2: 1, 3: 2}) == "up"
    assert direction_for_path([1, 2], {1: 2, 2: 1}) == "down"
    assert direction_for_path([1, 2, 3], {1: 1, 2: 2, 3: 1}) == "up/down"

def test_shaft_type_keyword():
    assert shaft_matches_type("ВИС_СС_СПЗ", ["СС", "СБ", "СПЗ"])
    assert not shaft_matches_type("АР_", ["СС", "СБ", "СПЗ"])
