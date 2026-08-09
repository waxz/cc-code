"""Space-time A* over the LaneGraph: state = (node, discretized timestep), so a
high-level constraint can be resolved by rerouting through a different node, not
only by waiting at the current one. This is what src/lane_graph/routing.py's
plain A* plus the wait-insertion loop in the planners never did -- see
docs/weaknesses_analysis.md section 1.1 for the measured cost of that gap (0%
success rate on the hardest tested sweep) and docs/benchmark_plan.md for the
original trace that found it.

This is standard technique, not a novel one: it is exactly the low-level search
Sharon et al. (2015)'s original CBS paper uses, and exactly what this project's
own src/baselines/grid_cbs.py::space_time_astar already does correctly on a
discrete grid (verified against hand-built cases in tests/test_grid_cbs.py). The
gap being closed here is that the *lane-graph* planners never got the same
treatment their own grid baseline already had -- not that space-time search
itself is new to this project.

Time discretization, and why: the lane-graph's edge costs are continuous (real
length / speed), but constraint windows need a shared, finite state space to
search over. TIME_RESOLUTION buckets time into fixed steps; a trajectory's
final committed timestamps are bucket-aligned (bucket * TIME_RESOLUTION), not
the raw unrounded travel time -- a small, disclosed suboptimality (an agent may
wait up to one bucket-width longer than physically necessary) traded for
guaranteed consistency between what the search reasons about and what the
conflict detector (src/lane_graph/conflicts.py) later checks against. Chosen to
equal conflicts.py's own default time_margin (0.5s) so bucket rounding doesn't
introduce spurious near-miss conflicts smaller than what the detector already
tolerates.
"""
from __future__ import annotations

import heapq
import itertools
import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from src.lane_graph.graph import LaneGraph
from src.lane_graph.routing import segment_direction
from src.lane_graph.trajectory import LaneLeg, NodeVisit, Trajectory

TIME_RESOLUTION = 0.5  # seconds -- matches conflicts.py's default time_margin
_MOVE_TIE_BREAK_EPS = 1e-4  # see space_time_search's Action 2 comment

EdgeFeasibleFn = Callable[[str], bool]
SegmentSpeedFn = Callable[[str], float]
HeuristicFn = Callable[[str], float]
# location, t_start, t_end (continuous seconds) -> True if forbidden
BlockedFn = Callable[[str, float, float], bool]

State = Tuple[str, int]  # (node_id, time_bucket)


def _to_bucket(t: float) -> int:
    return max(0, round(t / TIME_RESOLUTION))


def _to_time(bucket: int) -> float:
    return bucket * TIME_RESOLUTION


