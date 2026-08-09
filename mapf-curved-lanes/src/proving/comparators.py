"""Comparator functions for src/proving/differential.py, covering both
single-agent cross-implementation agreement and MAPF solver self-consistency
(a returned solution must actually satisfy the properties the solver claims).
"""
from __future__ import annotations

from typing import Optional

from src.proving.grid_instances import GridInstance

COST_TOLERANCE = 1e-6


def single_agent_cost_comparator(candidate_fn, reference_fn):
    """Build a Comparator that requires candidate_fn and reference_fn to agree
    exactly on solved cost (and on success/failure) for a GridInstance. Both
    functions must return an object with `.path` and `.cost`, OR a bare float
    cost / None (this project's grid_planners.py and seeded_bug_demo.py use
    both shapes, so both are handled here rather than forcing a wrapper on
    each call site).
    """

    def _cost_of(result):
        if result is None:
            return None
        if hasattr(result, "path"):
            return result.cost if result.path is not None else None
        return result  # bare float or None

    def comparator(instance: GridInstance) -> Optional[str]:
        ref = _cost_of(reference_fn(instance.grid, instance.start, instance.goal))
        got = _cost_of(candidate_fn(instance.grid, instance.start, instance.goal))

        if ref is None and got is None:
            return None
        if ref is None or got is None:
            return f"success mismatch: reference={ref!r} candidate={got!r}"
        if abs(ref - got) > COST_TOLERANCE:
            return f"cost mismatch: reference={ref:.6f} candidate={got:.6f}"
        return None

    return comparator


def mapf_solution_self_consistency_comparator(mode: str = "cbs", max_expansions: int = 200):
    """Build a Comparator for MAPF instances (src/benchmark/generate_instances.py
    output) that checks a solver's OWN returned solution against the properties
    it implicitly claims to have: every pair of trajectories must be genuinely
    conflict-free (re-checked independently via
    src/lane_graph/conflicts.py::detect_first_conflict, not just trusted because
    the solver said "success"), and the reported sum_of_costs must equal the sum
    of the returned trajectories' own recomputed costs. This is a
    self-consistency check (one implementation against its own claimed
    invariants), the third comparator shape this engine supports alongside
    "two implementations must agree" -- see module docstring in
    src/proving/differential.py.
    """
    from src.lane_graph.conflicts import detect_first_conflict
    from src.solver import solve_instance

    def comparator(instance) -> Optional[str]:
        graph, mapf_instance = instance
        result = solve_instance(graph, mapf_instance.agents, mode=mode, max_expansions=max_expansions)
        if not result.success:
            return None  # nothing to check if the solver reports failure

        conflict = detect_first_conflict(result.trajectories)
        if conflict is not None:
            a, b, loc, t0, t1 = conflict
            return (
                f"solver reported success but returned trajectories conflict: "
                f"{a} vs {b} at {loc} during [{t0:.3f}, {t1:.3f}]"
            )

        recomputed = sum(t.cost for t in result.trajectories.values())
        if abs(recomputed - result.sum_of_costs) > 1e-3:
            return (
                f"reported sum_of_costs ({result.sum_of_costs:.3f}) != recomputed "
                f"from trajectories ({recomputed:.3f})"
            )
        return None

    return comparator
