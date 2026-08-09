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

## Reproducing a GPPC-relevant SOTA algorithm: Jump Point Search

The Grid-Based Path Planning Competition (GPPC) doesn't have a single "best"
algorithm — results are reported as a Pareto frontier trading solution quality,
query speed, and preprocessing cost. But every current frontier entry that
preserves optimality without heavy preprocessing (JPS+BB, JPS+ with geometric
containers) is Jump Point Search (Harabor & Grastien, 2011) plus additional
engineering on top, not a different search — so JPS is the right thing to
reproduce first, and `src/single_agent/grid_planners.py::jps` does.

### A real correctness bug, found and fixed by testing, not by inspection

The first implementation attempted to target the same corner-cutting-disallowed
cost model as `dijkstra()`/`astar()`. It was wrong: fuzz-testing against `dijkstra()`
on small random grids (not hand-picked cases) found it failed on **388 of 409**
real MovingAI scenarios and roughly **44% of random fuzz instances**. The root
cause is a real algorithmic subtlety, not a typo: classical JPS's pruning proof
relies on a diagonal shortcut being geometrically available everywhere along a
straight run, which lets an optimal path be "canonicalized" to change direction
only at genuine forced-neighbor cells. That assumption is simply false once
diagonal moves require both orthogonal corner cells to be open — a diagonal
blocked at one point along a straight run can become available a few cells later
purely from local wall geometry, with no "hole in the wall" of the kind the
classical forced-neighbor test looks for.

One targeted fix attempt (stop the scan whenever a forward diagonal newly becomes
available) reduced but did not eliminate the problem (down to ~44% failures from
~53%, on a larger fuzz run). Rather than keep patching an approach that kept
finding new counterexamples — and risk shipping something that looks fixed on the
cases checked but isn't actually correct — the implementation was rescoped to
target the classical, corner-cutting-**allowed** model instead, which is
unambiguously specified in the literature. That version was then fuzz-tested
against a matching-model Dijkstra (`dijkstra_allow_corner_cutting`) across 20,000
randomized grids of varying size and obstacle density: **0 mismatches**. It also
matches on all 409 real scenarios exactly (`self_consistent_rate=100.00%`). A
smaller bug was found and fixed in this pass too — an erroneous extra `AND`
condition on the diagonal forced-neighbor check that isn't part of the standard
formula, caught by the same fuzz harness at a ~1.4% failure rate before the fix.

A correct **no-corner-cutting** JPS remains explicitly out of scope here, flagged
as follow-up work rather than silently claimed done.

### Consequence of the cost-model difference, quantified rather than assumed

Because JPS targets a more permissive model, its solved cost can be strictly
*below* a scenario's own no-corner-cut `optimal_length` wherever a corner shortcut
exists. Measured on all 409 real scenarios:

```
astar      n= 409  success_rate=100.00%  avg_nodes_expanded=    69.6  avg_runtime=0.312ms
dijkstra   n= 409  success_rate=100.00%  avg_nodes_expanded=   397.0  avg_runtime=1.286ms
jps        n= 409  self_consistent_rate=100.00%  avg_nodes_expanded=    25.0  avg_runtime=0.268ms
astar reduces total nodes expanded by 82.5% vs. dijkstra (162365 -> 28448), at identical solution cost (both optimal)
jps reduces total nodes expanded by 64.1% vs. astar (28448 -> 10221) -- different cost model (corner-cutting
allowed), so not a same-cost comparison: jps cost equals the benchmark's stricter no-cut optimal on 77/409 scenarios
and is strictly lower (a corner shortcut exists) on 332/409
```

JPS's cost matched the benchmark's strict optimal on only 77/409 (18.8%) scenarios
and was strictly lower on 332/409 (81.2%) — the majority of these random-obstacle
instances have at least one exploitable corner shortcut. This is reported as a
property of the (deliberately different) cost model, not an error.

### Honest nuance: node reduction didn't translate proportionally to wall-clock

JPS visits 64.1% fewer nodes than A*, but total runtime only dropped from 127.5ms
to 110.7ms (~13%) across all 409 scenarios — far less than the node-count
reduction would suggest. This is a real, measured finding, not the "JPS is 10-100x
faster" result often quoted for compiled implementations: `jps()`'s recursive
`_jump` function does meaningfully more work *per node visited* than `astar()`'s
flat neighbor loop (recursive Python function calls, repeated re-scanning along
each direction), so Python's per-call overhead cancels a large fraction of the
algorithmic advantage. A compiled implementation (C++/Rust, or at minimum an
iterative rather than recursive `_jump`) would be expected to realize much more
of the node-count reduction as actual wall-clock speedup — that gap is exactly
what "improve this algorithm to compete with the best" means concretely here,
and is the identified next step rather than a claim already delivered.

### What would be needed to actually compete with GPPC frontier entries

Current GPPC-competitive optimal methods (JPS+BB, JPS+ with geometric containers)
add offline preprocessing on top of JPS — precomputed jump distances or bounding
regions that turn repeated symmetry-scanning into O(1) lookups. Suboptimal methods
using Compressed Path Databases report sub-microsecond query times (per "Sub-
Microsecond Grid Path Planning", GPPC 2025), but trade a heavyweight offline
preprocessing/compression pipeline for that speed. Neither is implemented here —
both require real preprocessing infrastructure this project doesn't have yet, and
claiming to match sub-microsecond, heavily-preprocessed competition entries with
an unpreprocessed pure-Python search would be dishonest. The concrete, scoped next
steps, in order of effort: (1) make `_jump` iterative instead of recursive to
recover more of the measured node-reduction as wall-clock speedup; (2) add JPS+
preprocessing (precomputed jump points) if the map is static and queried
repeatedly, which is exactly this project's actual use case (a fixed warehouse
layout); (3) CPD-based methods only if sub-millisecond single-query latency
becomes an actual requirement, which it is not yet for this project's current
scale.
