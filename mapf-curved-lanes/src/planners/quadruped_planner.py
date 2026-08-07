"""Low-level planner for legged agents (quadrupeds) at the MAPF coordination layer.

Per docs/research_proposal.md section 3.2 and 5, this project deliberately models the
quadruped abstractly at the coordination layer: a variable-footprint holonomic agent
that can turn in place or sidestep (unlike the forklift), with cost shaped by an
energy proxy. Full footstep-level execution is out of scope here and is deferred to a
downstream kinodynamic-refinement stage (see docs/related_work.md, WinkTPG), following
the plan-then-refine separation used elsewhere in MAPF-to-execution pipelines.

If/when this project is extended toward footstep-level validation, that work should
build on the leg-level IK formulation from the related Yin et al. (2024) extension
referenced in docs/related_work.md rather than duplicating it here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from src.planners.forklift_planner import Pose2D


@dataclass
class QuadrupedKinematicProfile:
    """Illustrative placeholders -- calibrate against the target platform before use."""

    max_speed: float = 1.2          # m/s, omnidirectional
    max_turn_rate: float = 2.0       # rad/s, can turn in place (unlike the forklift)
    footprint_length: float = 0.9    # m
    footprint_width: float = 0.4     # m


@dataclass
class QuadrupedTrajectory:
    poses: List[Pose2D]
    timestamps: List[float]
    energy_cost: float  # proxy cost, see module docstring


class QuadrupedPlanner:
    """Holonomic low-level planner with an energy-shaped cost function.

    TODO: implement the actual search (e.g. a lattice planner over the lane-graph's
    Frenet coordinates, since even a holonomic agent should stay lane-aware for
    conflict-checking tractability -- see src/lane_graph/conflicts.py). The energy
    cost function should be consistent with the peak-vs-average battery current
    framing from the related energy-aware locomotion work rather than a naive
    path-length cost.
    """

    def __init__(self, profile: Optional[QuadrupedKinematicProfile] = None):
        self.profile = profile or QuadrupedKinematicProfile()

    def plan(
        self,
        start: Pose2D,
        goal: Pose2D,
        constraints: Optional[List] = None,
    ) -> QuadrupedTrajectory:
        raise NotImplementedError(
            "Holonomic lattice planner not yet implemented. See module docstring for "
            "the intended design (lane-graph-aware search with energy-shaped cost)."
        )
