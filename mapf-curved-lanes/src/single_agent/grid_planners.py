"""Single-agent grid planners: Dijkstra (baseline) and A* (improvement), both
8-connected with octile edge costs and corner-cutting prevention, matching the
MovingAI benchmark's own cost model (see data/movingai/PROVENANCE.md) so solved
costs are directly comparable to each scenario's known-optimal length.

This is the "basement" the multi-agent solver's low-level planners
(src/planners/forklift_planner.py, quadruped_planner.py) sit on: those currently
run plain Dijkstra with no heuristic (src/lane_graph/routing.py). Benchmarking
Dijkstra vs. A* here, on a standard citable dataset, is what justifies (or would
have refuted, if A* hadn't won) upgrading the lane-graph router the same way --
see src/benchmark/single_agent_benchmark.py for the actual comparison and
docs/single_agent_benchmark.md for the result and the concrete follow-up.
"""
from __future__ import annotations

import heapq
import itertools
import math
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from src.single_agent.movingai_io import GridMap

Cell = Tuple[int, int]
SQRT2 = math.sqrt(2)
_DIAGONAL_MOVES = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
_ORTHOGONAL_MOVES = [(1, 0), (-1, 0), (0, 1), (0, -1)]


@dataclass
class PlanResult:
    path: Optional[List[Cell]]
    cost: float
    nodes_expanded: int
    runtime_s: float


def _neighbors(grid: GridMap, cell: Cell):
    x, y = cell
    for dx, dy in _ORTHOGONAL_MOVES:
        nx, ny = x + dx, y + dy
        if grid.passable(nx, ny):
            yield (nx, ny), 1.0
    for dx, dy in _DIAGONAL_MOVES:
        nx, ny = x + dx, y + dy
        if not grid.passable(nx, ny):
            continue
        # Corner-cutting prevention, matching the benchmark's own optimal-length
        # convention (see PROVENANCE.md): a diagonal move is only legal if both
        # orthogonal cells adjacent to it are passable too.
        if not (grid.passable(x + dx, y) and grid.passable(x, y + dy)):
            continue
        yield (nx, ny), SQRT2


def _reconstruct(came_from: Dict[Cell, Cell], goal: Cell) -> List[Cell]:
    path = [goal]
    while path[-1] in came_from:
        path.append(came_from[path[-1]])
    path.reverse()
    return path


def dijkstra(grid: GridMap, start: Cell, goal: Cell) -> PlanResult:
    """Baseline: uniform-cost search, no heuristic -- expands nodes in pure
    cost order regardless of direction toward the goal.
    """
    t0 = time.perf_counter()
    dist = {start: 0.0}
    came_from: Dict[Cell, Cell] = {}
    visited = set()
    counter = itertools.count()
    heap = [(0.0, next(counter), start)]
    nodes_expanded = 0

    while heap:
        d, _, cell = heapq.heappop(heap)
        if cell in visited:
            continue
        visited.add(cell)
        nodes_expanded += 1
        if cell == goal:
            return PlanResult(
                path=_reconstruct(came_from, goal), cost=d,
                nodes_expanded=nodes_expanded, runtime_s=time.perf_counter() - t0,
            )
        for ncell, step_cost in _neighbors(grid, cell):
            nd = d + step_cost
            if ncell not in dist or nd < dist[ncell]:
                dist[ncell] = nd
                came_from[ncell] = cell
                heapq.heappush(heap, (nd, next(counter), ncell))

    return PlanResult(path=None, cost=float("inf"), nodes_expanded=nodes_expanded,
                       runtime_s=time.perf_counter() - t0)


def _octile_heuristic(a: Cell, b: Cell) -> float:
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    return (dx + dy) + (SQRT2 - 2) * min(dx, dy)


def astar(grid: GridMap, start: Cell, goal: Cell) -> PlanResult:
    """Improvement over dijkstra(): guided by the octile-distance heuristic, which
    is admissible and consistent for this exact 8-connected/octile-cost model, so
    optimality is preserved -- the improvement is in nodes_expanded/runtime, not a
    suboptimality trade.
    """
    t0 = time.perf_counter()
    g_score = {start: 0.0}
    came_from: Dict[Cell, Cell] = {}
    visited = set()
    counter = itertools.count()
    h0 = _octile_heuristic(start, goal)
    heap = [(h0, next(counter), start)]
    nodes_expanded = 0

    while heap:
        _, _, cell = heapq.heappop(heap)
        if cell in visited:
            continue
        visited.add(cell)
        nodes_expanded += 1
        if cell == goal:
            return PlanResult(
                path=_reconstruct(came_from, goal), cost=g_score[cell],
                nodes_expanded=nodes_expanded, runtime_s=time.perf_counter() - t0,
            )
        for ncell, step_cost in _neighbors(grid, cell):
            ng = g_score[cell] + step_cost
            if ncell not in g_score or ng < g_score[ncell]:
                g_score[ncell] = ng
                came_from[ncell] = cell
                f = ng + _octile_heuristic(ncell, goal)
                heapq.heappush(heap, (f, next(counter), ncell))

    return PlanResult(path=None, cost=float("inf"), nodes_expanded=nodes_expanded,
                       runtime_s=time.perf_counter() - t0)


