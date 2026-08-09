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

import itertools
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from src.lane_graph.graph import LaneGraph
from src.lane_graph.trajectory import Trajectory


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
    t: float        # start of the overlapping time window
    t_end: float     # end of the overlapping time window -- both agents must be
                      # cleared of `location` for the conflict to actually resolve,
                      # so a constraint needs to block this whole window, not just
                      # the instant `t` (see src/high_level/conflict_tree.py)
    kind: str  # "lane" or "junction"


def check_lane_conflicts(
    occ_a: LaneOccupancy,
    occ_b: LaneOccupancy,
    safety_margin: float = 0.1,
    time_margin: float = 0.5,
) -> Optional[Conflict]:
    """1-D interval-overlap conflict check on a shared straight lane segment.

    Two agents conflict if their arc-length intervals (padded by footprint half-length
    plus a spatial safety margin) overlap during an overlapping time window, where the
    time window itself is padded by `time_margin` on each side.

    time_margin matters more than it looks: two agents that traverse the same segment
    back-to-back (one leaves exactly as the other enters) have *touching* but
    non-overlapping time intervals. Without a time buffer, the reported conflict
    window would be zero-width, and a zero-width constraint blocks nothing -- the
    high-level search would keep re-detecting the same "conflict" without the
    low-level planner's wait-insertion ever actually doing anything, and never
    converge. time_margin is what turns "they touch" into a real, resolvable
    constraint window.
    """
    if occ_a.segment_id != occ_b.segment_id:
        return None

    t_overlap_start = max(occ_a.t_start - time_margin, occ_b.t_start - time_margin)
    t_overlap_end = min(occ_a.t_end + time_margin, occ_b.t_end + time_margin)
    if t_overlap_start >= t_overlap_end:
        # >= not >: an exact-zero-width touch means the two padded occupancies
        # meet at precisely one instant with no actual overlap duration -- the
        # boundary of the safety margin being exactly satisfied, not violated.
        # Treating an exact touch as "still a conflict" (the old `>` here)
        # forced the high-level search to keep branching on it forever once
        # space-time search (src/lane_graph/space_time_routing.py) started
        # finding minimal-cost solutions that land exactly on that boundary --
        # found by tracing an actual non-converging run and watching the same
        # zero-width window (t_start == t_end) recur, not assumed from theory.
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
        t_end=t_overlap_end,
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
            "Full discretized-pose swept-volume checking (agents' actual curved "
            "footprints sweeping through the junction) is not implemented. "
            "check_node_conflict() below is the working simplification currently "
            "used by src/solver.py: a time-interval overlap on the junction *node* "
            "itself, treating the junction as a single shared resource rather than "
            "computing where within it two differently-shaped bodies would actually "
            "intersect. This is strictly more conservative (it can report a conflict "
            "where the real swept volumes wouldn't actually touch, e.g. two agents "
            "crossing a wide junction on opposite sides) but never misses a real one, "
            "so it is safe to use for planning even though it is not tight."
        )


def check_node_conflict(
    visit_a, visit_b, time_margin: float = 0.5
) -> Optional[Conflict]:
    """Node-occupancy junction conflict check: two agents conflict at a junction if
    their [t_enter, t_exit] intervals there overlap once padded by time_margin on
    each side (same reasoning as check_lane_conflicts' time_margin -- a zero-width
    overlap window produces a constraint that blocks nothing). See
    JunctionConflictChecker.check's docstring for why this node-level check is a
    conservative stand-in for full swept-volume checking rather than a claim of
    geometric precision.
    """
    if visit_a.node_id != visit_b.node_id:
        return None
    lo = max(visit_a.t_enter - time_margin, visit_b.t_enter - time_margin)
    hi = min(visit_a.t_exit + time_margin, visit_b.t_exit + time_margin)
    if lo >= hi:
        # >= not >: see check_lane_conflicts' comment on the same boundary --
        # an exact touch is the safety margin being exactly satisfied, not
        # violated.
        return None
    return Conflict(
        agent_a="", agent_b="", location=visit_a.node_id, t=lo, t_end=hi, kind="junction"
    )


def detect_first_conflict(
    trajectories: Dict[str, Trajectory], safety_margin: float = 0.1
) -> Optional[Tuple[str, str, str, float, float]]:
    """Scan all agent pairs for the first conflict, lane or junction. Returns
    (agent_a, agent_b, location, t_start, t_end) -- the full overlapping time
    window, not just its start -- in the shape the high-level ConflictTreeSearch
    expects (src/high_level/conflict_tree.py), or None if the joint plan is
    conflict-free.

    Agent pair order and leg/visit order are both deterministic (sorted agent_ids,
    original leg order) so search behavior is reproducible across runs -- important
    for benchmark comparability.
    """
    agent_ids = sorted(trajectories.keys())
    for a_id, b_id in itertools.combinations(agent_ids, 2):
        traj_a, traj_b = trajectories[a_id], trajectories[b_id]

        for leg_a in traj_a.legs:
            for leg_b in traj_b.legs:
                occ_a = LaneOccupancy(
                    agent_id=a_id, segment_id=leg_a.segment_id,
                    s_start=min(leg_a.s_start, leg_a.s_end),
                    s_end=max(leg_a.s_start, leg_a.s_end),
                    t_start=leg_a.t_start, t_end=leg_a.t_end,
                    half_length=traj_a.half_length,
                )
                occ_b = LaneOccupancy(
                    agent_id=b_id, segment_id=leg_b.segment_id,
                    s_start=min(leg_b.s_start, leg_b.s_end),
                    s_end=max(leg_b.s_start, leg_b.s_end),
                    t_start=leg_b.t_start, t_end=leg_b.t_end,
                    half_length=traj_b.half_length,
                )
                conflict = check_lane_conflicts(occ_a, occ_b, safety_margin)
                if conflict is not None:
                    return (a_id, b_id, conflict.location, conflict.t, conflict.t_end)

        for visit_a in traj_a.node_visits:
            for visit_b in traj_b.node_visits:
                conflict = check_node_conflict(visit_a, visit_b, safety_margin)
                if conflict is not None:
                    return (a_id, b_id, conflict.location, conflict.t, conflict.t_end)

    return None
