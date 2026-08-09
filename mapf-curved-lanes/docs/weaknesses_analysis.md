# Weaknesses and Limitations Analysis

This consolidates every weakness found across this project's algorithms into one
place, ranked by how much it actually costs in measured results (not by how
interesting it is to discuss), and identifies which one is worth fixing next.
Every claim here links to where it was measured, not asserted.

## 1. Ranked by measured impact

### 1.1 `ours_full` (this project's lane-graph CBS/PBS solver) — CRITICAL

**The weakness**: the low-level planner (`src/planners/forklift_planner.py`,
`quadruped_planner.py`) computes a route once via A* and, when the high-level
search adds a constraint, only inserts a wait — it never tries an alternate
route around the constrained segment.

**Measured cost**: 0% success rate on the medium-map, 10/15-agent sweep in
`docs/algorithm_comparison_report.md` §4 — the worst result of any algorithm
tested, on the same difficulty tier where `grid_cbs` and `pibt` both still
solved ~22% of instances. On the easier 32-instance sweep (§3), 25.00% —
still last place. Root cause confirmed by tracing an actual non-converging
instance (`docs/benchmark_plan.md`): the high-level search explores hundreds
of branches that all plateau at the same cost, the signature of a genuine
completeness gap, not an expansion-budget shortfall (verified by re-running at
5000 expansions with zero improvement).

**This is the single highest-leverage fix available.** Attempted in this
document's companion work — see `docs/space_time_routing_results.md` for the
full, honest result: real space-time search was implemented and verified
correct (rerouting works), but did **not** improve aggregate benchmark success
rate (unchanged at 25.00%) and made runtime substantially worse (7.4x slower),
because it exposes a different, well-documented CBS limitation (slow
convergence on single-corridor head-on cases, a recognized gap requiring
dedicated "corridor reasoning" this project doesn't implement). The revised
recommendation is a different high-level algorithm for the lane-graph (a
PIBT-style search, reusing the space-time state representation but replacing
CBS's branching), not further low-level patching — see that document's §5.

### 1.2 `grid_cbs` (classical grid-CBS baseline) — MODERATE

**The weakness**: exhaustive branch-and-bound on the conflict tree, no
symmetry-breaking or bypass heuristics (disclosed in the module docstring at
implementation time).

**Measured cost**: average runtime 1.17s vs. PIBT's 0.0017s on the same
32-instance sweep — roughly 687x slower — and one single instance took 12.1s
(§4 of the comparison report). This is expected for an unoptimized, from-scratch
CBS reimplementation (real competition-grade CBS variants add bypass,
prioritized conflicts, and symmetry reasoning this one doesn't) and is not a
correctness problem — `grid_cbs` is independently verified against hand-built
cases (`tests/test_grid_cbs.py`) and never produced a wrong answer, only a slow
one on hard instances.

**Not the highest priority to fix**: `grid_cbs` exists as a baseline to measure
*against*, not as this project's deliverable solver. Speeding it up would make
it a better baseline but doesn't advance the actual research contribution.

### 1.3 `pibt` (Priority Inheritance with Backtracking) — MODERATE, but by design

**The weakness**: no completeness or optimality guarantee outside biconnected
graphs; static priorities (not the literature's starvation-aware dynamic
scheme) mean a low-priority agent can in principle be perpetually deprioritized
in longer-running scenarios, though this wasn't observed in the measured runs.

**Measured cost**: average solved cost 44.14 vs. `grid_cbs`'s 39.00 on the same
instances and cost model (§3 of the comparison report) — roughly 13% worse
solution quality, the expected and disclosed trade for PIBT's ~687x speed
advantage. This is not really a "weakness" so much as the literature's own
stated trade-off, measured rather than assumed to hold here too.

**Two real implementation bugs were already found and fixed** (candidate-
ordering deadlock, goal-oscillation) — see `docs/algorithm_comparison_report.md`
and `src/baselines/pibt.py`'s module docstring. Both are closed, not open
weaknesses.

### 1.4 `jps` (single-agent Jump Point Search) — MINOR, disclosed

**The weakness**: targets a corner-cutting-*allowed* cost model, not the same
one `dijkstra()`/`astar()`/this project's other planners use, so it cannot be
swapped in as a drop-in replacement without translating that difference.

**Measured cost**: solved cost matches the benchmark's strict optimal on only
77/409 (18.8%) real scenarios, strictly better (a corner-cutting shortcut
exists) on 332/409 — quantified precisely in `docs/single_agent_benchmark.md`,
not a defect, a disclosed scope boundary. Separately, node-count reduction
(64.1% fewer than `astar`) didn't translate proportionally into wall-clock
speedup (~13%) due to Python recursion overhead — an honest, measured nuance
already documented.

**Not on the critical path**: this affects single-agent search efficiency, one
level below where the critical weakness (§1.1) actually costs solved instances.

### 1.5 `dijkstra`/`astar` (single-agent baseline planners) — NONE FOUND

20,000+ fuzz trials (`src/proving/`) plus 409 real MovingAI scenarios, 0
failures. No open weakness identified. Included here for completeness of the
ranking, not because there's anything to report.

## 2. What "advanced technology" means here, concretely

Not a euphemism for "try something impressive-sounding" — the specific,
established technique that fixes §1.1 is **space-time search**: instead of
computing one static route and only ever waiting under a constraint, search
directly over an expanded state space of `(node, discretized timestep)` pairs,
the same technique this project's own `grid_cbs` baseline
(`src/baselines/grid_cbs.py::space_time_astar`) already uses correctly and has
verified against hand-built cases. This is standard, well-understood CBS
low-level search (Sharon et al. 2015's own low-level planner is exactly this);
the gap was that this project's lane-graph planners never got the same
treatment their own grid baseline already had.

## 3. What was attempted, and the honest result

See `docs/space_time_routing_results.md` for the full writeup. Summary: real
space-time search (`src/lane_graph/space_time_routing.py`) was implemented,
verified correct in isolation (rerouting genuinely works), and integrated into
both planners, fixing two real bugs found along the way (a zero-width
conflict-detector boundary bug, a needless-oscillation tie-break bug). It did
**not** improve this project's measured success rate on the standard benchmark
sweep (unchanged, 25.00%) and made runtime 7.4x worse, because it exposes CBS's
own well-documented slow convergence on single-corridor head-on cases more
severely than the old, more restricted wait-only scheme happened to. The
revised recommendation is a PIBT-style high-level search for the lane-graph,
not further CBS low-level patching — this project has already measured PIBT
does not share this failure mode, and runs ~687x faster besides
(`docs/algorithm_comparison_report.md`).
