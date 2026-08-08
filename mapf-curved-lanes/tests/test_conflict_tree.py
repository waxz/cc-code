"""Exercise the conflict-tree search with a toy low-level planner, independent of the
still-stubbed forklift/quadruped planners -- see module docstring in
src/high_level/conflict_tree.py.
"""
from typing import Dict, List, Optional

from src.high_level.conflict_tree import (
    AgentPlan,
    ConflictTreeSearch,
    Constraint,
)


class TwoAgentHeadOnPlanner:
    """Two agents on the same single-segment lane, moving head-on. Without a
    constraint they'd both claim the whole segment at the same time; a constraint on
    one agent forces it to wait (cost += 1), resolving the conflict.
    """

    LOCATION = "seg_1"

    def plan(self, agent_id: str, constraints: List[Constraint]) -> Optional[AgentPlan]:
        blocked = any(c.location == self.LOCATION for c in constraints)
        cost = 2.0 if blocked else 1.0  # waiting costs one extra tick
        return AgentPlan(agent_id=agent_id, cost=cost, trajectory={"waited": blocked})


def conflict_detector(plans: Dict[str, AgentPlan]):
    a, b = "agent_a", "agent_b"
    if not plans[a].trajectory["waited"] and not plans[b].trajectory["waited"]:
        return (a, b, TwoAgentHeadOnPlanner.LOCATION, 0.0, 1.0)
    return None


def test_cbs_resolves_head_on_conflict():
    search = ConflictTreeSearch(
        agent_ids=["agent_a", "agent_b"],
        low_level_planner=TwoAgentHeadOnPlanner(),
        conflict_detector=conflict_detector,
        mode="cbs",
    )
    result = search.search()
    assert result is not None
    waited_flags = [plan.trajectory["waited"] for plan in result.values()]
    assert sum(waited_flags) == 1  # exactly one agent should have been made to wait
    assert conflict_detector(result) is None  # resolved


def test_pbs_resolves_head_on_conflict():
    search = ConflictTreeSearch(
        agent_ids=["agent_a", "agent_b"],
        low_level_planner=TwoAgentHeadOnPlanner(),
        conflict_detector=conflict_detector,
        mode="pbs",
    )
    result = search.search()
    assert result is not None
    assert conflict_detector(result) is None


def test_invalid_mode_raises():
    import pytest

    with pytest.raises(ValueError):
        ConflictTreeSearch(
            agent_ids=["a"],
            low_level_planner=TwoAgentHeadOnPlanner(),
            conflict_detector=conflict_detector,
            mode="bogus",
        )