def space_time_search(
    graph: LaneGraph,
    agent_id: str,
    agent_class: str,
    half_length: float,
    start_node: str,
    goal_node: str,
    edge_feasible_fn: EdgeFeasibleFn,
    segment_speed_fn: SegmentSpeedFn,
    blocked_fn: BlockedFn,
    heuristic_fn: Optional[HeuristicFn] = None,
    start_time: float = 0.0,
    max_wait_buckets: int = 400,
) -> Optional[Trajectory]:
    """Search (node, time_bucket) states directly, so waiting and rerouting are
    both just ordinary actions the search can freely choose between, rather
    than rerouting being unavailable once a route is fixed. Returns a
    Trajectory with bucket-aligned timestamps, or None if the goal cannot be
    reached within max_wait_buckets of search depth from any reachable state
    (a generous bound, not a tight one -- this is a completeness improvement
    over the old wait-only scheme, not a claim of optimality within the
    discretized model).
    """
    start_bucket = _to_bucket(start_time)
    start_state: State = (start_node, start_bucket)
    h = heuristic_fn or (lambda node_id: 0.0)

    # An agent must eventually stop at its goal without ever again violating a
    # constraint there -- mirrors src/baselines/grid_cbs.py's goal_min_safe_t
    # trick: only accept the goal as final once no later constraint touches it.
    goal_min_safe_bucket = 0
    # blocked_fn doesn't expose raw constraint windows directly, so probe: if
    # the goal is blocked at any bucket up to a generous horizon, push the
    # earliest acceptable arrival past it. This is a bounded, honest scan
    # (not an unbounded search) capped by max_wait_buckets.
    probe = start_bucket
    while probe < start_bucket + max_wait_buckets:
        t0, t1 = _to_time(probe), _to_time(probe + 1)
        if blocked_fn(goal_node, t0, t1):
            goal_min_safe_bucket = probe + 1
        probe += 1

    g_score: Dict[State, float] = {start_state: 0.0}
    came_from: Dict[State, Tuple[State, Optional[str]]] = {}
    visited = set()
    counter = itertools.count()
    heap = [(h(start_node), next(counter), start_state)]

    result_state: Optional[State] = None

    while heap:
        _, _, state = heapq.heappop(heap)
        if state in visited:
            continue
        visited.add(state)
        node, tb = state

        if node == goal_node and tb >= goal_min_safe_bucket:
            result_state = state
            break
        if tb - start_bucket >= max_wait_buckets:
            continue

        # Action 1: wait one bucket at this node.
        wait_state = (node, tb + 1)
        t0, t1 = _to_time(tb), _to_time(tb + 1)
        if not blocked_fn(node, t0, t1):
            ng = g_score[state] + TIME_RESOLUTION
            if wait_state not in g_score or ng < g_score[wait_state]:
                g_score[wait_state] = ng
                came_from[wait_state] = (state, None)
                heapq.heappush(heap, (ng + h(node), next(counter), wait_state))

        # Action 2: traverse a feasible outgoing segment.
        for seg_id in graph.neighbors(node):
            if not edge_feasible_fn(seg_id):
                continue
            seg = graph.segments[seg_id]
            other = seg.end_node if seg.start_node == node else seg.start_node
            if other == node:
                continue
            speed = segment_speed_fn(seg_id)
            travel_time = seg.length / speed
            travel_buckets = max(1, round(travel_time / TIME_RESOLUTION))
            new_tb = tb + travel_buckets
            t0, t1 = _to_time(tb), _to_time(new_tb)
            if blocked_fn(seg_id, t0, t1) or blocked_fn(other, t0, t1):
                continue
            new_state = (other, new_tb)
            # A tiny tie-break penalty on movement, not enough to ever change
            # which of two genuinely different-duration paths is cheaper, but
            # enough to prefer "wait in place" over "move away and back" when
            # both cost exactly the same in the discretized model. Without
            # this, the search has no reason to prefer the simpler option and
            # can return needlessly oscillating paths (e.g. traverse a segment
            # and immediately traverse it back) whenever a node is
            # temporarily blocked -- each such bounce creates a new,
            # hard-to-predict segment-occupancy window that can trigger fresh
            # conflicts with other agents, compounding CBS's already
            # documented slow convergence on head-on single-corridor cases
            # (a recognized case in the literature needing dedicated
            # "corridor reasoning" this project doesn't implement -- see
            # docs/space_time_routing_results.md). Found by tracing an actual
            # stuck search and seeing a fabricated-looking multi-bounce path
            # in a real returned trajectory, not assumed necessary in advance.
            ng = g_score[state] + travel_buckets * TIME_RESOLUTION + _MOVE_TIE_BREAK_EPS
            if new_state not in g_score or ng < g_score[new_state]:
                g_score[new_state] = ng
                came_from[new_state] = (state, seg_id)
                heapq.heappush(heap, (ng + h(other), next(counter), new_state))

    if result_state is None:
        return None

    # Reconstruct: walk came_from back to start, collecting (segment_id or
    # None-for-wait) transitions, then build the Trajectory forward.
    chain: List[Tuple[State, Optional[str]]] = []
    state = result_state
    while state in came_from:
        prev_state, seg_id = came_from[state]
        chain.append((state, seg_id))
        state = prev_state
    chain.reverse()

    traj = Trajectory(agent_id=agent_id, agent_class=agent_class, half_length=half_length)
    cur_node = start_node
    cur_bucket = start_bucket
    for (next_node_state, seg_id) in chain:
        next_node, next_bucket = next_node_state
        t_start, t_end = _to_time(cur_bucket), _to_time(next_bucket)
        if seg_id is None:
            # wait action: record as a node-visit dwell, no new leg
            pass
        else:
            seg = graph.segments[seg_id]
            forward = segment_direction(graph, seg_id, cur_node)
            s_start, s_end = (0.0, seg.length) if forward else (seg.length, 0.0)
            traj.legs.append(
                LaneLeg(segment_id=seg_id, s_start=s_start, s_end=s_end, t_start=t_start, t_end=t_end)
            )
        traj.node_visits.append(NodeVisit(node_id=cur_node, t_enter=t_start, t_exit=t_end))
        cur_node, cur_bucket = next_node, next_bucket

    traj.node_visits.append(NodeVisit(node_id=cur_node, t_enter=_to_time(cur_bucket), t_exit=_to_time(cur_bucket)))
    return traj
