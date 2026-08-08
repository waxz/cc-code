"""Classical grid-based CBS baseline (Sharon et al., 2015), used per
docs/benchmark_plan.md baseline #1: point-mass agents on a plain 4-connected grid
derived from the same instance's node positions, ignoring lane curvature and load
dependence entirely. This measures what's lost by treating the environment as a grid
-- the comparison this whole project's research gap is motivated by.

Independent implementation of the standard algorithm: time-expanded (space-time) A*
per agent for the low level, conflict-tree branching on the first vertex or edge
conflict for the high level. Same shape as src/high_level/conflict_tree.py, just
specialized to discrete grid cells and integer timesteps instead of continuous
lane-graph geometry, since a completely separate implementation is the honest way to
get a baseline that isn't accidentally biased by this project's own design choices.

Known simplifications, disclosed rather than hidden: waiting at the goal beyond the
computed "safe" time isn't re-validated against constraints created *after* an agent
is deemed done (handled via goal_min_safe_t below, which covers the common case but
not every pathological ordering); there's no symmetry-breaking or bypass heuristic,
so this will be slower than a tuned CBS on larger instances.
"""
from __future__ import annotations

import heapq
import itertools
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from src.benchmark.generate_instances import AgentSpec
from src.lane_graph.graph import LaneGraph

Cell = Tuple[int, int]
MOVES = [(0, 1), (0, -1), (1, 0), (-1, 0), (0, 0)]  # 4-connected + wait-in-place


@dataclass
class GridAgent:
    agent_id: str
    start: Cell
    goal: Cell


