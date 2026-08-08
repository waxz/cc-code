"""Trajectory representation shared by the low-level planners, the conflict
detector, and the high-level solver.

A Trajectory is a time-parameterized route through the lane-graph: an ordered list
of lane legs (arc-length interval + time interval on one segment) plus the node
visits at the junctions between them. This is deliberately the same shape the
Frenet-frame design in docs/research_proposal.md calls for -- straight/curved lane
segments reduce to 1-D interval checks, junctions get their own (simplified, see
conflicts.py) check.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class LaneLeg:
    segment_id: str
    s_start: float
    s_end: float
    t_start: float
    t_end: float


@dataclass
class NodeVisit:
    node_id: str
    t_enter: float
    t_exit: float


@dataclass
class Trajectory:
    agent_id: str
    agent_class: str  # "forklift" or "quadruped"
    half_length: float
    legs: List[LaneLeg] = field(default_factory=list)
    node_visits: List[NodeVisit] = field(default_factory=list)
    min_stability_margin: float = 1.0  # 1.0 = fully safe; see forklift_planner.py

    @property
    def cost(self) -> float:
        """Total elapsed time (this agent's part of the makespan)."""
        if self.node_visits:
            return self.node_visits[-1].t_exit
        if self.legs:
            return self.legs[-1].t_end
        return 0.0
