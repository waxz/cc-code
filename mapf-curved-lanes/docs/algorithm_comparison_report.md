# Performance Metric Report: This Project's Solvers vs. PIBT

Status: PIBT reproduced and run for real (`src/baselines/pibt.py`), completing
step 1 of `docs/improvement_plan.md` section 7's comparison plan. All numbers
below are measured from actual runs (`src/benchmark/run_solver_benchmark.py`),
not projected from the literature.

## 1. What's being compared, and on what

Three solvers, run on **literally identical instances** (the grid-based two
share the exact same `instance_to_grid` translation, so they see the same grid,
obstacles, and start/goal cells — not just instances drawn from the same
distribution):

- **`ours_full`** — this project's lane-graph CBS solver (`src/solver.py`),
  continuous curved lane-graph, load-dependent kinematics, A* low-level routing.
- **`grid_cbs`** — classical grid-based CBS (`src/baselines/grid_cbs.py`),
  independently implemented, 4-connected, no curvature/load-dependence.
- **`pibt`** — Priority Inheritance with Backtracking (`src/baselines/pibt.py`),
  reproduced from Okumura et al. (IJCAI 2019 / AI 2022), same 4-connected grid
  as `grid_cbs`, same translated instances.

**Important unit caveat, stated precisely rather than glossed over**:
`ours_full`'s cost is continuous time (distance ÷ speed) on the lane-graph;
`grid_cbs`'s and `pibt`'s cost is discrete step count on the translated grid.
These are not the same units. Success rate and runtime/throughput are
meaningfully cross-comparable across all three; **cost is only directly
comparable between `grid_cbs` and `pibt`**, which share both a graph and a cost
model.

## 2. Method

`src/benchmark/run_solver_benchmark.py`, extended to add `pibt` alongside the
two solvers already compared in earlier work. For each generated instance: run
`ours_full` (CBS mode, max 300 high-level expansions), translate to a grid and
run `grid_cbs` (max 500 expansions) and `pibt` (max 200 timesteps) on the
identical translated grid. Metrics: success rate, sum-of-costs (when solved),
runtime, and **agents/second** (`n_agents / runtime_s`) — the specific
throughput metric the PIBT/League-of-Robot-Runners literature reports (see
`docs/improvement_plan.md` section 7: "hundreds of agents in under 200ms" /
"10,000 agents in one second").

## 3. Results (measured, 32 instances per solver: small+medium maps, 2/4/6/10
## agents, 4 instances per configuration, seed=100)

```
grid_cbs    n=  32  success_rate=40.62%  avg_runtime=1.1685s  avg_cost_when_solved=39.00  avg_agents_per_second=5767.2
ours_full   n=  32  success_rate=25.00%  avg_runtime=0.1834s  avg_cost_when_solved=83.04  avg_agents_per_second=14670.0
pibt        n=  32  success_rate=43.75%  avg_runtime=0.0017s  avg_cost_when_solved=44.14  avg_agents_per_second=21270.8
```

**Headline, measured result**: PIBT edges out `grid_cbs` on success rate
(43.75% vs. 40.62%) while running **~687x faster on average**
(1.1685s → 0.0017s). This is the core PIBT claim from the literature —
dramatically faster, competitive-or-better success rate on hard instances,
at the cost of solution optimality — reproduced and measured on this
project's own instances, not merely cited.

**Cost quality, comparable pair only**: on instances both solved, PIBT's
average cost (44.14) is higher than `grid_cbs`'s (39.00) — expected and
consistent with the literature: PIBT is a greedy, suboptimal one-step
algorithm with no completeness or optimality guarantee in general, versus
`grid_cbs`'s exhaustive branch-and-bound search. This is the literature's
stated trade-off (speed for optimality), measured directly rather than
assumed to hold here too.

**`ours_full` performs worst on success rate here (25.00%)**, consistent
with — not contradicting — the already-documented finding in
`docs/benchmark_plan.md`: its low-level planner can wait but not reroute
around a contested segment, a genuine completeness gap distinct from PIBT's
different (greedy, no-backtracking-across-timesteps) limitation. `ours_full`'s
own throughput (14,670 agents/sec) looks respectable in isolation but is not
directly comparable to the grid-based two given the cost-unit and
map-representation differences noted in §1.

