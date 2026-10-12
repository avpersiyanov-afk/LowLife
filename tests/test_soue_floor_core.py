# -*- coding: utf-8 -*-
from lowlife import soue_floor_core as core

APT = [u"Прихожая", u"Холл"]
CORR = [u"Коридор"]
LIFT = [u"Лифтовой холл"]


def test_classify_one_room_per_lot_by_priority_and_level():
    rooms = [
        (1, u"Прихожая", u"Кв.1", 3.0),
        (2, u"Холл", u"Кв.1", 0.0),       # ниже, но хуже по приоритету
        (3, u"Холл", u"Кв.2", 0.0),       # в Кв.2 прихожей нет
        (4, u"Прихожая", u"Кв.3", 6.0),   # двухуровневая: берётся нижняя
        (5, u"прихожая", u"кв.3", 3.0),
        (6, u"Кухня", u"Кв.1", 0.0),
    ]
    roles, no_lot = core.classify_rooms(rooms, APT, CORR, LIFT)
    assert roles == {1: core.ROLE_APARTMENT, 3: core.ROLE_APARTMENT, 5: core.ROLE_APARTMENT}
    assert no_lot == []


def test_classify_mop_skips_apartment_corridors():
    rooms = [
        (1, u"Прихожая", u"Кв.1", 0.0),
        (2, u"Коридор", u"Кв.1", 0.0),    # коридор внутри квартиры
        (3, u"Коридор", u"", 0.0),
        (4, u"Коридор", u"МОП", 0.0),     # лот без прихожей — не квартира
        (5, u"Лифтовой холл", u"", 0.0),
    ]
    roles, _ = core.classify_rooms(rooms, APT, CORR, LIFT)
    assert roles == {1: core.ROLE_APARTMENT, 3: core.ROLE_CORRIDOR,
                     4: core.ROLE_CORRIDOR, 5: core.ROLE_LIFT_HALL}


def test_classify_room_without_lot():
    rooms = [(1, u"Прихожая", u"", None), (2, u"Холл", u"", 0.0)]
    roles, no_lot = core.classify_rooms(rooms, APT, CORR, [u"Холл"])
    # «Холл» есть и в квартирах, и в МОП: без лота — МОП
    assert roles == {1: core.ROLE_APARTMENT, 2: core.ROLE_LIFT_HALL}
    assert no_lot == [1]


def test_grid_cells():
    assert core.grid_cells(0, 0, 10, 2, 0) == [(0, 0, 10, 2)]
    cells = core.grid_cells(0, 0, 25, 2, 10)
    assert len(cells) == 3
    assert abs(cells[1][0] - 25.0 / 3) < 1e-9
    assert len(core.grid_cells(0, 0, 20, 20, 10)) == 4
    assert core.grid_cells(0, 0, 10, 2, 10) == [(0, 0, 10, 2)]


def test_cell_samples_start_at_center():
    samples = core.cell_samples((0, 0, 10, 4), count=3)
    assert samples[0] == (5.0, 2.0)
    assert len(samples) == 10


SQUARE = [(0, 0, 10, 0), (10, 0, 10, 4), (10, 4, 0, 4), (0, 4, 0, 0)]


def test_wall_point_nearest_wall_facing_inside():
    x, y, nx, ny, free = core.wall_point(SQUARE, (5, 1), [], 0.5)
    assert (x, y) == (5, 0)
    assert (nx, ny) == (0, 1)
    assert free


def test_wall_point_avoids_opening_and_margin():
    # дверь посреди нижней стены — точка сдвигается к краю её зоны
    x, y, _, _, free = core.wall_point(SQUARE, (5, 1), [(5, 0.1, 1.0)], 0.5)
    assert free and abs(y) < 1e-9
    assert abs(abs(x - 5) - (1.0 - 0.01) ** 0.5) < 1e-9
    # угол комнаты: не ближе отступа
    x, y, _, _, _ = core.wall_point(SQUARE, (0.1, 0.1), [], 0.5)
    assert min(x, y) == 0 and max(x, y) == 0.5


def test_wall_point_all_blocked_falls_back():
    obstacles = [(5, 2, 20)]
    x, y, _, _, free = core.wall_point(SQUARE, (5, 1), obstacles, 0.5)
    assert not free
    assert (x, y) == (5, 0)
    assert core.wall_point([], (0, 0), [], 0.5) is None
