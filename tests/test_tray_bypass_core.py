from lowlife.tray_bypass_core import plan_bypass


def test_plan_bypass_uses_free_side_and_preserves_endpoints():
    route = plan_bypass(
        (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 1.0, 0.0),
        [{"start": 4.0, "end": 6.0, "perp_min": -0.5, "perp_max": 0.5}],
        0.25, 0.1)
    assert route[0] == (0.0, 0.0, 0.0)
    assert route[-1] == (10.0, 0.0, 0.0)
    assert route[2][1] > 0.0
    assert route[2][1] == route[3][1]


def test_plan_bypass_merges_overlapping_crossings():
    route = plan_bypass(
        (0.0, 0.0, 0.0), (20.0, 0.0, 0.0), (0.0, 1.0, 0.0),
        [{"start": 4.0, "end": 8.0, "perp_min": -0.2, "perp_max": 0.2},
         {"start": 7.0, "end": 12.0, "perp_min": -0.4, "perp_max": 0.4}],
        0.25, 0.1)
    assert len(route) == 6
    assert route[1][0] == 3.9
    assert route[4][0] == 12.1


def test_plan_bypass_without_crossings_is_unchanged():
    assert plan_bypass((0, 0, 0), (2, 0, 0), (0, 1, 0), [], 0.2, 0.1) == [
        (0, 0, 0), (2, 0, 0)]


def test_tray_crossing_uses_vertical_detour():
    route = plan_bypass(
        (0.0, 0.0, 2.0), (10.0, 0.0, 2.0), (0.0, 1.0, 0.0),
        [{"start": 4.0, "end": 6.0, "mode": "vertical",
          "vertical_min": 1.0, "vertical_max": 3.0}],
        0.25, 0.1, tray_half_height=0.25)
    assert route[2][2] > 2.0
    assert route[2][2] == route[3][2]


def test_nearby_crossings_are_one_detour_group():
    route = plan_bypass(
        (0.0, 0.0, 0.0), (15.0, 0.0, 0.0), (0.0, 1.0, 0.0),
        [{"start": 4.0, "end": 5.0, "perp_min": -0.2, "perp_max": 0.2},
         {"start": 5.4, "end": 6.0, "perp_min": -0.2, "perp_max": 0.2}],
        0.25, 0.1)
    assert len(route) == 6
    assert route[1][0] == 3.9
    assert route[4][0] == 6.1


def test_horizontal_side_can_be_forced_to_right():
    route = plan_bypass(
        (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 1.0, 0.0),
        [{"start": 4.0, "end": 6.0, "perp_min": -0.5, "perp_max": 0.5}],
        0.25, 0.1, horizontal_side=-1)
    assert route[2][1] < 0.0


def test_vertical_side_can_be_forced_below():
    route = plan_bypass(
        (0.0, 0.0, 2.0), (10.0, 0.0, 2.0), (0.0, 1.0, 0.0),
        [{"start": 4.0, "end": 6.0, "mode": "vertical",
          "vertical_min": 1.0, "vertical_max": 3.0}],
        0.25, 0.1, tray_half_height=0.25, vertical_side=-1)
    assert route[2][2] < 2.0
