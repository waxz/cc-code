from pathlib import Path

from src.single_agent.grid_planners import astar, dijkstra
from src.single_agent.movingai_io import load_map, load_scen

DATA_DIR = Path(__file__).parent.parent / "data" / "movingai"


def test_load_map_parses_dimensions_and_passability():
    grid = load_map(DATA_DIR / "random-32-32-20.map")
    assert grid.width == 32
    assert grid.height == 32
    # spot-check a known passable and a known blocked cell from the file header
    assert grid.passable(0, 0) is True  # row 0 starts with '.'
    assert grid.passable(-1, 0) is False  # out of bounds
    assert grid.passable(100, 100) is False


def test_load_scen_parses_known_entry_count_and_fields():
    scens = load_scen(DATA_DIR / "random-32-32-20-random-1.scen")
    assert len(scens) == 409
    first = scens[0]
    assert first.start == (5, 16)
    assert first.goal == (31, 24)
    assert abs(first.optimal_length - 31.31370850) < 1e-6


def test_dijkstra_and_astar_match_known_optimal_on_real_scenarios():
    grid = load_map(DATA_DIR / "random-32-32-20.map")
    scens = load_scen(DATA_DIR / "random-32-32-20-random-1.scen")
    for s in scens[:20]:
        r_d = dijkstra(grid, s.start, s.goal)
        r_a = astar(grid, s.start, s.goal)
        assert r_d.path is not None
        assert r_a.path is not None
        assert abs(r_d.cost - s.optimal_length) < 1e-3
        assert abs(r_a.cost - s.optimal_length) < 1e-3


def test_astar_expands_fewer_or_equal_nodes_than_dijkstra():
    grid = load_map(DATA_DIR / "random-32-32-20.map")
    scens = load_scen(DATA_DIR / "random-32-32-20-random-1.scen")
    for s in scens[:20]:
        r_d = dijkstra(grid, s.start, s.goal)
        r_a = astar(grid, s.start, s.goal)
        assert r_a.nodes_expanded <= r_d.nodes_expanded


def test_jps_self_consistent_with_matching_corner_cutting_dijkstra_fuzz():
    """JPS (src/single_agent/grid_planners.py::jps) targets the classical,
    corner-cutting-ALLOWED cost model, not the same one dijkstra()/astar() use
    -- see the module docstring above jps() for why, including the debugging
    history (an initial no-corner-cutting attempt was wrong, found by exactly
    this kind of fuzz test, not by inspection). This locks that finding in as a
    regression test: JPS must match a Dijkstra using the SAME (corner-cutting
    allowed) model exactly, on many random small grids, not just hand-picked
    ones.
    """
    import random

    from src.single_agent.grid_planners import dijkstra_allow_corner_cutting, jps
    from src.single_agent.movingai_io import GridMap

    rng = random.Random(1)
    for _ in range(300):
        w, h = rng.choice([5, 6, 8]), rng.choice([5, 6, 8])
        density = rng.choice([0.15, 0.25, 0.35])
        g = [[rng.random() > density for _ in range(w)] for _ in range(h)]
        g[0][0] = True
        g[h - 1][w - 1] = True
        grid = GridMap(width=w, height=h, grid=g)
        start, goal = (0, 0), (w - 1, h - 1)

        r_cut = dijkstra_allow_corner_cutting(grid, start, goal)
        r_jps = jps(grid, start, goal)

        assert (r_cut.path is None) == (r_jps.path is None)
        if r_cut.path is not None:
            assert abs(r_cut.cost - r_jps.cost) < 1e-6


def test_jps_self_consistent_on_real_scenarios():
    """Same check as above, but on the real MovingAI scenarios rather than only
    synthetic fuzz grids -- both should agree on every one of the 409 real
    instances, even though JPS's cost will often be strictly below the
    scenario file's own no-corner-cut optimal_length (see
    docs/single_agent_benchmark.md for exactly how often and why that's
    expected, not a bug).
    """
    from src.single_agent.grid_planners import dijkstra_allow_corner_cutting, jps

    grid = load_map(DATA_DIR / "random-32-32-20.map")
    scens = load_scen(DATA_DIR / "random-32-32-20-random-1.scen")
    for s in scens:
        r_cut = dijkstra_allow_corner_cutting(grid, s.start, s.goal)
        r_jps = jps(grid, s.start, s.goal)
        assert abs(r_cut.cost - r_jps.cost) < 1e-6
        # Corner-cutting is a relaxation, so it can only ever match or beat the
        # stricter no-cut optimal length, never exceed it.
        assert r_jps.cost <= s.optimal_length + 1e-6


def test_unreachable_goal_returns_no_path():
    from src.single_agent.movingai_io import GridMap

    # A 3x3 grid where the goal is walled off entirely.
    grid = GridMap(width=3, height=3, grid=[
        [True, True, True],
        [True, True, True],
        [True, True, False],
    ])
    result = dijkstra(grid, (0, 0), (2, 2))
    assert result.path is None
    assert result.cost == float("inf")


def test_corner_cutting_is_prevented():
    """A diagonal move between two orthogonally-blocked cells must not be
    allowed, matching the benchmark's own optimal-length convention (see
    data/movingai/PROVENANCE.md).
    """
    from src.single_agent.movingai_io import GridMap

    # (0,0) open, (1,1) open, but (1,0) and (0,1) both blocked -- diagonal
    # shortcut from (0,0) to (1,1) must be rejected; only route is the long way
    # around, if one exists. Here none does, so the goal must be unreachable.
    grid = GridMap(width=2, height=2, grid=[
        [True, False],
        [False, True],
    ])
    result = dijkstra(grid, (0, 0), (1, 1))
    assert result.path is None
