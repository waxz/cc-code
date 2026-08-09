"""Generic differential-testing engine for pathfinding and MAPF implementations.

Motivation (see docs/research_proposal_proving.md for the full case): every
correctness claim about a pathfinding algorithm ("this search is optimal",
"this pruning rule cannot skip a shortest path") is a proof about an *idealized*
algorithm. What actually ships is an *implementation*, adapted to a specific cost
model, and adaptation is exactly where the two real bugs in this project's own
history came from (see git history for src/single_agent/grid_planners.py::jps and
src/high_level/conflict_tree.py): both looked correct on hand-picked test cases
and were wrong on a large fraction of randomized ones.

This module doesn't invent a new testing philosophy -- it's the same one compiler
fuzzing (Csmith and descendants, Yang et al. 2011) uses: generate many random
inputs, run multiple implementations that are supposed to agree, and flag
disagreement. What it adds for this project's use case is a `Comparator`
abstraction general enough to express "these two functions must agree exactly"
(dijkstra vs. astar), "these two must agree only under a matching cost model"
(jps vs. dijkstra_allow_corner_cutting), and "this one function's own output must
satisfy an internal invariant" (a MAPF solver's returned trajectories must be
mutually collision-free) -- the same engine covers all three cases in
docs/research_proposal_proving.md's proof-of-concept results.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Discrepancy:
    trial: int
    seed: int
    instance: Any
    detail: str


@dataclass
class DifferentialRunReport:
    n_trials: int
    n_failures: int
    discrepancies: List[Discrepancy] = field(default_factory=list)
    runtime_s: float = 0.0

    @property
    def failure_rate(self) -> float:
        return self.n_failures / self.n_trials if self.n_trials else 0.0

    def summary(self) -> str:
        return (
            f"{self.n_trials} trials, {self.n_failures} failures "
            f"({self.failure_rate:.2%}), {self.runtime_s:.2f}s"
        )


InstanceGenerator = Callable[[random.Random], Any]
# Comparator receives the instance and returns None if all is well, or a short
# string describing the discrepancy if not. Kept as a single free function
# (rather than a fixed "compare N candidates" shape) so it can express both
# cross-implementation agreement and single-implementation self-consistency
# checks with the same engine.
Comparator = Callable[[Any], Optional[str]]


def run_differential(
    instance_generator: InstanceGenerator,
    comparator: Comparator,
    n_trials: int,
    seed: int = 0,
    max_discrepancies: int = 20,
) -> DifferentialRunReport:
    """Generate n_trials random instances, run `comparator` on each, and collect
    every discrepancy found (up to max_discrepancies, so a badly-broken candidate
    doesn't produce an unbounded report). Each trial gets its own child seed
    derived deterministically from `seed` and the trial index, so any failing
    trial is independently reproducible by seed alone -- required for the
    shrinking step in src/proving/shrink.py, which re-runs single trials.
    """
    t0 = time.perf_counter()
    discrepancies: List[Discrepancy] = []
    n_failures = 0

    for trial in range(n_trials):
        trial_seed = seed * 1_000_003 + trial  # deterministic, distinct per trial
        rng = random.Random(trial_seed)
        instance = instance_generator(rng)
        detail = comparator(instance)
        if detail is not None:
            n_failures += 1
            if len(discrepancies) < max_discrepancies:
                discrepancies.append(
                    Discrepancy(trial=trial, seed=trial_seed, instance=instance, detail=detail)
                )

    return DifferentialRunReport(
        n_trials=n_trials, n_failures=n_failures, discrepancies=discrepancies,
        runtime_s=time.perf_counter() - t0,
    )
