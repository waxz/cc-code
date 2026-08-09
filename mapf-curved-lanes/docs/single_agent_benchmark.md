# Single-Agent Global Path Planner Benchmark

Multi-agent path finding sits on top of single-agent search: every low-level
planner call in `src/planners/` is, at its core, one shortest-path query. If that
query is slow or wrong, the multi-agent layer inherits both problems no matter how
good the high-level conflict resolution is. This document benchmarks and improves
that foundation directly, on a standard, citable dataset, rather than only on this
project's own generated instances.

## Dataset

`data/movingai/random-32-32-20.map` + `random-32-32-20-random-1.scen`: Sturtevant's
MovingAI 2D Pathfinding Benchmark (Sturtevant, 2012), the de facto standard
single-agent (and multi-agent) pathfinding benchmark — see
`data/movingai/PROVENANCE.md` for full citation and format details. 409 real
start/goal scenario instances on a 32×32 grid with 20% random obstacle density,
each with a known-optimal path length (octile distance, corner-cutting
disallowed).

## Method

`src/single_agent/grid_planners.py` implements two 8-connected, octile-cost
planners over `src/single_agent/movingai_io.py`'s parsed grid:

- **`dijkstra`**: uniform-cost search, no heuristic — the baseline.
- **`astar`**: same search, guided by the octile-distance heuristic, which is
  admissible and consistent for this exact cost model, so it cannot change
  solution *quality* — only search *effort*.

`src/benchmark/single_agent_benchmark.py` runs both over every scenario and checks
each result against the scenario file's own known-optimal length (not just "a path
was found") as the success criterion.

## Result (measured, not asserted)

```
astar      n= 409  success_rate=100.00%  avg_nodes_expanded=    69.6  avg_runtime=0.478ms
dijkstra   n= 409  success_rate=100.00%  avg_nodes_expanded=   397.0  avg_runtime=1.989ms
astar reduces total nodes expanded by 82.5% vs. dijkstra (162365 -> 28448), at identical solution cost (both optimal)
```

Success rate was already 100% for both planners — these are curated, connected,
solvable instances, so there was no headroom to improve there. The real,
measurable improvement is in the performance metric: A* expands 82.5% fewer nodes
and runs about 4x faster than Dijkstra, for the exact same optimal-cost solution on
every one of the 409 real scenarios. This matches textbook expectations for A* with
an admissible, consistent heuristic on a uniform grid — the contribution here is
confirming it empirically on a real dataset rather than assuming it, and then
actually propagating the result rather than leaving it as an isolated finding.

## Propagating the result into the multi-agent solver

`src/lane_graph/routing.py` — the router every low-level planner in
`src/planners/` calls — was plain Dijkstra with no heuristic. It is now A*, with
`heuristic_fn` optional (defaults to Dijkstra behavior for any future caller that
doesn't supply one, so this is backward-compatible, not a breaking change).

The heuristic used is straight-line distance to the goal divided by the agent's
maximum possible speed. This is proven admissible for this project's specific
lane-graph, not assumed: every segment's length is constructed to be at least the
straight-line distance between its own two endpoints (grid segments: exactly
equal; curved shortcuts: deliberately longer — see
`src/benchmark/generate_instances.py`), so by the triangle inequality any full
path's length is at least the straight-line start-to-goal distance; and an agent's
speed on any segment is capped at its flat `max_speed` and never exceeds it (see
`ForkliftPlanner._segment_speed`), so dividing by that flat maximum can only
under-estimate, never over-estimate, the true remaining time. Both conditions
together are exactly what admissibility requires.

**Verification, not assumption**: all 24 pre-existing tests — including the
load-dependent curvature routing test and both head-on conflict-resolution tests —
pass unchanged after this swap, confirming the heuristic didn't alter any solution,
only the search effort to find it (`tests/test_lane_graph.py::
test_astar_heuristic_matches_dijkstra_on_lane_graph` locks this in directly at the
routing level, not just via downstream test survival).

## What this doesn't (yet) fix

This benchmark and upgrade address search *efficiency* on a fixed graph. It does
not address the documented completeness limitation from `docs/benchmark_plan.md`
(the low-level planner still can't reroute around a contested segment once
constrained by the high-level search, only wait) — that's a different problem
(constraint handling, not base-case search speed) and PIBT/db-LaCAM
(`docs/improvement_plan.md`) remain the identified fix for it. A faster single-agent
search makes replanning under constraints cheaper per attempt, which helps, but
doesn't by itself make the search complete.