def instance_to_grid(
    graph: LaneGraph, agent_specs: List[AgentSpec], cell_size: float = 5.0
) -> Tuple[List[GridAgent], int, int]:
    """Discretize node positions onto a grid and snap each agent's start/goal node
    to its nearest cell. No obstacles -- an open grid covering the node bounding box,
    which is the simplest faithful "ignore the lane structure" baseline.
    """
    xs = [n.position[0] for n in graph.nodes.values()]
    ys = [n.position[1] for n in graph.nodes.values()]
    x_min, y_min = min(xs), min(ys)
    width = max(1, int((max(xs) - x_min) // cell_size) + 1)
    height = max(1, int((max(ys) - y_min) // cell_size) + 1)

    def to_cell(node_id: str) -> Cell:
        pos = graph.nodes[node_id].position
        cx = int((pos[0] - x_min) // cell_size)
        cy = int((pos[1] - y_min) // cell_size)
        return (min(cx, width - 1), min(cy, height - 1))

    agents = [
        GridAgent(agent_id=a.agent_id, start=to_cell(a.start_node), goal=to_cell(a.goal_node))
        for a in agent_specs
    ]
    return agents, width, height


def _in_bounds(cell: Cell, width: int, height: int) -> bool:
    x, y = cell
    return 0 <= x < width and 0 <= y < height


def space_time_astar(
    start: Cell,
    goal: Cell,
    width: int,
    height: int,
    vertex_constraints: Set[Tuple[Cell, int]],
    edge_constraints: Set[Tuple[Cell, Cell, int]],
    max_t: int,
) -> Optional[List[Cell]]:
    """Time-expanded A*: state = (cell, timestep). Returns a list of cells, one per
    timestep from t=0 to arrival, or None if no path is found within max_t steps.
    """
    goal_min_safe_t = -1
    for (cell, t) in vertex_constraints:
        if cell == goal and t > goal_min_safe_t:
            goal_min_safe_t = t

    def h(cell: Cell) -> int:
        return abs(cell[0] - goal[0]) + abs(cell[1] - goal[1])

    counter = itertools.count()
    open_heap = [(h(start), next(counter), start, 0)]
    came_from: Dict[Tuple[Cell, int], Tuple[Cell, int]] = {}
    g_score = {(start, 0): 0}

    while open_heap:
        _, _, cell, t = heapq.heappop(open_heap)
        if cell == goal and t > goal_min_safe_t:
            path = [cell]
            state = (cell, t)
            while state in came_from:
                state = came_from[state]
                path.append(state[0])
            path.reverse()
            return path
        if t >= max_t:
            continue
        for dx, dy in MOVES:
            ncell = (cell[0] + dx, cell[1] + dy)
            if not _in_bounds(ncell, width, height):
                continue
            nt = t + 1
            if (ncell, nt) in vertex_constraints:
                continue
            if (cell, ncell, nt) in edge_constraints:
                continue
            ng = g_score[(cell, t)] + 1
            key = (ncell, nt)
            if key not in g_score or ng < g_score[key]:
                g_score[key] = ng
                came_from[key] = (cell, t)
                heapq.heappush(open_heap, (ng + h(ncell), next(counter), ncell, nt))
    return None


def _first_conflict(paths: Dict[str, List[Cell]]):
    agent_ids = sorted(paths.keys())
    max_len = max(len(p) for p in paths.values())
    padded = {aid: p + [p[-1]] * (max_len - len(p)) for aid, p in paths.items()}

    for t in range(max_len):
        occupied: Dict[Cell, str] = {}
        for aid in agent_ids:
            c = padded[aid][t]
            if c in occupied:
                return ("vertex", occupied[c], aid, c, t)
            occupied[c] = aid

    for t in range(max_len - 1):
        for a, b in itertools.combinations(agent_ids, 2):
            if padded[a][t] == padded[b][t + 1] and padded[a][t + 1] == padded[b][t]:
                return ("edge", a, b, (padded[a][t], padded[a][t + 1]), t + 1)

    return None


@dataclass
class GridCBSNode:
    vertex_constraints: Dict[str, Set[Tuple[Cell, int]]]
    edge_constraints: Dict[str, Set[Tuple[Cell, Cell, int]]]
    paths: Dict[str, List[Cell]]
    cost: int

    def __lt__(self, other: "GridCBSNode") -> bool:
        return self.cost < other.cost


@dataclass
class GridCBSResult:
    success: bool
    paths: Dict[str, List[Cell]] = field(default_factory=dict)
    sum_of_costs: int = 0
    makespan: int = 0
    runtime_s: float = 0.0
    high_level_expansions: int = 0


def solve_grid_cbs(
    agents: List[GridAgent], width: int, height: int, max_t: int = 200, max_expansions: int = 2000
) -> GridCBSResult:
    t0 = time.perf_counter()

    def plan_all(vertex_c, edge_c) -> Optional[Dict[str, List[Cell]]]:
        paths = {}
        for a in agents:
            path = space_time_astar(
                a.start, a.goal, width, height,
                vertex_c.get(a.agent_id, set()), edge_c.get(a.agent_id, set()), max_t,
            )
            if path is None:
                return None
            paths[a.agent_id] = path
        return paths

    root_paths = plan_all({}, {})
    if root_paths is None:
        return GridCBSResult(success=False, runtime_s=time.perf_counter() - t0)

    root = GridCBSNode(
        vertex_constraints={}, edge_constraints={}, paths=root_paths,
        cost=sum(len(p) for p in root_paths.values()),
    )
    open_list = [root]
    heapq.heapify(open_list)
    expansions = 0

    while open_list and expansions < max_expansions:
        node = heapq.heappop(open_list)
        expansions += 1

        conflict = _first_conflict(node.paths)
        if conflict is None:
            makespan = max(len(p) for p in node.paths.values()) - 1
            return GridCBSResult(
                success=True, paths=node.paths,
                sum_of_costs=sum(len(p) - 1 for p in node.paths.values()),
                makespan=makespan, runtime_s=time.perf_counter() - t0,
                high_level_expansions=expansions,
            )

        kind = conflict[0]
        if kind == "vertex":
            _, agent_a, agent_b, cell, t = conflict
            branches = [(agent_a, ("vertex", cell, t)), (agent_b, ("vertex", cell, t))]
        else:
            _, agent_a, agent_b, edge, t = conflict
            branches = [
                (agent_a, ("edge", edge, t)),
                (agent_b, ("edge", (edge[1], edge[0]), t)),
            ]

        for agent, constraint in branches:
            new_vc = {k: set(v) for k, v in node.vertex_constraints.items()}
            new_ec = {k: set(v) for k, v in node.edge_constraints.items()}
            if constraint[0] == "vertex":
                new_vc.setdefault(agent, set()).add((constraint[1], constraint[2]))
            else:
                _, edge, t = constraint
                new_ec.setdefault(agent, set()).add((edge[0], edge[1], t))

            new_paths = plan_all(new_vc, new_ec)
            if new_paths is None:
                continue
            child = GridCBSNode(
                vertex_constraints=new_vc, edge_constraints=new_ec, paths=new_paths,
                cost=sum(len(p) for p in new_paths.values()),
            )
            heapq.heappush(open_list, child)

    return GridCBSResult(
        success=False, runtime_s=time.perf_counter() - t0, high_level_expansions=expansions
    )
