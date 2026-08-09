"""Shortest-path routing over a LaneGraph, filtering edges by kinematic feasibility.

This is the piece that turns "load-dependent curvature bound" from a number sitting
in ForkliftKinematicProfile into something that actually changes which routes are
available: a lane segment whose curvature exceeds an agent's current curvature bound
is simply not traversable by that agent in that load state, so a laden forklift may
be forced onto a longer route (or find no route at all) where an empty one, or a
holonomic quadruped, would not be.

Scope note: this is a discrete route-selection planner over the pre-built lane-graph,
not a continuous-space Reeds-Shepp curve generator. See
src/planners/forklift_planner.py for why that's the deliberate simplification here
and what upgrading to real curve generation would involve.

Search algorithm: A* with an optional heuristic (falls back to exact Dijkstra when
none is given, so existing callers that don't pass one are unaffected). This
upgrade is not speculative -- it's the direct, measured follow-up from
src/single_agent/grid_planners.py's benchmark against the MovingAI dataset
(docs/single_agent_benchmark.md), which found A* expands ~83% fewer nodes than
Dijkstra at identical optimal cost on a standard, citable benchmark. The heuristic
used by the planners here (straight-line distance to goal, divided by the agent's
fastest possible speed) is constructed to stay admissible for this graph's time-cost
model -- see forklift_planner.py/quadruped_planner.py for the actual heuristic and
why it can't overestimate.
"""
from __future__ import annotations

import heapq
import itertools
from typing import Callable, List, Optional

from src.lane_graph.graph import LaneGraph

EdgeCostFn = Callable[[str], float]       # segment_id -> traversal time
EdgeFeasibleFn = Callable[[str], bool]    # segment_id -> can this agent use it?
HeuristicFn = Callable[[str], float]      # node_id -> admissible lower-bound time-to-goal


def shortest_path(
    graph: LaneGraph,
    start_node: str,
    goal_node: str,
    edge_cost_fn: EdgeCostFn,
    edge_feasible_fn: EdgeFeasibleFn,
    heuristic_fn: Optional[HeuristicFn] = None,
) -> Optional[List[str]]:
    """A* over junction nodes, edges = lane segments (degrades to exact Dijkstra if
    heuristic_fn is None). Returns the ordered list of segment_ids from start_node
    to goal_node, or None if no feasible route exists (e.g. every route to the goal
    requires a curve tighter than this agent, in its current load state, can take).

    heuristic_fn must be admissible (never overestimate the true remaining cost) or
    the returned path is not guaranteed optimal -- this function doesn't verify
    that, it trusts the caller, so see the callers for why their heuristics qualify.
    """
    if start_node == goal_node:
        return []
    if start_node not in graph.nodes or goal_node not in graph.nodes:
        raise KeyError(f"unknown node(s): {start_node}, {goal_node}")

    h = heuristic_fn or (lambda node_id: 0.0)  # h==0 everywhere reduces A* to Dijkstra

    dist = {start_node: 0.0}
    prev_segment = {}
    prev_node = {}
    visited = set()
    counter = itertools.count()
    heap = [(h(start_node), next(counter), start_node)]

    while heap:
        _, _, node = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        if node == goal_node:
            break

        for seg_id in graph.neighbors(node):
            if not edge_feasible_fn(seg_id):
                continue
            seg = graph.segments[seg_id]
            other = seg.end_node if seg.start_node == node else seg.start_node
            if other == node:
                continue  # self-loop, shouldn't occur but guard anyway
            nd = dist[node] + edge_cost_fn(seg_id)
            if other not in dist or nd < dist[other]:
                dist[other] = nd
                prev_segment[other] = seg_id
                prev_node[other] = node
                heapq.heappush(heap, (nd + h(other), next(counter), other))

    if goal_node not in dist:
        return None

    path = []
    node = goal_node
    while node != start_node:
        path.append(prev_segment[node])
        node = prev_node[node]
    path.reverse()
    return path


def segment_direction(graph: LaneGraph, segment_id: str, from_node: str) -> bool:
    """True if traversing segment_id from from_node runs s: 0 -> length (forward);
    False if it runs length -> 0 (the agent enters from the segment's end_node).
    """
    seg = graph.segments[segment_id]
    if seg.start_node == from_node:
        return True
    if seg.end_node == from_node:
        return False
    raise ValueError(f"{from_node} is not an endpoint of segment {segment_id}")
