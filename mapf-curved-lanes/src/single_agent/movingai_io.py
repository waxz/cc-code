"""Parser for Sturtevant's MovingAI benchmark .map and .scen formats.

Format reference: https://movingai.com/benchmarks/formats.html (also mirrored,
practically, by every MAPF paper's own repo that includes example files -- see
data/movingai/PROVENANCE.md for this project's specific source and citation).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

PASSABLE_CHARS = {".", "G"}  # everything else ('@', 'O', 'T', ...) is blocked.
# Simplification, disclosed: the format also defines 'S' (swamp, passable but
# costly) and 'W' (water, traversable but not from regular terrain), which this
# parser treats as blocked rather than modeling their special traversal rules --
# none of the standard benchmark maps (random/maze/room/game/street) use them, so
# this doesn't affect results on the data actually included in this repo.


@dataclass
class GridMap:
    width: int
    height: int
    grid: List[List[bool]]  # grid[y][x] == True means passable

    def passable(self, x: int, y: int) -> bool:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        return self.grid[y][x]


@dataclass
class ScenEntry:
    map_file: str
    map_width: int
    map_height: int
    start: Tuple[int, int]
    goal: Tuple[int, int]
    optimal_length: float


def load_map(path: Path) -> GridMap:
    lines = Path(path).read_text().splitlines()
    if not lines[0].startswith("type"):
        raise ValueError(f"{path}: expected MovingAI map header, got {lines[0]!r}")
    height = int(lines[1].split()[1])
    width = int(lines[2].split()[1])
    if lines[3].strip() != "map":
        raise ValueError(f"{path}: expected 'map' marker on line 4, got {lines[3]!r}")

    rows = lines[4 : 4 + height]
    if len(rows) != height:
        raise ValueError(f"{path}: expected {height} map rows, got {len(rows)}")

    grid = [[c in PASSABLE_CHARS for c in row] for row in rows]
    for y, row in enumerate(grid):
        if len(row) != width:
            raise ValueError(f"{path}: row {y} has width {len(row)}, expected {width}")

    return GridMap(width=width, height=height, grid=grid)


def load_scen(path: Path) -> List[ScenEntry]:
    lines = Path(path).read_text().splitlines()
    if not lines[0].startswith("version"):
        raise ValueError(f"{path}: expected 'version' header, got {lines[0]!r}")

    entries = []
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 9:
            raise ValueError(f"{path}: expected 9 tab-separated fields, got {len(parts)}")
        _bucket, map_file, map_w, map_h, sx, sy, gx, gy, opt_len = parts
        entries.append(
            ScenEntry(
                map_file=map_file,
                map_width=int(map_w),
                map_height=int(map_h),
                start=(int(sx), int(sy)),
                goal=(int(gx), int(gy)),
                optimal_length=float(opt_len),
            )
        )
    return entries
