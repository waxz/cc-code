# Research Proposal: Heterogeneous, Load-Dependent MAPF on Curved Lane Networks

## 1. Problem statement

Classical Multi-Agent Path Finding (MAPF) plans collision-free paths for a set of agents on a
graph, typically a 4- or 8-connected grid, treating each agent as a point mass with uniform,
fixed kinematics. Two extensions relax these assumptions independently:

- **Continuous-space / car-like MAPF** (CL-MAPF, CL-CBS) plans Reeds–Shepp curves for
  non-holonomic vehicles and checks collisions between swept vehicle bodies rather than grid
  cells.
- **Heterogeneous MAPF** (HCBS) mixes holonomic and non-holonomic agents within a single
  conflict-resolution framework.

Neither line of work addresses a fleet in which (a) different agents have fundamentally
different motion models — wheeled/car-like versus legged — and (b) an individual agent's
kinematic constraints change during the mission, most importantly a forklift's turning radius,
max lateral acceleration, and tipping margin, which all depend on whether it is currently
carrying a load. Nor does either line of work use a curved **lane-graph** map representation
of the kind used in autonomous-driving road networks, which is a closer model of a real
warehouse or factory floor than either a grid or an unconstrained continuous workspace.

## 2. Research gap

> A shared conflict-resolution layer for heterogeneous, load-dependent kinodynamic agents
> operating on a continuous, curved lane-graph, with conflict checking that stays tractable by
> exploiting the lane structure instead of performing full swept-volume checks everywhere.

## 3. Proposed approach

### 3.1 Map representation

The environment is a graph of clothoid or cubic-spline lane segments with known width, meeting
at junction nodes. Agent trajectories are parameterized in a Frenet frame (arc-length `s`,
lateral offset `d`) rather than raw `(x, y)`. On a shared straight lane segment, conflict
detection reduces to a 1-D time-interval overlap along `s`; full swept-volume checks are
reserved for junctions, where geometry is genuinely 2-D.

### 3.2 Low-level planners (one per agent class)

- **Car-like (forklift):** Reeds–Shepp / hybrid-A* planner whose curvature bound `κ` and max
  lateral acceleration are functions of a load-state variable fixed at planning time (empty vs.
  laden), derived from a friction-circle / tipping-margin model.
- **Legged (quadruped):** variable-footprint holonomic planner (can turn in place, sidestep),
  with cost shaped by an energy proxy consistent with prior work on peak-vs-average battery
  current as an RL objective (see `docs/related_work.md`, energy-aware locomotion). Full
  footstep-level execution is deliberately deferred to a downstream refinement stage — this
  project's contribution is the coordination layer, not a full-body controller.

### 3.3 High-level search

A body-conflict tree in the style of CL-CBS: on detecting a conflict, branch into two children,
each constraining one agent, and replan that agent's low-level trajectory under the new
constraint. Both CBS (optimal, smaller instances) and PBS (scalable, suboptimal) variants are
implemented so solution quality and scalability trade-offs can be measured directly.

## 4. Baselines and ablations

See [`docs/benchmark_plan.md`](benchmark_plan.md) for the full evaluation design. In brief:

1. Grid-based CBS on a discretized version of the same map (lower bound / sanity check).
2. CL-CBS: forklift-only fleet, fixed curvature, no load dependence.
3. HCBS: heterogeneous agents, fixed kinematics per class.
4. This work, with load-dependence switched off (internal ablation).
5. This work, full.

## 5. Scope and what this project does *not* claim to solve

- Full-body legged locomotion control is out of scope; the quadruped is modeled abstractly at
  the coordination layer.
- Dynamic online replanning (new tasks arriving mid-mission, i.e. lifelong MAPF) is future
  work; this project targets the one-shot MAPF setting.
- Real hardware deployment is out of scope; validation is in simulation (see benchmark plan).
