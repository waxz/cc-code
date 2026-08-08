"""Low-level planner for legged agents (quadrupeds) at the MAPF coordination layer.

Per docs/research_proposal.md section 3.2 and 5, this project deliberately models the
quadruped abstractly at the coordination layer: a variable-footprint holonomic agent
that can turn in place or sidestep (unlike the forklift), with cost shaped by an
energy proxy. Full footstep-level execution is out of scope here and is deferred to a
downstream kinodynamic-refinement stage (see docs/related_work.md, WinkTPG), following
the plan-then-refine separation used elsewhere in MAPF-to-execution pipelines.

SCOPE NOTE: same route-selection simplification as src/planners/forklift_planner.py
(see that module's docstring) -- Dijkstra over the lane-graph rather than a true
holonomic lattice planner in continuous space. The one real difference from the
forklift planner is that curvature never excludes a segment here (a quadruped isn't
constrained by a minimum turning radius), so its route choice is driven purely by
distance/time, not kinematic feasibility.

The "energy cost" used for routing is currently a fixed per-distance proxy, not the
peak-vs-average battery-current model from the related energy-aware locomotion work
-- wiring that model in (so routes are chosen to minimize actual predicted battery
draw, not just time) is flagged as the natural next step rather than silently
approximated as done.

If/when this project is extended toward footstep-level validation, that work should
build on the leg-level IK formulation from the related Yin et al. (2024) extension
referenced in docs/related_work.md rather than duplicating it here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from src.lane_graph.graph import LaneGraph
from src.lane_graph.routing import segment_direction, shortest_path
from src.lane_graph.trajectory import LaneLeg, NodeVisit, Trajectory
from src.planners.forklift_planner import (
    CONSTRAINT_CLEARANCE_BUFFER,
    MAX_WAIT_INSERTIONS,
    RouteConstraint,
)


@dataclass
class QuadrupedKinematicProfile:
    """Illustrative placeholders -- calibrate against the target platform before use."""

    max_speed: float = 1.2          # m/s, omnidirectional
    max_turn_rate: float = 2.0       # rad/s, can turn in place (unlike the forklift)
    footprint_half_length: float = 0.45  # m
    energy_cost_per_meter: float = 1.0   # proxy units; see module docstring


class QuadrupedPlanner:
    """Route-selection low-level planner for a holonomic, curvature-unconstrained
    agent. See the module docstring for what's implemented vs. simplified.
    """

    def __init__(self, graph: LaneGraph, profile: Optional[QuadrupedKinematicProfile] = None):
        self.graph = graph
        self.profile = profile or QuadrupedKinematicProfile()

    def plan(
        self,
        agent_id: str,
        start_node: str,
        goal_node: str,
        constraints: Optional[Iterable[RouteConstraint]] = None,
        start_time: float = 0.0,
    ) -> Optional[Trajectory]:
        constraints = list(constraints or [])
        speed = self.profile.max_speed

        def feasible(seg_id: str) -> bool:
            return True  # no curvature constraint for a holonomic legged agent

        def cost(seg_id: str) -> float:
            return self.graph.segments[seg_id].length / speed

        path = shortest_path(self.graph, start_node, goal_node, cost, feasible)
        if path is None:
            return None

        return self._simulate_timing(agent_id, start_node, path, speed, constraints, start_time)

    def _simulate_timing(
        self,
        agent_id: str,
        start_node: str,
        path: List[str],
        speed: float,
        constraints: List[RouteConstraint],
        start_time: float,
    ) -> Optional[Trajectory]:
        traj = Trajectory(
            agent_id=agent_id, agent_class="quadruped",
            half_length=self.profile.footprint_half_length,
        )
        t = start_time
        node = start_node

        def blocked_until(location: str, t_start: float, t_end: float) -> Optional[float]:
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
            travel_time = seg.length / speed

            for _ in range(MAX_WAIT_INSERTIONS):
                release = blocked_until(node, t, t + 1e-6) or blocked_until(
                    seg_id, t, t + travel_time
                )
                if release is None:
                    break
                t = release + CONSTRAINT_CLEARANCE_BUFFER
            else:
                return None

            enter_t = t
            exit_t = t + travel_time
            traj.node_visits.append(NodeVisit(node_id=node, t_enter=enter_t, t_exit=exit_t))

            s_start, s_end = (0.0, seg.length) if forward else (seg.length, 0.0)
            traj.legs.append(
                LaneLeg(segment_id=seg_id, s_start=s_start, s_end=s_end, t_start=t, t_end=exit_t)
            )

            t = exit_t
            node = seg.end_node if forward else seg.start_node

        traj.node_visits.append(NodeVisit(node_id=node, t_enter=t, t_exit=t))
        return traj
