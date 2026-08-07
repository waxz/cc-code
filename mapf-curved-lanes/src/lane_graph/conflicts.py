"""Conflict detection between agent trajectories on a LaneGraph.

Two tiers, matching the design in docs/research_proposal.md:

1. Shared straight lane segment: reduce to a 1-D time-interval overlap along arc-length
   `s`, offset by each agent's half-length plus a safety margin. Cheap.
2. Junction: fall back to discretized swept-volume overlap, since geometry there is
   genuinely 2-D and agents may have different footprints (a laden forklift's swept
   rectangle differs from an empty one; a quadruped's footprint differs from both).

This module defines the interfaces and the straight-segment fast path in full; the
junction swept-volume check is stubbed with a clear TODO (see JunctionConflictChecker)
since it depends on the per-agent-class footprint model in src/planners/, which is
itself a stub pending the load-dependent kinematic model described in the proposal.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from src.lane_graph.graph import LaneGraph


@dataclass
class LaneOccupancy:
    """One agent's claimed interval on one lane segment."""

    agent_id: str
    segment_id: str
    s_start: float
    s_end: float
    t_start: float
    t_end: float
    half_length: float  # agent footprint half-length along the lane direction


@dataclass
class Conflict:
    agent_a: str
    agent_b: str
    location: str  # segment_id or junction node_id
    t: float
    kind: str  # "lane" or "junction"


def check_lane_conflicts(
    occ_a: LaneOccupancy, occ_b: LaneOccupancy, safety_margin: float = 0.1
) -> Optional[Conflict]:
    """1-D interval-overlap conflict check on a shared straight lane segment.

    Two agents conflict if their arc-length intervals (padded by footprint half-length
    plus a safety margin) overlap during an overlapping time window.
    """
    if occ_a.segment_id != occ_b.segment_id:
        return None

    t_overlap_start = max(occ_a.t_start, occ_b.t_start)
    t_overlap_end = min(occ_a.t_end, occ_b.t_end)
    if t_overlap_start > t_overlap_end:
        return None

    pad = occ_a.half_length + occ_b.half_length + safety_margin
    a_lo, a_hi = occ_a.s_start - pad, occ_a.s_end + pad
    b_lo, b_hi = occ_b.s_start, occ_b.s_end
    if a_hi < b_lo or b_hi < a_lo:
        return None

    return Conflict(
        agent_a=occ_a.agent_id,
        agent_b=occ_b.agent_id,
        location=occ_a.segment_id,
        t=t_overlap_start,
        kind="lane",
    )


class JunctionConflictChecker:
    """Swept-volume conflict checking at junction nodes.

    TODO: implement discretized-pose swept-volume overlap using each agent's
    load/gait-dependent footprint from src/planners/. This is the expensive part of
    the design flagged in docs/benchmark_plan.md ("conflict-check overhead") and
    should be benchmarked explicitly, not just implemented.
    """

    def __init__(self, graph: LaneGraph, time_resolution: float = 0.1):
        self.graph = graph
        self.time_resolution = time_resolution

    def check(self, trajectory_a, trajectory_b, junction_id: str) -> List[Conflict]:
        raise NotImplementedError(
            "Junction swept-volume conflict checking depends on the per-agent-class "
            "footprint model (src/planners/forklift_planner.py, "
            "src/planners/quadruped_planner.py), which is not yet implemented."
        )
