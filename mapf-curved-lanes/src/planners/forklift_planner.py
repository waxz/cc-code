"""Low-level planner for car-like agents (forklifts) with load-dependent kinematics.

Core idea from docs/research_proposal.md section 3.2: a forklift's curvature bound and
max lateral acceleration are not constants but functions of its load state, derived
from a friction-circle / tipping-margin model. This is what differentiates this
planner from CL-CBS's fixed-curvature Reeds-Shepp planner.

SCOPE NOTE (read before trusting quantitative results from this module): the
research proposal describes continuous-space Reeds-Shepp curve generation (as in
CL-CBS, via a library like OMPL). What's implemented here instead is discrete route
selection over the pre-built LaneGraph: Dijkstra shortest-path routing that treats a
lane segment as traversable only if its curvature is within this agent's current
load-dependent curvature bound (src/lane_graph/routing.py), with per-segment timing
derived from the load-dependent max speed. This is a real, working simplification --
it does make the load-dependent constraint actually change which routes are
available and infeasible -- but it is not the same thing as generating a smooth
Reeds-Shepp path through open space. Swapping in real curve generation (OMPL's
ReedsSheppStateSpace, or the `reeds_shepp` PyPI package) inside a segment, rather
than only choosing which segments to use, is the natural next step and would let
this module also plan feasible maneuvers *within* a segment or at junctions rather
than only between them.

Constraint handling: given a high-level constraint forbidding this agent from a
(location, time-window), the planner used to keep its A*-computed route fixed
and insert a wait before the constrained location -- documented at the time as
"mirrors bounded local waiting rather than a full space-time search", and later
measured to cost real solved instances (0% success on the hardest tested sweep,
see docs/weaknesses_analysis.md section 1.1). This has been replaced with a real
space-time search (src/lane_graph/space_time_routing.py): the low-level planner
now searches (node, discretized-timestep) states directly, so a constraint can
be resolved by rerouting through a different node, not only by waiting where it
is. See docs/space_time_routing_results.md for the measured before/after.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, List, Optional, Tuple

from src.lane_graph.graph import LaneGraph
from src.lane_graph.space_time_routing import space_time_search
from src.lane_graph.trajectory import Trajectory

MAX_WAIT_INSERTIONS = 50

# When a constraint forces a wait, release a bit *after* the constraint's end rather
# than exactly at it. The constraint window is itself padded by the conflict
# detector's time_margin on *both* agents' occupancies (src/lane_graph/conflicts.py:
# check_lane_conflicts/check_node_conflict), so releasing at exactly c.t_end still
# leaves the released agent's own re-padded window touching the other agent's
# re-padded window -- the true gap needs to exceed 2*time_margin (both agents' pads
# stacked), not just time_margin, or the high-level search re-detects "a conflict"
# forever without ever converging. Verified against the actual detector's
# time_margin default of 0.5 by running the solver on a genuine head-on two-agent
# instance and tracing exactly where it got stuck rather than guessing a value.
CONSTRAINT_CLEARANCE_BUFFER = 1.0


class LoadState(Enum):
    EMPTY = "empty"
    LADEN = "laden"


@dataclass
class ForkliftKinematicProfile:
    """Load-dependent kinematic bounds for one forklift.

    Values below are illustrative placeholders, not calibrated to a real vehicle --
    replace with measured or datasheet values before drawing quantitative conclusions.
    Derived from a simple friction-circle / static-tipping model: a laden load raises
    the effective center of gravity and increases the tipping moment under lateral
    acceleration, which both increases the minimum turning radius and lowers the safe
    max speed through curves.
    """

    max_speed_empty: float = 3.0        # m/s
    max_speed_laden: float = 1.8         # m/s
    min_turn_radius_empty: float = 1.6   # m
    min_turn_radius_laden: float = 2.4   # m
    max_lateral_accel_empty: float = 3.5  # m/s^2
    max_lateral_accel_laden: float = 1.8  # m/s^2
    footprint_half_length: float = 1.2    # m; laden footprint is longer in practice
                                            # (forks extend) -- using one constant here
                                            # rather than a second load-dependent field
                                            # is a known simplification, see README status.

    def curvature_bound(self, load_state: LoadState) -> float:
        r = self.min_turn_radius_laden if load_state == LoadState.LADEN else self.min_turn_radius_empty
        return 1.0 / r

    def max_speed(self, load_state: LoadState) -> float:
        return self.max_speed_laden if load_state == LoadState.LADEN else self.max_speed_empty

    def max_lateral_accel(self, load_state: LoadState) -> float:
        return (
            self.max_lateral_accel_laden
            if load_state == LoadState.LADEN
            else self.max_lateral_accel_empty
        )

    def stability_margin(self, load_state: LoadState, realized_lateral_accel: float) -> float:
        """Fraction of the lateral-acceleration budget still in hand (1.0 = fully safe,
        0.0 = at the limit, negative = constraint violated). This is the metric
        docs/benchmark_plan.md calls "stability-margin utilization".
        """
        budget = self.max_lateral_accel(load_state)
        if budget <= 0:
            raise ValueError("max_lateral_accel must be positive")
        return 1.0 - (abs(realized_lateral_accel) / budget)


@dataclass
class Pose2D:
    x: float
    y: float
    theta: float


@dataclass(frozen=True)
class RouteConstraint:
    """(location, [t_start, t_end)) this agent may not occupy. location is a
    segment_id or a junction node_id, matching src/high_level/conflict_tree.Constraint.
    """

    location: str
    t_start: float
    t_end: float


class ForkliftPlanner:
    """Route-selection low-level planner with load-dependent curvature feasibility.
    See the module docstring for exactly what this does and doesn't implement.
    """

    CURVATURE_EPS = 1e-6

    def __init__(self, graph: LaneGraph, profile: Optional[ForkliftKinematicProfile] = None):
        self.graph = graph
        self.profile = profile or ForkliftKinematicProfile()

    def plan(
        self,
        agent_id: str,
        start_node: str,
        goal_node: str,
        load_state: LoadState,
        constraints: Optional[Iterable[RouteConstraint]] = None,
        start_time: float = 0.0,
    ) -> Optional[Trajectory]:
        """Route agent_id from start_node to goal_node, respecting the load-dependent
        curvature bound and any RouteConstraints, via space-time search (rerouting
        is available, not only waiting) -- see module docstring.
        """
        constraints = list(constraints or [])
        curvature_bound = self.profile.curvature_bound(load_state)

        def feasible(seg_id: str) -> bool:
            seg = self.graph.segments[seg_id]
            return abs(seg.curvature) <= curvature_bound + self.CURVATURE_EPS

        def speed(seg_id: str) -> float:
            return self._segment_speed(self.graph.segments[seg_id], load_state)

        def blocked(location: str, t_start: float, t_end: float) -> bool:
            for c in constraints:
                # Padded by CONSTRAINT_CLEARANCE_BUFFER beyond the constraint's
                # raw end, not just c.t_end: the constraint window already
                # comes from the high-level conflict detector's own
                # time_margin-padded overlap (src/lane_graph/conflicts.py), so
                # a state that clears the raw window by less than
                # 2*time_margin can still register as newly conflicting once
                # the detector re-pads both agents' occupancies on the next
                # high-level check -- the same Zeno's-paradox-style boundary
                # case CONSTRAINT_CLEARANCE_BUFFER was originally derived to
                # fix for the old wait-only scheme (see that constant's own
                # docstring). Found again here, in the new space-time search,
                # by watching the exact same conflict window recur forever
                # with a growing constraint count that had no effect -- not
                # assumed to still apply, checked.
                if c.location == location and t_start < c.t_end + CONSTRAINT_CLEARANCE_BUFFER and c.t_start < t_end:
                    return True
            return False

        traj = space_time_search(
            self.graph, agent_id, "forklift", self.profile.footprint_half_length,
            start_node, goal_node, feasible, speed, blocked,
            heuristic_fn=self._heuristic(goal_node, load_state), start_time=start_time,
        )
        if traj is None:
            return None
        self._annotate_stability_margin(traj, load_state, speed)
        return traj

    def _annotate_stability_margin(self, traj: Trajectory, load_state: LoadState, speed_fn) -> None:
        """Post-process the returned trajectory's legs to compute
        min_stability_margin -- a forklift-specific metric space_time_search
        itself doesn't know about (it's generic over agent classes, see
        src/planners/quadruped_planner.py for the other caller).
        """
        min_margin = 1.0
        for leg in traj.legs:
            seg = self.graph.segments[leg.segment_id]
            if abs(seg.curvature) > self.CURVATURE_EPS:
                seg_speed = speed_fn(leg.segment_id)
                lateral_accel = (seg_speed ** 2) * abs(seg.curvature)
                margin = self.profile.stability_margin(load_state, lateral_accel)
                min_margin = min(min_margin, margin)
        traj.min_stability_margin = min_margin

    def _heuristic(self, goal_node: str, load_state: LoadState):
        """Straight-line-distance-over-max-speed heuristic for A* (see
        src/lane_graph/routing.py's module docstring for why this upgrade from
        plain Dijkstra was made). Admissible because (a) every segment's length is
        constructed to be >= the straight-line distance between its own two
        endpoints (grid segments: exactly equal; curved shortcuts: deliberately
        longer, see src/benchmark/generate_instances.py), so by the triangle
        inequality any path's total length is >= straight-line start-to-goal
        distance, and (b) this agent's speed on any segment is capped at
        profile.max_speed(load_state) and never exceeds it (see
        _segment_speed), so dividing by that flat max speed can only
        under-estimate, never over-estimate, true remaining travel time.
        """
        goal_pos = self.graph.nodes[goal_node].position
        max_speed = self.profile.max_speed(load_state)

        def h(node_id: str) -> float:
            node_pos = self.graph.nodes[node_id].position
            dist = ((node_pos[0] - goal_pos[0]) ** 2 + (node_pos[1] - goal_pos[1]) ** 2) ** 0.5
            return dist / max_speed

        return h

    def _segment_speed(self, seg, load_state: LoadState) -> float:
        """Speed this agent may travel `seg` at, in this load state.

        Curvature feasibility (checked separately, in `feasible()` above) only
        guarantees the vehicle's steering geometry *can* take the curve -- it says
        nothing about whether traveling it at full speed stays within the
        lateral-acceleration / tipping-margin budget. Capping speed here by
        sqrt(lateral_accel_budget / curvature) is what keeps `stability_margin`
        (see ForkliftKinematicProfile.stability_margin) from going negative; an
        earlier version of this planner didn't do this and produced physically
        inconsistent negative "safety margins" on curved segments, caught by
        actually running the planner on a curved test segment rather than by
        inspection -- see git history for that finding.
        """
        base_speed = self.profile.max_speed(load_state)
        if abs(seg.curvature) < self.CURVATURE_EPS:
            return base_speed
        accel_budget = self.profile.max_lateral_accel(load_state)
        curve_speed_limit = (accel_budget / abs(seg.curvature)) ** 0.5
        return min(base_speed, curve_speed_limit)
