"""End-to-end solver: wires the LaneGraph, the two low-level planners, the
conflict detector, and the high-level ConflictTreeSearch together into a single
solve_instance() call.

This is what makes the components in src/lane_graph, src/planners, and
src/high_level actually solve a heterogeneous MAPF instance rather than being
independently-tested pieces.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.benchmark.generate_instances import AgentSpec
from src.high_level.conflict_tree import AgentPlan, ConflictTreeSearch, Constraint
from src.lane_graph.conflicts import detect_first_conflict
from src.lane_graph.graph import LaneGraph
from src.lane_graph.trajectory import Trajectory
from src.planners.forklift_planner import ForkliftPlanner, LoadState, RouteConstraint
from src.planners.quadruped_planner import QuadrupedPlanner


class HeterogeneousLowLevelPlanner:
    """Adapts ForkliftPlanner / QuadrupedPlanner to the LowLevelPlanner protocol the
    high-level ConflictTreeSearch expects (src/high_level/conflict_tree.py), and
    converts between the high-level Constraint shape and each planner's
    RouteConstraint shape.
    """

    def __init__(self, graph: LaneGraph, agent_specs: List[AgentSpec]):
        self.graph = graph
        self.specs = {a.agent_id: a for a in agent_specs}
        self.forklift_planner = ForkliftPlanner(graph)
        self.quadruped_planner = QuadrupedPlanner(graph)

    def plan(self, agent_id: str, constraints: List[Constraint]) -> Optional[AgentPlan]:
        spec = self.specs[agent_id]
        route_constraints = [
            RouteConstraint(location=c.location, t_start=c.t_start, t_end=c.t_end)
            for c in constraints
        ]

        if spec.agent_class == "forklift":
            load_state = LoadState.LADEN if spec.load_state == "laden" else LoadState.EMPTY
            traj = self.forklift_planner.plan(
                agent_id, spec.start_node, spec.goal_node, load_state, route_constraints
            )
        elif spec.agent_class == "quadruped":
            traj = self.quadruped_planner.plan(
                agent_id, spec.start_node, spec.goal_node, route_constraints
            )
        else:
            raise ValueError(f"unknown agent_class {spec.agent_class!r} for {agent_id}")

        if traj is None:
            return None
        return AgentPlan(agent_id=agent_id, cost=traj.cost, trajectory=traj)


def _conflict_detector(plans: Dict[str, AgentPlan]):
    trajectories: Dict[str, Trajectory] = {aid: p.trajectory for aid, p in plans.items()}
    return detect_first_conflict(trajectories)


@dataclass
class SolverResult:
    success: bool
    trajectories: Dict[str, Trajectory] = field(default_factory=dict)
    sum_of_costs: float = 0.0
    makespan: float = 0.0
    runtime_s: float = 0.0
    high_level_expansions: int = 0
    min_stability_margin: float = 1.0  # 1.0 if no forklifts, or none ever curved


def solve_instance(
    graph: LaneGraph,
    agent_specs: List[AgentSpec],
    mode: str = "cbs",
    max_expansions: int = 200,
) -> SolverResult:
    """Solve one heterogeneous MAPF instance. See docs/benchmark_plan.md for what
    success/failure and each reported metric mean for this project.
    """
    low_level = HeterogeneousLowLevelPlanner(graph, agent_specs)
    search = ConflictTreeSearch(
        agent_ids=[a.agent_id for a in agent_specs],
        low_level_planner=low_level,
        conflict_detector=_conflict_detector,
        mode=mode,
    )

    t0 = time.perf_counter()
    plans = search.search(max_expansions=max_expansions)
    runtime_s = time.perf_counter() - t0

    if plans is None:
        return SolverResult(
            success=False, runtime_s=runtime_s, high_level_expansions=search.last_expansions
        )

    trajectories = {aid: p.trajectory for aid, p in plans.items()}
    sum_of_costs = sum(t.cost for t in trajectories.values())
    makespan = max((t.cost for t in trajectories.values()), default=0.0)
    forklift_margins = [
        t.min_stability_margin for t in trajectories.values() if t.agent_class == "forklift"
    ]
    min_margin = min(forklift_margins) if forklift_margins else 1.0

    return SolverResult(
        success=True,
        trajectories=trajectories,
        sum_of_costs=sum_of_costs,
        makespan=makespan,
        runtime_s=runtime_s,
        high_level_expansions=search.last_expansions,
        min_stability_margin=min_margin,
    )
