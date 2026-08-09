"""Random grid-instance generation and simplification strategies for
src/proving/differential.py and src/proving/shrink.py, specialized to
GridMap-based single-agent pathfinding (src/single_agent/grid_planners.py).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Tuple

from src.single_agent.movingai_io import GridMap

Cell = Tuple[int, int]


@dataclass
class GridInstance:
    grid: GridMap
    start: Cell
    goal: Cell


def random_grid_instance(
    rng: random.Random, min_size: int = 4, max_size: int = 12
) -> GridInstance:
    """Random grid with start=(0,0), goal=(w-1,h-1), both forced passable so a
    trial is never trivially vacuous. Obstacle density is itself randomized per
    instance (not fixed) so the generator covers sparse and dense maps alike --
    the JPS corner-cutting bug in this project's history was density-sensitive,
    so a fixed density could have hidden it.
    """
    w = rng.randint(min_size, max_size)
    h = rng.randint(min_size, max_size)
    density = rng.uniform(0.05, 0.45)
    cells = [[rng.random() > density for _ in range(w)] for _ in range(h)]
    cells[0][0] = True
    cells[h - 1][w - 1] = True
    return GridInstance(grid=GridMap(width=w, height=h, grid=cells), start=(0, 0), goal=(w - 1, h - 1))


def simplify_grid_instance(instance: GridInstance) -> List[GridInstance]:
    """Candidate simplifications, from cheapest/most-likely-to-preserve-the-bug
    to more aggressive: (1) crop one row/column off an edge (moving start/goal
    inward with it if they sat on that edge, rather than skipping the crop --
    an earlier version skipped cropping whenever start or goal touched the edge
    being removed, which is *always* true for the corner-to-corner start/goal
    convention used here and made the shrinker stop far earlier than necessary;
    caught by inspecting an actual shrink run that stalled at the original grid
    size instead of reducing it, not assumed), and (2) unblock one obstacle cell
    at a time. Both strictly reduce the instance's "size" in a way delta-debugging
    can make monotonic progress on; neither can ever make the grid larger or add
    a new obstacle, so the shrink loop in src/proving/shrink.py is guaranteed to
    terminate.
    """
    g = instance.grid
    candidates: List[GridInstance] = []

    if g.width > 2:
        candidates.append(_cropped(instance, left=1))
        candidates.append(_cropped(instance, right=1))
    if g.height > 2:
        candidates.append(_cropped(instance, top=1))
        candidates.append(_cropped(instance, bottom=1))

    # Unblock one obstacle at a time (each is an independent candidate; the
    # shrink loop tries them in turn and keeps the first that still fails).
    for y in range(g.height):
        for x in range(g.width):
            if not g.grid[y][x]:
                candidates.append(_with_cell_unblocked(instance, x, y))

    return [c for c in candidates if c is not None]


def _cropped(instance: GridInstance, left=0, right=0, top=0, bottom=0) -> "GridInstance | None":
    g = instance.grid
    new_w, new_h = g.width - left - right, g.height - top - bottom
    if new_w < 2 or new_h < 2:
        return None
    new_rows = [row[left: g.width - right] for row in g.grid[top: g.height - bottom]]
    new_grid = GridMap(width=new_w, height=new_h, grid=new_rows)

    def _clamp(cell: Cell) -> Cell:
        x, y = cell[0] - left, cell[1] - top
        return (min(max(x, 0), new_w - 1), min(max(y, 0), new_h - 1))

    new_start, new_goal = _clamp(instance.start), _clamp(instance.goal)
    if new_start == new_goal:
        return None  # cropping collapsed start onto goal -- not a valid instance
    if not new_grid.passable(*new_start) or not new_grid.passable(*new_goal):
        return None  # clamping landed start/goal on an obstacle -- skip, don't force it open
    return GridInstance(grid=new_grid, start=new_start, goal=new_goal)


def _with_cell_unblocked(instance: GridInstance, x: int, y: int) -> GridInstance:
    g = instance.grid
    new_rows = [row[:] for row in g.grid]
    new_rows[y][x] = True
    new_grid = GridMap(width=g.width, height=g.height, grid=new_rows)
    return GridInstance(grid=new_grid, start=instance.start, goal=instance.goal)


def render(instance: GridInstance) -> str:
    lines = []
    for y, row in enumerate(instance.grid.grid):
        chars = []
        for x, passable in enumerate(row):
            if (x, y) == instance.start:
                chars.append("S")
            elif (x, y) == instance.goal:
                chars.append("G")
            else:
                chars.append("." if passable else "@")
        lines.append("".join(chars))
    return "\n".join(lines)
