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


# --- акустический расчёт МОП (значения — из «Расчёт СОУЭ.xlsx») -------------

def test_acoustic_reach_matches_spreadsheet():
    # потолочный SC-5106, 1,5 Вт, МОП (50 дБА), h = 3 м
    rmax, reach = core.acoustic_reach(87, 1.5, 50, 15, 6, 0, 3.0, 1.5)
    assert abs(rmax - 7.7276) < 1e-3
    assert abs(reach - 7.5806) < 1e-3
    # настенный SW-2110, 10 Вт, парковка (70 дБА), h = 2,5 м
    _, reach = core.acoustic_reach(92, 10, 70, 15, 6, 0, 2.5, 1.5)
    assert abs(reach - 3.4043) < 1e-3
    # не дотягивает до расчётной плоскости
    assert core.acoustic_reach(87, 6, 80, 15, 6, 0, 2.5, 1.5)[1] == 0.0
    assert core.acoustic_reach(87, 0, 50, 15, 6, 0, 3.0, 1.5) == (0.0, 0.0)


def test_lattice_square_grid_and_row():
    reach = 7.5806
    assert len(core.lattice(0, 0, 20, 20, reach)) == 4      # шаг ≤ R·√2 ≈ 10,7
    assert len(core.lattice(0, 0, 30, 2, reach)) == 2       # ряд, шаг почти 2R
    assert len(core.lattice(0, 0, 50, 2.4, reach)) == 4
    assert core.lattice(0, 0, 10, 10, 0) == []
    assert core.lattice(0, 0, 10, 2, reach) == [(5.0, 1.0)]


def _grid(width, height, step=0.5, mask=None):
    nodes = [(i, j) for j in range(int(height / step)) for i in range(int(width / step))
             if mask is None or mask(step / 2 + i * step, step / 2 + j * step)]
    return core.SampleGrid(step / 2, step / 2, step, nodes)


def test_greedy_cover_ceiling_corridor():
    grid = _grid(30, 2)
    samples = grid.points()
    sets = core.coverage(samples, samples, 7.5806, grid)
    chosen, uncovered = core.greedy_cover(samples, sets, samples)
    assert uncovered == 0
    assert len(chosen) == 2


def test_visibility_in_l_shaped_corridor():
    grid = _grid(20, 20, mask=lambda x, y: y < 2 or x < 2)
    assert grid.visible(1, 1, 15, 1)
    assert not grid.visible(15, 1, 1, 15)   # через угол — не видно
    samples = grid.points()
    sets = core.coverage(samples, samples, 7.5806, grid)
    chosen, uncovered = core.greedy_cover(samples, sets, samples)
    assert uncovered == 0
    assert len(chosen) == 3


def test_wall_cover_corridor_avoids_door():
    grid = _grid(30, 2)
    samples = grid.points()
    segments = [(0, 0, 30, 0, 0, 1), (30, 0, 30, 2, -1, 0), (30, 2, 0, 2, 0, -1), (0, 2, 0, 0, 1, 0)]
    door = (15, 0, 1.2)
    candidates = core.wall_candidates(segments, [door], 0.3, 1.0)
    assert not any(abs(x - 15) < 1.1 and abs(y) < 1e-9 for x, y, _, _ in candidates)
    sets = core.coverage(candidates, samples, 12.2, grid, wall=True)
    chosen, uncovered = core.greedy_cover(candidates, sets, samples)
    assert uncovered == 0
    assert len(chosen) == 2


def test_wall_cover_only_in_front():
    grid = _grid(4, 4)
    samples = grid.points()
    # оповещатель на стене x = 0 смотрит в +X: точки «за спиной» не озвучивает
    sets = core.coverage([(0, 2, 1, 0), (0, 2, -1, 0)], samples, 10, grid, wall=True)
    assert len(sets[0]) == len(samples)
    assert len(sets[1]) == 0


def test_unreachable_samples_reported():
    samples = [(0, 0), (100, 0)]
    sets = core.coverage([(0, 0)], samples, 5)
    chosen, uncovered = core.greedy_cover([(0, 0)], sets, samples)
    assert chosen == [0] and uncovered == 1


def test_classify_ceiling():
    assert core.classify_ceiling([(3.0, None), (2.5, "slab"), (2.7, "ceiling")]) == ("slab", 2.5)
    assert core.classify_ceiling([(3.0, "slab"), (2.6, "ceiling")]) == ("ceiling", 2.6)
    assert core.classify_ceiling([(1.0, None)]) == (None, None)


def test_sample_step_limits_point_count():
    assert core.sample_step(30, 2, 0.5) == 0.5
    step = core.sample_step(100, 100, 0.5, max_samples=600)
    assert (100 / step) ** 2 <= 600 + 1e-6
