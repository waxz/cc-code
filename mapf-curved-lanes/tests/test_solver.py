"""Tests for the real (non-toy) pieces added on top of the conflict-tree scaffold:
load-dependent routing feasibility, the fixed Zeno-boundary conflict resolution, and
the end-to-end solver.
"""
from src.benchmark.generate_instances import AgentSpec
from src.lane_graph.graph import JunctionNode, LaneGraph, LaneSegment
from src.planners.forklift_planner import ForkliftPlanner, LoadState
from src.solver import solve_instance


def _shortcut_vs_detour_graph() -> LaneGraph:
    g = LaneGraph()
    for n in ("a", "b", "c"):
        g.add_node(JunctionNode(n, (0.0, 0.0)))
    # curvature 0.5 -> min radius 2.0m: within empty's bound (min_turn_radius_empty
    # default 1.6m -> curvature_bound ~0.625) but outside laden's (min_turn_radius_laden
    # default 2.4m -> curvature_bound ~0.417).
    g.add_segment(LaneSegment("shortcut", "a", "b", length=3.0, width=3.0, curvature=0.5))
    g.add_segment(LaneSegment("d1", "a", "c", length=8.0, width=3.0, curvature=0.0))
    g.add_segment(LaneSegment("d2", "c", "b", length=8.0, width=3.0, curvature=0.0))
    return g


def test_load_dependent_curvature_changes_route():
    g = _shortcut_vs_detour_graph()
    planner = ForkliftPlanner(g)

    empty_traj = planner.plan("fk", "a", "b", LoadState.EMPTY, [])
    laden_traj = planner.plan("fk", "a", "b", LoadState.LADEN, [])

    assert [leg.segment_id for leg in empty_traj.legs] == ["shortcut"]
    assert [leg.segment_id for leg in laden_traj.legs] == ["d1", "d2"]
    assert laden_traj.cost > empty_traj.cost  # laden is forced onto the longer detour


def test_curved_segment_speed_is_capped_so_margin_never_negative():
    g = _shortcut_vs_detour_graph()
    planner = ForkliftPlanner(g)
    traj = planner.plan("fk", "a", "b", LoadState.EMPTY, [])
    # Regression test for the bug where curvature feasibility was checked but speed
    # wasn't capped to match, producing a physically inconsistent negative margin.
    assert traj.min_stability_margin >= -1e-9


def test_infeasible_when_only_route_exceeds_curvature_bound_for_both_states():
    g = LaneGraph()
    for n in ("a", "b"):
        g.add_node(JunctionNode(n, (0.0, 0.0)))
    # curvature 2.0 -> min radius 0.5m, tighter than even the empty forklift's
    # min_turn_radius_empty (1.6m default) can take, and it's the only route.
    g.add_segment(LaneSegment("tight", "a", "b", length=2.0, width=3.0, curvature=2.0))
    planner = ForkliftPlanner(g)
    assert planner.plan("fk", "a", "b", LoadState.EMPTY, []) is None
    assert planner.plan("fk", "a", "b", LoadState.LADEN, []) is None


def _head_on_corridor_graph() -> LaneGraph:
    g = LaneGraph()
    for n in ("a", "b", "c"):
        g.add_node(JunctionNode(n, (0.0, 0.0)))
    g.add_segment(LaneSegment("s1", "a", "b", length=10.0, width=3.0))
    g.add_segment(LaneSegment("s2", "b", "c", length=10.0, width=3.0))
    return g


def test_solver_resolves_head_on_conflict_cbs():
    g = _head_on_corridor_graph()
    agents = [
        AgentSpec("fk_0", "forklift", "a", "c", "empty"),
        AgentSpec("fk_1", "forklift", "c", "a", "empty"),
    ]
    result = solve_instance(g, agents, mode="cbs")
    assert result.success
    assert result.sum_of_costs > 0
    assert result.high_level_expansions >= 1
    # Regression test for the fix: this used to loop forever re-detecting the same
    # zero-width "conflict" at the segment handoff boundary and never converge.
    assert result.high_level_expansions < 50


def test_solver_resolves_head_on_conflict_pbs():
    g = _head_on_corridor_graph()
    agents = [
        AgentSpec("fk_0", "forklift", "a", "c", "empty"),
        AgentSpec("fk_1", "forklift", "c", "a", "empty"),
    ]
    result = solve_instance(g, agents, mode="pbs")
    assert result.success


def test_solver_heterogeneous_fleet_no_conflict_when_independent():
    """Two agents on disjoint parts of the graph shouldn't need to wait at all."""
    g = LaneGraph()
    for n in ("a", "b", "c", "d"):
        g.add_node(JunctionNode(n, (0.0, 0.0)))
    g.add_segment(LaneSegment("s1", "a", "b", length=5.0, width=3.0))
    g.add_segment(LaneSegment("s2", "c", "d", length=5.0, width=3.0))
    agents = [
        AgentSpec("fk_0", "forklift", "a", "b", "empty"),
        AgentSpec("qp_0", "quadruped", "c", "d", "empty"),
    ]
    result = solve_instance(g, agents, mode="cbs")
    assert result.success
    assert result.high_level_expansions == 1  # root node, no branching needed
