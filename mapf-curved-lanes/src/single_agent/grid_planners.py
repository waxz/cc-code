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
