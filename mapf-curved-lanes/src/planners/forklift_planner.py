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

Constraint handling is similarly simplified: given a high-level constraint forbidding
this agent from a (location, time-window), the planner keeps its Dijkstra-computed
route fixed and inserts a wait before the constrained location until the window has
passed, rather than replanning the route itself. This mirrors bounded local waiting
rather than a full space-time search (e.g. SIPP) -- documented here rather than
silently passed off as one.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, List, Optional, Tuple

from src.lane_graph.graph import LaneGraph
from src.lane_graph.routing import segment_direction, shortest_path
from src.lane_graph.trajectory import LaneLeg, NodeVisit, Trajectory

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
        curvature bound and any RouteConstraints, or return None if infeasible (no
        curvature-feasible route exists, or every route remains blocked after
        MAX_WAIT_INSERTIONS wait insertions).
        """
        constraints = list(constraints or [])
        curvature_bound = self.profile.curvature_bound(load_state)

        def feasible(seg_id: str) -> bool:
            seg = self.graph.segments[seg_id]
            return abs(seg.curvature) <= curvature_bound + self.CURVATURE_EPS

        def cost(seg_id: str) -> float:
            seg = self.graph.segments[seg_id]
            return seg.length / self._segment_speed(seg, load_state)

        path = shortest_path(
            self.graph, start_node, goal_node, cost, feasible,
            heuristic_fn=self._heuristic(goal_node, load_state),
        )
        if path is None:
            return None  # no curvature-feasible route exists for this load state

        return self._simulate_timing(agent_id, start_node, path, load_state, constraints, start_time)

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

    def _simulate_timing(
        self,
        agent_id: str,
        start_node: str,
        path: List[str],
        load_state: LoadState,
        constraints: List[RouteConstraint],
        start_time: float,
    ) -> Optional[Trajectory]:
        traj = Trajectory(
            agent_id=agent_id, agent_class="forklift",
            half_length=self.profile.footprint_half_length,
        )
        t = start_time
        node = start_node
        min_margin = 1.0

        def blocked_until(location: str, t_start: float, t_end: float) -> Optional[float]:
            """If any constraint forbids `location` during [t_start, t_end), return
            the latest such constraint's end time (when we could safely proceed);
            else None.
            """
            latest_release = None
            for c in constraints:
                if c.location != location:
                    continue
                if t_start < c.t_end and c.t_start < t_end:
                    if latest_release is None or c.t_end > latest_release:
                        latest_release = c.t_end
            return latest_release

        for seg_id in path:
            seg = self.graph.segments[seg_id]
            forward = segment_direction(self.graph, seg_id, node)
            seg_speed = self._segment_speed(seg, load_state)
            travel_time = seg.length / seg_speed

            # Node dwell before entering the segment: check node + segment
            # constraints, inserting waits (bounded) until clear.
            for _ in range(MAX_WAIT_INSERTIONS):
                release = blocked_until(node, t, t + 1e-6) or blocked_until(
                    seg_id, t, t + travel_time
                )
                if release is None:
                    break
                t = release + CONSTRAINT_CLEARANCE_BUFFER
            else:
                return None  # gave up waiting out a persistent constraint

            enter_t = t
            exit_t = t + travel_time
            traj.node_visits.append(NodeVisit(node_id=node, t_enter=enter_t, t_exit=exit_t))

            s_start, s_end = (0.0, seg.length) if forward else (seg.length, 0.0)
            traj.legs.append(
                LaneLeg(segment_id=seg_id, s_start=s_start, s_end=s_end, t_start=t, t_end=exit_t)
            )

            if abs(seg.curvature) > self.CURVATURE_EPS:
                lateral_accel = (seg_speed ** 2) * abs(seg.curvature)
                margin = self.profile.stability_margin(load_state, lateral_accel)
                min_margin = min(min_margin, margin)

            t = exit_t
            node = seg.end_node if forward else seg.start_node

        traj.node_visits.append(NodeVisit(node_id=node, t_enter=t, t_exit=t))
        traj.min_stability_margin = min_margin
        return traj
