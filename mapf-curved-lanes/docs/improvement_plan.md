# Improvement Plan: Simulator Testbed, Metrics, and Algorithm Upgrades

This is a planning document, not an implementation — it evaluates where the project
actually stands, picks a practical simulator testbed, defines metrics precisely, and
recommends specific published algorithms to address the two weak points the
benchmarking work already found. Sources are cited inline; see
`docs/related_work.md` for full bibliography entries.

## 1. Honest progress evaluation

What's real and tested (25 unit tests, `src/solver.py` runs end to end):
- Lane-graph representation with curved (non-grid) segments, Frenet-style conflict
  checking, a working CBS/PBS high-level search.
- Load-dependent forklift routing: verified that an empty forklift takes a curve a
  laden one is physically forced to detour around, with speed correctly capped by
  the lateral-acceleration budget (not just curvature feasibility).
- An independent classical grid-CBS baseline, verified against hand-built cases.

What's known-broken, documented rather than hidden (see `docs/benchmark_plan.md`):
- **Core algorithmic weakness**: the low-level planners fix a route via Dijkstra
  once and, under a constraint, only insert waits. On sparse graphs with 3+ agents
  this is genuinely incomplete — traced and confirmed, not assumed.
- **Conflict checking**: junction conflicts use a node-occupancy time-interval
  approximation, not true swept-volume geometry (conservative, not tight).
- No literal CL-CBS/HCBS reimplementation, no physics validation, no local reactive
  collision-avoidance layer at all — every conflict is resolved centrally, ahead of
  time, with zero tolerance for execution/tracking error.

**Conclusion**: the solver proves the core research claim (load-dependent curvature
routing changes behavior) but is not yet competitive at even moderate agent density,
and has never been tested against anything with real dynamics, sensor noise, or
tracking error. Two upgrades matter more than any amount of further tuning of the
current design: (a) a global planner algorithm that doesn't have the wait-only
incompleteness problem, and (b) a proper physics testbed, because the current
node-occupancy conflict model is exactly the kind of simplification that looks fine
on paper and falls apart under real execution.

## 2. Simulator comparison and selection

| Simulator | ROS 2 fit | Multi-robot scale | Physics fidelity | Fit for this project |
|---|---|---|---|---|
| **Gazebo (Harmonic)** | Native (`ros_gz_bridge`), the standard ROS 2 sim | Good; CPU/RTF degrades above ~20 agents on identical hardware (independent Gazebo-vs-Webots study) | Solid rigid-body physics, realistic sensor plugins | **Best fit**: matches the MRP-Bench pipeline already cited in `docs/related_work.md` (RMF traffic editor → Gazebo → ROS 2), has both wheeled and legged robot model support, free |
| **Webots** | Good, more turnkey | Better CPU headroom than Gazebo at swarm scale on modest hardware | Serviceable, less detailed sensor modeling | Good secondary option specifically for the >20-agent stress tests where Gazebo's RTF drops |
| **NVIDIA Isaac Sim** | Good (ROS 2 bridge) | Scales via GPU parallelism, built for perception-heavy work | Photorealistic, PhysX rigid-body | Overkill here — this project is about coordination, not perception/sim-to-real transfer; steep GPU/learning-curve cost buys nothing we need yet |
| **CoppeliaSim** | Decent | Strong for robot-arm and small multi-robot setups | Multiple physics engines, configurable | Not a clear advantage over Gazebo for a wheeled+legged fleet coordination testbed |

**Decision: Gazebo (Harmonic) as the primary testbed**, for three concrete reasons:
it's already the tool the related-work bibliography's MRP-Bench pipeline uses (so
physical-plausibility validation and this testbed can share infrastructure), it has
native ROS 2 integration matching the HCBS/CL-CBS baseline literature's own
toolchains, and it supports both a car-like forklift model (Ackermann or
skid-steer plugin) and a legged quadruped model (existing ROS 2 packages for
Unitree/ANYmal-class robots) without switching simulators mid-project. Webots is
kept as the designated fallback specifically for agent-count scaling tests, where
its lower CPU overhead matters more than Gazebo's richer sensor fidelity.

## 3. Metrics, defined precisely

