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

Early-stage research code: the lane-graph representation, conflict-tree scaffold, and
benchmark instance generator are implemented and runnable. The load-dependent Reeds–Shepp
planner and the full baseline comparisons (grid-CBS, CL-CBS, HCBS) described in
`docs/benchmark_plan.md` are stubbed out with clear TODOs — see each module's docstring.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m src.benchmark.generate_instances --out data/instances --n-agents 10 --n-instances 5
python -m src.benchmark.run_baseline --instances data/instances --solver grid_cbs
```

## License

MIT — see [`LICENSE`](LICENSE).
