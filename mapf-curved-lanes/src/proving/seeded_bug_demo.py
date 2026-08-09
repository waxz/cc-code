"""A deliberately-buggy toy planner, used ONLY to validate that
src/proving/differential.py + shrink.py actually catch bugs and reduce them to a
minimal counterexample -- not part of any production planner. Ground truth is
known here (the bug is intentional and documented), which is what makes this a
valid validation of the tool rather than another thing that needs trusting.

Honesty note on how this bug was chosen, because the first attempt failed and
that failure is itself informative: the original idea was an "inadmissible
heuristic" bug (deliberately overestimating in astar()'s heuristic). Empirically
(not by assumption) that produced 0/500 failures against dijkstra() on random
instances -- including with the overestimate increased 10x. Root cause,
understood only after checking: a *uniform* additive constant added to every
node's heuristic cannot change A*'s relative expansion order at all (f_i - f_j is
unaffected by a shared offset), and even the direction-dependent variant tried
apparently stayed too small relative to typical cost gaps on these small grids to
ever flip the final answer. That's a real, useful negative result about how
robust A* is to small heuristic miscalibration -- and a good demonstration of why
"I reasoned it should be inadmissible" isn't the same claim as "I measured it
causes wrong answers." The bug actually used below is blunter and unambiguous:
a Dijkstra copy that omits the four diagonal moves (a realistic, easy-to-make
implementation slip, not a contrived one) -- measured to manifest on 306/500
(61.2%) random instances against the real 8-connected dijkstra().
"""
from __future__ import annotations

import heapq
import itertools
from typing import Optional, Tuple

from src.single_agent.movingai_io import GridMap

Cell = Tuple[int, int]
_FOUR_CONNECTED = [(1, 0), (-1, 0), (0, 1), (0, -1)]


def buggy_dijkstra_missing_diagonals(grid: GridMap, start: Cell, goal: Cell) -> Optional[float]:
    """Same as src/single_agent/grid_planners.py::dijkstra, except it iterates
    only _FOUR_CONNECTED instead of all 8 directions -- the diagonal branch was
    simply never added. Returns the solved cost, or None if no path.
    """
    dist = {start: 0.0}
    visited = set()
    counter = itertools.count()
    heap = [(0.0, next(counter), start)]

    while heap:
        d, _, cell = heapq.heappop(heap)
        if cell in visited:
            continue
        visited.add(cell)
        if cell == goal:
            return d
        x, y = cell
        for dx, dy in _FOUR_CONNECTED:
            nx, ny = x + dx, y + dy
            if not grid.passable(nx, ny):
                continue
            nd = d + 1.0
            if (nx, ny) not in dist or nd < dist[(nx, ny)]:
                dist[(nx, ny)] = nd
                heapq.heappush(heap, (nd, next(counter), (nx, ny)))

    return None