These extend (don't replace) `docs/benchmark_plan.md`'s existing metrics, adding
the ones a physics-and-time testbed makes measurable that a pure algorithmic
benchmark can't:

| Metric | Definition | Why it matters here |
|---|---|---|
| **Cycle time** | Wall-clock time from task assignment (a pickup/delivery goal) to task completion, per agent, in a lifelong (not one-shot) run | The industry-standard throughput proxy in warehouse MAPF literature (Amazon's lifelong-MAPF papers report exactly this) — one-shot makespan doesn't capture it |
| **Latency** | (a) planning latency: wall-clock time for the high-level solver to produce a plan/replan; (b) control latency: time from a conflict being detected in simulation to a corrective command being issued | Splits "is the algorithm fast enough" from "is the control loop fast enough" — the current `high_level_expansions` metric only covers (a) |
| **Optimal score** | Ratio of achieved sum-of-costs (or cycle time) to a lower bound (shortest-path sum ignoring other agents), i.e. suboptimality factor | Directly comparable to CBS/ECBS/PIBT literature, which reports this same ratio |
| **Success rate** | Fraction of tasks/instances completed without collision, deadlock, or exceeding a time budget | Already used in `docs/benchmark_plan.md`; a physics testbed makes "collision" a real, sensor/geometry-based event instead of only a planning-time conflict |
| **Throughput** *(new)* | Completed tasks per hour, fleet-wide, in a lifelong run | The actual business metric warehouse operators use; ties cycle time and success rate together into one number worth optimizing against |

## 4. Global path-finder algorithm upgrade

**The problem is specific, not generic**: the current wait-only low-level planner
(documented in `src/planners/forklift_planner.py` and traced to a real failure in
`docs/benchmark_plan.md`) can't reroute around a contested segment, only wait for
it, which is provably incomplete on sparse graphs.

**Recommendation: adopt PIBT (Priority Inheritance with Backtracking)** as an
additional, faster solver mode, not a replacement for CBS/PBS. PIBT (Okumura et
al., 2022) does one-timestep, priority-based replanning with backtracking to break
deadlocks — every agent reconsiders its next step every timestep, which is exactly
the "reroute, don't just wait" capability the current planner lacks. It's the
component underlying WPPL, winner of the 2023 Amazon-sponsored League of Robot
Runners competition, and is reported capable of collision-free solutions for
hundreds of agents in under 200ms, with the competition's target being 10,000
agents planned in one second. Practical migration path: keep CBS/PBS as the
"optimal reference" mode for small instances and correctness validation (it's
already tested and understood), and add PIBT as the "fast/scalable" mode for the
lifelong, larger-fleet Gazebo benchmarks — this mirrors how the MAPF field itself
is structured (CBS-family for provable optimality, PIBT/LaCAM-family for scale).

**For the kinodynamic/curved-lane case specifically** — this project's actual
research niche — the most directly relevant recent paper is **db-LaCAM**
("Fast and Scalable Multi-Robot Kinodynamic Motion Planning with
Discontinuity-Bounded Search and Lightweight MAPF"), which combines a lightweight
MAPF layer with discontinuity-bounded search to handle real vehicle kinematics
rather than assuming point-mass agents on a graph. This sits almost exactly at the
intersection this project's research proposal targets (heterogeneous, kinodynamic,
non-grid MAPF) and should be read closely before deciding the specific integration
— it may turn out to make more sense as the direct replacement for the current
Dijkstra-based low-level planner than PIBT does, since it's designed for kinodynamic
constraints from the ground up rather than adapted to them.

## 5. Collision-avoidance algorithm upgrade

**The problem, again specific**: there is currently no local/reactive
collision-avoidance layer at all. Every conflict is resolved centrally, ahead of
time, via the high-level constraint search — there is zero tolerance built in for
the tracking error, sensor noise, or timing drift that a real (or even
Gazebo-simulated) robot will have. This gap is invisible in the current pure-Python
benchmark and will surface immediately once agents are driven by an actual
controller in Gazebo rather than by the planner's own timing assumptions.

**Recommendation: add ORCA (Optimal Reciprocal Collision Avoidance)** as a
decentralized local safety layer beneath the global plan — the standard two-layer
architecture in both industry and the literature: the global coordinator (CBS/PBS
or PIBT) assigns time-windowed reference trajectories, and each agent's local ORCA
layer adjusts its instantaneous velocity to stay collision-free with respect to
other agents' *actual observed* velocities, not just their planned ones. ORCA is
mature, well-understood, and the most widely used reciprocal collision-avoidance
algorithm in both multi-robot systems and crowd simulation; it's a natural fit as
the first local layer to implement precisely because it's a known, boring
technology rather than a research risk in its own right.

**Stretch option for phase 2**: MPC/MPPI-based local layers (e.g. Conflict-Based
MPC, or sampling-based variants like MPPI-ORCA/CoRL-MPPI) report measurably better
collision-free success rates in dense, high-speed scenarios than reactive
one-step methods like plain ORCA or DWA, because they optimize over a receding
horizon instead of reacting to the current instant. These are heavier to implement
and tune (nonlinear optimization or sampling per control step, per agent) and are
recommended only after an ORCA baseline is working end-to-end in Gazebo — if ORCA's
known failure modes (oscillation, local deadlock in tight curved-lane geometry,
which is exactly this project's map style) prove limiting, that's the concrete,
measured justification for moving to MPC rather than adopting it speculatively.

## 6. Phased roadmap

1. **Testbed stand-up**: Gazebo (Harmonic) world matching the existing lane-graph
   maps (`src/benchmark/generate_instances.py`'s output translated to a Gazebo
   world), with a car-like forklift model and a legged quadruped model. Drive both
   from the existing CBS/PBS solver's output trajectories open-loop first, to get a
   baseline cycle time / latency / success rate before changing any algorithm.
2. **Global planner upgrade**: implement PIBT as an additional `solve_instance`
   mode in `src/solver.py`, targeting the documented wait-only incompleteness
   directly. Re-run the same Gazebo comparison; expect success rate and throughput
   to improve on the denser instances that currently fail outright.
3. **Local safety layer**: add ORCA underneath the global plan in Gazebo, and
   measure collision rate / near-miss rate under injected tracking error — this is
   the first point where "success rate" becomes a real, physics-grounded number
   rather than a planning-time-only one.
4. **Stretch**: MPC/MPPI local layer, only if phase 3 shows ORCA's known
   oscillation/deadlock modes actually binding in this project's curved-lane,
   load-dependent setting.

Each phase produces a comparable CSV/report in the same shape as
`src/benchmark/run_solver_benchmark.py` already does, so phase-over-phase
improvement is measurable rather than asserted.