# ---------------------------------------------------------------------------
# Jump Point Search (Harabor & Grastien, 2011) -- reproduced from the published
# algorithm description (not copied from any specific codebase). JPS is not a
# different, approximate algorithm from astar() above -- it is *the same*
# optimal search, restructured so that straight-line runs of uniform-cost grid
# get skipped over ("jumped") instead of expanded cell by cell, using a
# symmetry-breaking rule that provably cannot skip past a cell that could be on
# a shortest path.
#
# SCOPE NOTE, arrived at after real debugging, not by design choice: classical
# JPS's pruning rule implicitly assumes a diagonal move is always geometrically
# available regardless of where along a straight run you take it -- that's what
# lets an optimal path be "canonicalized" to change direction only at genuine
# forced-neighbor cells. That assumption holds when corner-cutting is allowed
# (the textbook JPS setting) but breaks when it's disallowed (this project's
# dijkstra()/astar() cost model, matching the MovingAI benchmark's own
# optimal-length convention -- data/movingai/PROVENANCE.md): a diagonal blocked
# at one point along a straight run can become available a few cells later
# purely from local corner geometry, with no "hole in the wall" of the kind the
# classical forced-neighbor test looks for. A first implementation here
# targeted the no-corner-cutting model directly and was WRONG -- caught by
# fuzz-testing against dijkstra() on small random grids
# (tests/test_single_agent.py), not by inspection, initially failing on ~53%
# of random instances despite passing hand-picked cases. Patching the specific
# failures found didn't converge to correctness either (still ~44% failures
# after one fix attempt). Rather than keep patching an approach that kept
# finding new counterexamples, this implementation targets the classical,
# corner-cutting-ALLOWED model instead, which is unambiguously specified in
# the literature and does verify correct by fuzz testing (see
# tests/test_single_agent.py::test_jps_matches_dijkstra_corner_cutting_allowed).
# A correct no-corner-cutting JPS is flagged as follow-up work in
# docs/single_agent_benchmark.md, not silently claimed as done.
#
# Because this targets a different (more permissive) cost model than
# dijkstra()/astar(), its solved cost on a real MovingAI scenario can be
# strictly *less* than the scenario's own "no corner cutting" optimal_length
# on maps where a corner-cutting shortcut exists -- that's an expected,
# quantified consequence of the relaxed model, not a bug, and
# docs/single_agent_benchmark.md reports how often it actually happens rather
# than assuming "never" or "always".
# ---------------------------------------------------------------------------

_ALL_DIRECTIONS = _ORTHOGONAL_MOVES + _DIAGONAL_MOVES


def _walkable(grid: GridMap, cell: Cell) -> bool:
    return grid.passable(*cell)


def dijkstra_allow_corner_cutting(grid: GridMap, start: Cell, goal: Cell) -> PlanResult:
    """Same as dijkstra(), but diagonal moves need only the diagonal destination
    cell to be open, not both orthogonal corner cells. This is the cost model
    jps() below actually targets -- kept as a separate function (rather than a
    flag threaded through dijkstra()) so neither this project's benchmark
    numbers against the real MovingAI dataset nor its existing tests can
    silently start using a different cost convention by accident.
    """
    t0 = time.perf_counter()
    dist = {start: 0.0}
    came_from: Dict[Cell, Cell] = {}
    visited = set()
    counter = itertools.count()
    heap = [(0.0, next(counter), start)]
    nodes_expanded = 0

    while heap:
        d, _, cell = heapq.heappop(heap)
        if cell in visited:
            continue
        visited.add(cell)
        nodes_expanded += 1
        if cell == goal:
            return PlanResult(path=_reconstruct(came_from, goal), cost=d,
                               nodes_expanded=nodes_expanded, runtime_s=time.perf_counter() - t0)
        x, y = cell
        for dx, dy in _ALL_DIRECTIONS:
            ncell = (x + dx, y + dy)
            if not _walkable(grid, ncell):
                continue
            step_cost = SQRT2 if (dx != 0 and dy != 0) else 1.0
            nd = d + step_cost
            if ncell not in dist or nd < dist[ncell]:
                dist[ncell] = nd
                came_from[ncell] = cell
                heapq.heappush(heap, (nd, next(counter), ncell))

    return PlanResult(path=None, cost=float("inf"), nodes_expanded=nodes_expanded,
                       runtime_s=time.perf_counter() - t0)