## 4. A closer look at scaling behavior (medium maps, 5/10/15 agents, 3
## instances per configuration, separate run)

```
grid_cbs    n=   9  success_rate=22.22%  avg_runtime=3.4191s  avg_cost_when_solved=54.00  avg_agents_per_second=2010.4
ours_full   n=   9  success_rate=0.00%   avg_runtime=0.3765s  avg_cost_when_solved=nan    avg_agents_per_second=nan
pibt        n=   9  success_rate=22.22%  avg_runtime=0.0024s  avg_cost_when_solved=82.50  avg_agents_per_second=21248.0
```

At this harder, higher-agent-count regime: `grid_cbs`'s average runtime climbs
to 3.4s (one instance took 12.1s) while PIBT stays at low-millisecond
runtimes regardless — the qualitative behavior the literature describes as
PIBT's whole reason for existing (constant-ish per-timestep cost vs. CBS's
combinatorial branch-tree blowup). Success rate is tied here (22.22% each);
neither solver "wins" outright at this specific regime, which is itself an
honest, useful data point — PIBT's throughput advantage does not
automatically imply a success-rate advantage at every scale, only a
consistent speed advantage.

`ours_full` reports **0% success** at this scale — the sharpest illustration
yet of its documented wait-only completeness limitation. This is not a new
finding; it is the same root cause from `docs/benchmark_plan.md` showing up
more severely as agent count grows, exactly as that limitation predicts.

## 5. Honest limitations of this comparison

- **Sample size**: 32 and 9 instances respectively are enough to see clear
  qualitative patterns (the ~687x runtime gap is not subtle) but not enough
  for tight statistical confidence intervals on success-rate differences that
  are closer (43.75% vs. 40.62%, or the tied 22.22%). A rigorous version of
  this comparison would run hundreds of instances per configuration, which
  was not done here given CI/session time budgets — flagged as the natural
  extension, not silently assumed unnecessary.
- **PIBT's own documented simplifications** (`src/baselines/pibt.py`): static
  priorities rather than the literature's starvation-aware dynamic priority
  scheme, and a simplified cycle-detection instead of the paper's fuller
  backtracking. Both are disclosed in the module docstring. The dynamic
  priority scheme in particular could plausibly improve PIBT's success rate
  further, since some observed failures are timestep-budget exhaustion on
  instances a more starvation-resistant priority scheme might resolve faster
  — untested here, flagged as a next step.
- **This is not yet PIBT vs. this project's actual lane-graph solver on the
  actual research problem** (heterogeneous, curved-lane, load-dependent
  instances) — it's PIBT vs. `grid_cbs` on a grid, and `ours_full` reported
  alongside on its own native representation for context. Translating this
  project's real curved-lane instances into a form PIBT can consume (as
  `docs/improvement_plan.md` section 7 step 3 describes) remains undone; that
  translation would very likely lose exactly the curvature/load-dependence
  information this project's own research contribution is about, the same
  concern already flagged for the `flatland-rl` and `grid_cbs` translations
  elsewhere in this project's docs.

## 6. What this settles, and what it doesn't

**Settled, with real measurement**: PIBT's core speed claim holds on this
project's own instances — roughly three orders of magnitude faster than this
project's own classical CBS baseline, with success rate that is competitive
(and, in the first sweep, slightly better) rather than worse. This is
sufficient evidence to justify implementing PIBT as an actual solver mode in
`src/solver.py` (operating on the lane-graph directly, not only the grid
translation), per `docs/improvement_plan.md` section 6 phase 2 — the next
concrete step.

**Not settled**: whether PIBT (or a lane-graph adaptation of it) can also
express this project's specific research contribution — load-dependent
curvature feasibility — without losing it in translation the way the grid
representation necessarily does. That is the real open question this
comparison sets up rather than answers.
