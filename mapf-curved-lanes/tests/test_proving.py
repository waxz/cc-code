"""Tests for src/proving/. Two jobs: (1) validate the framework itself actually
catches bugs and shrinks them to minimal counterexamples, using the seeded bug
in src/proving/seeded_bug_demo.py where ground truth is known; (2) apply it for
real to this project's production single-agent and multi-agent code, as
regression tests -- smaller trial counts than
docs/research_proposal_proving.md's reported numbers, for CI speed, but the same
real checks, not a mocked-down version of them.
"""
from src.proving.comparators import (
    mapf_solution_self_consistency_comparator,
    single_agent_cost_comparator,
)
from src.proving.differential import run_differential
from src.proving.grid_instances import random_grid_instance, simplify_grid_instance
from src.proving.mapf_instances import random_mapf_instance
from src.proving.seeded_bug_demo import buggy_dijkstra_missing_diagonals
from src.proving.shrink import shrink
from src.single_agent.grid_planners import astar, dijkstra, dijkstra_allow_corner_cutting, jps


def test_framework_catches_the_seeded_bug():
    """Ground-truth check: the seeded bug is known to be wrong (it omits
    diagonal moves), so the framework MUST report a nonzero failure rate here,
    or the framework itself is broken.
    """
    comparator = single_agent_cost_comparator(buggy_dijkstra_missing_diagonals, dijkstra)
    report = run_differential(random_grid_instance, comparator, n_trials=200, seed=0)
    assert report.n_failures > 0
    # Measured at 57.8% on a larger run (see docs/research_proposal_proving.md);
    # a loose lower bound here avoids CI flakiness from trial-count variance
    # while still catching a framework regression that silently stops detecting.
    assert report.failure_rate > 0.2


def test_shrinker_reduces_seeded_bug_to_minimal_diagonal_counterexample():
    """The known-minimal counterexample for the missing-diagonal-moves bug is a
    2x2 grid with start and goal on opposite corners (a single diagonal move
    vs. two orthogonal ones) -- verified by manual inspection of an actual
    shrink run, not assumed. This locks that finding in as a regression test
    for the shrinker itself.
    """
    comparator = single_agent_cost_comparator(buggy_dijkstra_missing_diagonals, dijkstra)
    report = run_differential(random_grid_instance, comparator, n_trials=200, seed=0)
    assert report.discrepancies, "seeded bug should have produced at least one failure to shrink"

    d = report.discrepancies[0]
    result = shrink(d.instance, comparator, simplify_grid_instance, d.detail)

    assert result.minimal_instance.grid.width * result.minimal_instance.grid.height <= 4
    assert result.minimal_detail is not None
    # No obstacles should remain in a minimal missing-diagonal counterexample --
    # the bug has nothing to do with obstacles.
    assert all(all(row) for row in result.minimal_instance.grid.grid)


def test_dijkstra_and_astar_agree_on_many_random_instances():
    comparator = single_agent_cost_comparator(astar, dijkstra)
    report = run_differential(random_grid_instance, comparator, n_trials=1000, seed=1)
    assert report.n_failures == 0, report.discrepancies


def test_jps_and_matching_dijkstra_agree_on_many_random_instances():
    comparator = single_agent_cost_comparator(jps, dijkstra_allow_corner_cutting)
    report = run_differential(random_grid_instance, comparator, n_trials=1000, seed=2)
    assert report.n_failures == 0, report.discrepancies


def test_mapf_solver_self_consistency_on_random_instances():
    """Checks the multi-agent solver's OWN returned solutions against its own
    claimed invariants (conflict-freeness, cost consistency) -- not against a
    second implementation, since none exists at this cost model's fidelity.
    This is a soundness check only: it says nothing about the already-documented
    completeness gap (docs/benchmark_plan.md) where the solver sometimes fails
    to find a solution that exists -- a successful result here means "when this
    solver claims success, that claim is trustworthy", not "this solver always
    succeeds when it should".
    """
    comparator = mapf_solution_self_consistency_comparator(mode="cbs", max_expansions=200)
    report = run_differential(random_mapf_instance, comparator, n_trials=60, seed=3)
    assert report.n_failures == 0, report.discrepancies