def _jump(grid: GridMap, x: int, y: int, dx: int, dy: int, goal: Cell) -> Optional[Cell]:
    """Step repeatedly in direction (dx, dy) from (x, y) until hitting the goal,
    an obstacle, or a cell with a forced neighbor -- that cell becomes the next
    jump point. Returns None if the direction runs off the map or into a dead
    end without ever finding one. Corner-cutting is allowed (see module-level
    scope note above).
    """
    while True:
        nx, ny = x + dx, y + dy
        if not _walkable(grid, (nx, ny)):
            return None
        if (nx, ny) == goal:
            return (nx, ny)

        if dx != 0 and dy != 0:
            if (_walkable(grid, (nx - dx, ny + dy)) and not _walkable(grid, (nx - dx, ny))) or (
                _walkable(grid, (nx + dx, ny - dy)) and not _walkable(grid, (nx, ny - dy))
            ):
                return (nx, ny)
            if _jump(grid, nx, ny, dx, 0, goal) is not None:
                return (nx, ny)
            if _jump(grid, nx, ny, 0, dy, goal) is not None:
                return (nx, ny)
        elif dx != 0:  # horizontal
            if (_walkable(grid, (nx + dx, ny + 1)) and not _walkable(grid, (nx, ny + 1))) or (
                _walkable(grid, (nx + dx, ny - 1)) and not _walkable(grid, (nx, ny - 1))
            ):
                return (nx, ny)
        else:  # vertical
            if (_walkable(grid, (nx + 1, ny + dy)) and not _walkable(grid, (nx + 1, ny))) or (
                _walkable(grid, (nx - 1, ny + dy)) and not _walkable(grid, (nx - 1, ny))
            ):
                return (nx, ny)

        x, y = nx, ny


def _pruned_directions(grid: GridMap, cell: Cell, came_from_dir: Optional[Cell]) -> List[Cell]:
    """Directions to try jumping in from `cell`. With no direction of travel yet
    (the start cell), try all 8. Otherwise, apply JPS's neighbor-pruning rule:
    only continue in the direction of travel (and, for a diagonal direction of
    travel, its two straight components), plus any direction that leads to a
    forced neighbor given the current direction of travel.
    """
    if came_from_dir is None:
        return list(_ALL_DIRECTIONS)

    x, y = cell
    dx, dy = came_from_dir
    dirs = []

    if dx != 0 and dy != 0:
        if _walkable(grid, (x, y + dy)):
            dirs.append((0, dy))
        if _walkable(grid, (x + dx, y)):
            dirs.append((dx, 0))
        if _walkable(grid, (x + dx, y + dy)):
            dirs.append((dx, dy))
        if not _walkable(grid, (x - dx, y)):
            dirs.append((-dx, dy))
        if not _walkable(grid, (x, y - dy)):
            dirs.append((dx, -dy))
    elif dx != 0:
        if _walkable(grid, (x + dx, y)):
            dirs.append((dx, 0))
        if not _walkable(grid, (x, y + 1)) and _walkable(grid, (x + dx, y + 1)):
            dirs.append((dx, 1))
        if not _walkable(grid, (x, y - 1)) and _walkable(grid, (x + dx, y - 1)):
            dirs.append((dx, -1))
    else:
        if _walkable(grid, (x, y + dy)):
            dirs.append((0, dy))
        if not _walkable(grid, (x + 1, y)) and _walkable(grid, (x + 1, y + dy)):
            dirs.append((1, dy))
        if not _walkable(grid, (x - 1, y)) and _walkable(grid, (x - 1, y + dy)):
            dirs.append((-1, dy))

    return dirs


def _step_cost(a: Cell, b: Cell) -> float:
    return SQRT2 if (a[0] != b[0] and a[1] != b[1]) else 1.0


def jps(grid: GridMap, start: Cell, goal: Cell) -> PlanResult:
    """Jump Point Search, corner-cutting-allowed model (see module-level scope
    note above for why, and what a no-corner-cutting version would need).
    """
    t0 = time.perf_counter()
    g_score = {start: 0.0}
    came_from: Dict[Cell, Cell] = {}
    direction_arrived: Dict[Cell, Cell] = {}
    visited = set()
    counter = itertools.count()
    heap = [(_octile_heuristic(start, goal), next(counter), start)]
    nodes_expanded = 0

    while heap:
        _, _, cell = heapq.heappop(heap)
        if cell in visited:
            continue
        visited.add(cell)
        nodes_expanded += 1
        if cell == goal:
            return PlanResult(
                path=_reconstruct(came_from, goal), cost=g_score[cell],
                nodes_expanded=nodes_expanded, runtime_s=time.perf_counter() - t0,
            )

        for dx, dy in _pruned_directions(grid, cell, direction_arrived.get(cell)):
            jp = _jump(grid, cell[0], cell[1], dx, dy, goal)
            if jp is None:
                continue
            step_len = max(abs(jp[0] - cell[0]), abs(jp[1] - cell[1]))
            ng = g_score[cell] + step_len * _step_cost((0, 0), (dx, dy))
            if jp not in g_score or ng < g_score[jp]:
                g_score[jp] = ng
                came_from[jp] = cell
                direction_arrived[jp] = (dx, dy)
                f = ng + _octile_heuristic(jp, goal)
                heapq.heappush(heap, (f, next(counter), jp))

    return PlanResult(path=None, cost=float("inf"), nodes_expanded=nodes_expanded,
                       runtime_s=time.perf_counter() - t0)
