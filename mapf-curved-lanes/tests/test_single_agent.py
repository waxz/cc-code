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
