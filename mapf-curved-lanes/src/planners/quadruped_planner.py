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

Constraint handling now uses real space-time search
(src/lane_graph/space_time_routing.py), matching the forklift planner's upgrade --
see that module's docstring for why the earlier wait-only scheme was replaced.

If/when this project is extended toward footstep-level validation, that work should
build on the leg-level IK formulation from the related Yin et al. (2024) extension
referenced in docs/related_work.md rather than duplicating it here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from src.lane_graph.graph import LaneGraph
from src.lane_graph.space_time_routing import space_time_search
from src.lane_graph.trajectory import Trajectory
from src.planners.forklift_planner import CONSTRAINT_CLEARANCE_BUFFER, RouteConstraint


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

        def speed_fn(seg_id: str) -> float:
            return speed

        goal_pos = self.graph.nodes[goal_node].position

        def heuristic(node_id: str) -> float:
            # Same admissibility argument as ForkliftPlanner._heuristic: segment
            # lengths are constructed >= straight-line endpoint distance, and this
            # agent never exceeds `speed`, so straight_line_dist / speed can only
            # under-estimate true remaining time.
            node_pos = self.graph.nodes[node_id].position
            dist = ((node_pos[0] - goal_pos[0]) ** 2 + (node_pos[1] - goal_pos[1]) ** 2) ** 0.5
            return dist / speed

        def blocked(location: str, t_start: float, t_end: float) -> bool:
            # Same CONSTRAINT_CLEARANCE_BUFFER padding as ForkliftPlanner's
            # blocked() -- see that function's comment for why the raw
            # constraint window alone isn't enough to avoid a recurring
            # boundary-touch false-conflict.
            for c in constraints:
                if c.location == location and t_start < c.t_end + CONSTRAINT_CLEARANCE_BUFFER and c.t_start < t_end:
                    return True
            return False

        return space_time_search(
            self.graph, agent_id, "quadruped", self.profile.footprint_half_length,
            start_node, goal_node, feasible, speed_fn, blocked,
            heuristic_fn=heuristic, start_time=start_time,
        )
