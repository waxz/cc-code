# Heterogeneous Multi-Agent Path Finding on Curved Lane Networks (HMAPF-CL)

Research codebase for multi-agent path finding (MAPF) with **heterogeneous, non-point-mass
agents** (car-like vehicles such as forklifts, and legged robots such as quadrupeds) operating
on a **continuous, curved lane-graph map** rather than a discrete grid.

## Motivation

Existing MAPF work covers each piece of this problem separately, but not the combination:

- **CL-CBS** (Wen et al., 2021) plans car-like robots on continuous curves (Reeds–Shepp paths)
  using a body-conflict tree, but assumes a single, fixed kinematic model per agent — a
  forklift's turning radius and stability margin do not change with load.
- **HCBS** (2025) mixes holonomic and non-holonomic agents in one conflict tree, but each
  agent's kinematic model is still fixed for the whole mission.
- No existing work combines wheeled (car-like) and legged agents, whose motion primitives are
  fundamentally different (a quadruped can turn in place or sidestep; a forklift cannot), on a
  **curved lane-graph** map representative of a real warehouse/factory floor rather than a grid
  or unconstrained continuous workspace.

This project implements a solver that:

1. Represents the environment as a **lane-graph** (clothoid/spline segments + junction nodes)
   instead of a 4/8-connected grid, so conflict checking on straight lane segments reduces to a
   1-D arc-length interval overlap, with full swept-volume checks reserved for junctions.
2. Gives each agent class its **own low-level planner**: Reeds–Shepp/hybrid-A* for car-like
   agents with a **load-dependent curvature bound and stability margin**, and a variable-
   footprint holonomic planner for legged agents.
3. Resolves inter-agent conflicts with a **body-conflict tree** (CBS-style, with a PBS variant
   for scale), generalized to heterogeneous, load-varying agent shapes.

See [`docs/research_proposal.md`](docs/research_proposal.md) for the full problem statement and
[`docs/related_work.md`](docs/related_work.md) for the annotated bibliography this design is
built on.

## Repository layout

```
docs/                     Research proposal, related work, benchmark plan
src/lane_graph/           Clothoid/spline lane-graph representation + Frenet conversion
src/planners/             Per-agent-class low-level planners (forklift, quadruped)
src/high_level/           Body-conflict-tree high-level search (CBS / PBS)
src/benchmark/            Instance generator + baseline runners (grid-CBS, CL-CBS, HCBS)
tests/                    Unit tests for lane-graph geometry and conflict detection
```

## Status

Early-stage research code, updated as of the most recent solver work: the
lane-graph representation, Frenet-frame conflict checking, the CBS/PBS high-level
conflict-tree search, both low-level planners (forklift with load-dependent
curvature/speed, quadruped holonomic), and a classical grid-CBS baseline are
implemented, unit-tested (25 tests), and wired into an end-to-end solver
(`src/solver.py`) with a real solver-vs-baseline comparison script
(`src/benchmark/run_solver_benchmark.py`).

Known limitations, found by actually running the solver rather than by inspection
(see `docs/benchmark_plan.md` for the full writeup):
- The low-level planners fix their route via Dijkstra once and only insert waits
  under a constraint -- they never reroute around a contested segment. On sparse
  graphs with 3+ agents this can make the search genuinely incomplete (verified: a
  non-converging instance was traced and shown to plateau at a fixed cost across
  hundreds of branches, not just need a bigger expansion budget).
- The junction conflict checker uses a node-occupancy time-interval approximation
  rather than true swept-volume geometry (conservative, not tight -- see
  `src/lane_graph/conflicts.py::JunctionConflictChecker`'s docstring).
- A literal CL-CBS/HCBS reimplementation (as opposed to the classical grid-CBS
  baseline actually implemented) remains future work.

See [`docs/improvement_plan.md`](docs/improvement_plan.md) for the evaluated next
steps: a CI-viable simulator testbed (flatland-rl -- chosen and verified once the
requirement was clarified to no-physics-simulation, must-run-in-GitHub-Actions; see
`tests/test_flatland_smoke.py`), precisely-defined lifelong-MAPF metrics
(cycle time, latency, optimal score, success rate, throughput), and specific
published algorithms to address the two limitations above -- PIBT/db-LaCAM for the
global planner's wait-only incompleteness, and ORCA (with MPC/MPPI flagged as a
contingent stretch option) for the currently-nonexistent local collision-avoidance
layer.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m src.benchmark.generate_instances --out data/instances --n-agents 10 --n-instances 5
python -m src.benchmark.run_solver_benchmark --out results/solver_benchmark.csv \
  --map-sizes small --agent-counts 2 3 4 --n-instances 3
```

## License

MIT — see [`LICENSE`](LICENSE).
