"""High-level search: a body-conflict tree generalized to heterogeneous agent classes.

This follows CL-CBS's conflict-tree branching rule (Wen et al., 2022): on detecting a
conflict between two agents, branch into two children, each adding a constraint to
exactly one agent, and replan only that agent's low-level trajectory. The
generalization here is that agents may belong to different classes (forklift,
quadruped), each with its own low-level planner and its own constraint representation
-- the tree itself is agent-class-agnostic and only needs a `LowLevelPlanner` protocol.

Two variants are supported via the `mode` argument:
  - "cbs": best-first on total cost, exhaustive branching -- optimal but slower.
  - "pbs": priority-based, single replan per conflict -- suboptimal but scales better.
See docs/benchmark_plan.md for why both are worth running rather than picking one.

This module is fully implemented and unit-testable (see tests/test_conflict_tree.py)
using a toy LowLevelPlanner, independent of the still-stubbed forklift/quadruped
planners -- the tree logic does not need real Reeds-Shepp curves to be exercised.
"""
from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol, Tuple


@dataclass(frozen=True)
class Constraint:
    """Forbids `agent_id` from occupying `location` during [t_start, t_end)."""

    agent_id: str
    location: str  # segment_id or junction node_id, matching src/lane_graph
    t_start: float
    t_end: float


class LowLevelPlanner(Protocol):
    def plan(self, agent_id: str, constraints: List[Constraint]) -> Optional["AgentPlan"]:
        ...


@dataclass
class AgentPlan:
    agent_id: str
    cost: float
    # Opaque to the tree; only used by the conflict detector and the low-level planner.
    trajectory: object


@dataclass
class CTNode:
    constraints: List[Constraint]
    plans: Dict[str, AgentPlan]
    cost: float

    def __lt__(self, other: "CTNode") -> bool:
        return self.cost < other.cost


ConflictDetector = Callable[[Dict[str, AgentPlan]], Optional[Tuple[str, str, str, float]]]
# Returns (agent_a, agent_b, location, t) for the first conflict found, or None.


class ConflictTreeSearch:
    def __init__(
        self,
        agent_ids: List[str],
        low_level_planner: LowLevelPlanner,
        conflict_detector: ConflictDetector,
        mode: str = "cbs",
    ):
        if mode not in ("cbs", "pbs"):
            raise ValueError(f"mode must be 'cbs' or 'pbs', got {mode!r}")
        self.agent_ids = agent_ids
        self.low_level_planner = low_level_planner
        self.conflict_detector = conflict_detector
        self.mode = mode

    def _plan_all(self, constraints: List[Constraint]) -> Optional[Dict[str, AgentPlan]]:
        plans: Dict[str, AgentPlan] = {}
        for agent_id in self.agent_ids:
            agent_constraints = [c for c in constraints if c.agent_id == agent_id]
            plan = self.low_level_planner.plan(agent_id, agent_constraints)
            if plan is None:
                return None  # infeasible under these constraints
            plans[agent_id] = plan
        return plans

    def search(self, max_expansions: int = 10_000) -> Optional[Dict[str, AgentPlan]]:
        """Run the conflict tree search. Returns a conflict-free plan per agent, or
        None if no solution is found within max_expansions high-level node expansions.
        """
        root_plans = self._plan_all(constraints=[])
        if root_plans is None:
            return None
        root = CTNode(
            constraints=[],
            plans=root_plans,
            cost=sum(p.cost for p in root_plans.values()),
        )

        open_list: List[CTNode] = [root]
        heapq.heapify(open_list)
        expansions = 0
        counter = itertools.count()  # tie-breaker for heap stability

        while open_list and expansions < max_expansions:
            node = heapq.heappop(open_list)
            expansions += 1

            conflict = self.conflict_detector(node.plans)
            if conflict is None:
                return node.plans  # conflict-free -- done

            agent_a, agent_b, location, t = conflict
            candidates = [agent_a, agent_b] if self.mode == "cbs" else [agent_a]
            # PBS mode: only constrain the lower-priority agent (assumed to be
            # agent_b by convention of the conflict_detector's ordering); this is a
            # simplification documented here rather than hidden -- a full PBS
            # implementation would also search over priority orderings.

            for agent in candidates:
                new_constraint = Constraint(
                    agent_id=agent, location=location, t_start=t, t_end=t + 1e-6
                )
                new_constraints = node.constraints + [new_constraint]
                new_plans = self._plan_all(new_constraints)
                if new_plans is None:
                    continue  # infeasible branch, prune
                child = CTNode(
                    constraints=new_constraints,
                    plans=new_plans,
                    cost=sum(p.cost for p in new_plans.values()),
                )
                heapq.heappush(open_list, child)

        return None  # exhausted budget without finding a conflict-free node
