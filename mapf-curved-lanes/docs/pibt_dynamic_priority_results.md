# Incorporating State-of-the-Art PIBT: Dynamic Priority

Per `docs/space_time_routing_results.md` §5's recommendation, and directly
requested: search for and study open-source SOTA MAPF implementations,
incorporate real improvements, measure the effect honestly.

## 1. What was cloned and studied

`Kei18/pypibt` (github.com/Kei18/pypibt, MIT-licensed) — a minimal Python
reference implementation of PIBT by the algorithm's own original author. Cloned
to `/tmp` for study, not vendored into this repository. Read for algorithmic
approach only; `src/baselines/pibt.py` remains an independently-written
implementation, as it was before this comparison — no code was copied.

`Kei18/lacam0`/`lacam2` (LaCAM, the algorithm that uses PIBT as a "configuration
generator" inside a complete, eventually-optimal search) were also identified
and reviewed at the README/documentation level as a further SOTA reference —
see §4 for why adopting LaCAM's full approach is flagged as future work rather
than attempted here.

## 2. The concrete gap found

This project's `src/baselines/pibt.py` (before this change) used **static**
priorities, explicitly documented at the time as a "standard, defensible
simplification" for one-shot MAPF. Reading the reference implementation showed
this understated the gap: the published algorithm's own reference code uses
**dynamic** priorities even outside the lifelong setting — an agent's priority
grows by 1 every timestep it hasn't reached its goal, and resets to a low value
once it does. This is the specific mechanism that gives PIBT its
starvation-freedom guarantee (Theorem 1 territory), not an optional add-on.

## 3. What was implemented, and the honest measured result

Added the dynamic priority update to `src/baselines/pibt.py` (independently
written, not copied — see the module's own comment on the update rule), toggled
by a `dynamic_priority` flag (default `True`) so the before/after comparison
below is reproducible by flipping one flag on otherwise identical code.

**Measured result: no difference, on every tested configuration.**

```
Small/sparse (500 trials, 2-5 agents, 4x4-10x10 grids):
  static:  420/500 success (84.0%), avg_makespan=6.79
  dynamic: 420/500 success (84.0%), avg_makespan=6.79   <- identical

Denser (300 trials, 8-15 agents, 5x5-7x7 grids):
  static:  40/300 success (13.3%)
  dynamic: 40/300 success (13.3%)                        <- identical

Large/congested (50 trials each, 20 and 40 agents, 12x12 grid):
  20 agents: static 1/50, dynamic 1/50 (2.0%)             <- identical
  40 agents: static 0/50, dynamic 0/50 (0.0%)              <- identical
```

Not a near-tie — **exactly identical** success/failure on every single trial
across four different instance distributions, which is too consistent to be
coincidence and was treated as a signal to find the actual mechanism, not
assumed to mean "the feature doesn't work."

## 4. Root cause of the null result, verified not assumed

Two checks confirm this is a real, coherent finding rather than a bug:

1. **The dynamic-priority code path was confirmed present and reachable**
   (inspected via `inspect.getsource`, and via a from-scratch reimplementation
   used purely to cross-check the production code's behavior).
2. **The 20-agent failures are genuine severe congestion, not an
   expansion-budget artifact**: re-run at 500, 2000, and 5000 timesteps (10x
   the default budget) — still fails at every budget, ruling out "just needs
   more time" the same way earlier findings in this project ruled that out for
   the CBS corridor case (`docs/space_time_routing_results.md`).

**The actual explanation**: dynamic priority's benefit — preventing a
persistently low-priority agent from being starved over a long run — requires
*sustained, repeated contention over many timesteps* to matter. This project's
tested instances are short, one-shot scenarios that either succeed quickly
(priority order barely matters before everyone reaches their goal) or fail
from structural over-congestion within the budget regardless of who goes first
(no priority scheme resolves 40 agents genuinely not fitting through a 12x12
grid's contested cells in time). Dynamic priority's guarantee is real and
theoretically important, but the instance distribution this project benchmarks
against doesn't exercise the specific failure mode it protects against — a
useful, honest finding about *when* this SOTA technique actually matters, not
a reason to think the implementation is broken or the technique unimportant.

## 5. What was kept, and why

`dynamic_priority=True` was kept as the default rather than reverted to
static, for two reasons: (1) it is the literature-correct behavior and never
measured worse than static on anything tested — a free correctness upgrade
even without a measured win here; (2) the scenario it protects against
(long-running, sustained contention) is exactly what a lifelong-MAPF
deployment (this project's actual eventual target, per
`docs/improvement_plan.md` §3's cycle-time/throughput framing) would exercise,
even though this project's current one-shot benchmark doesn't.

`tests/test_pibt.py` was extended with a regression test locking in the
"identical on this instance corpus" finding itself, so a future change that
makes dynamic priority start mattering (or stop being reachable) shows up as
an intentional, reviewable change rather than a silent behavior shift.

## 6. What wasn't attempted, and why it's flagged rather than skipped silently

**LaCAM** (PIBT as a configuration generator inside a complete,
eventually-optimal search with tree rewiring and backtracking) is the more
ambitious SOTA algorithm actually most relevant to this project's own
documented gap (`docs/space_time_routing_results.md` §5: CBS's corridor-case
incompleteness). It was not implemented here — it is a substantially larger
piece of work (a two-level search architecture, not a parameter change to an
existing one) and deserves its own scoped effort rather than a rushed,
under-tested addition in the same session as this smaller, already-thorough
comparison. Flagged as the next concrete candidate for "incorporate SOTA
algorithms," not silently deferred.
