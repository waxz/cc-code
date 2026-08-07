"""Low-level planner for car-like agents (forklifts) with load-dependent kinematics.

Core idea from docs/research_proposal.md section 3.2: a forklift's curvature bound and
max lateral acceleration are not constants but functions of its load state, derived
from a friction-circle / tipping-margin model. This is what differentiates this
planner from CL-CBS's fixed-curvature Reeds-Shepp planner.

The Reeds-Shepp curve generation itself is delegated to an external library (OMPL is
the standard choice, matching CL-CBS's toolchain for comparable runtimes -- see
docs/related_work.md). This module owns the load-dependent constraint model and the
adapter around whichever curve generator is installed; it does not reimplement
Reeds-Shepp geometry.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple


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


@dataclass
class ForkliftTrajectory:
    poses: List[Pose2D]
    timestamps: List[float]
    load_state: LoadState


class ForkliftPlanner:
    """Adapter around a Reeds-Shepp / hybrid-A* curve generator.

    TODO: wire up an actual Reeds-Shepp implementation (OMPL's
    `ompl.base.ReedsSheppStateSpace` is the reference used by CL-CBS; a pure-Python
    fallback such as `reeds_shepp` on PyPI works for prototyping without the OMPL
    build dependency). `plan` currently raises NotImplementedError so this remains
    honest about what is and isn't implemented yet.
    """

    def __init__(self, profile: Optional[ForkliftKinematicProfile] = None):
        self.profile = profile or ForkliftKinematicProfile()

    def plan(
        self,
        start: Pose2D,
        goal: Pose2D,
        load_state: LoadState,
        constraints: Optional[List] = None,
    ) -> ForkliftTrajectory:
        """Plan a Reeds-Shepp path from start to goal under the load-dependent
        curvature bound, respecting any high-level-search-imposed spatiotemporal
        constraints (see src/high_level/conflict_tree.py).
        """
        raise NotImplementedError(
            "Reeds-Shepp curve generation not yet wired up. Curvature bound for the "
            f"requested load state is {self.profile.curvature_bound(load_state):.4f} "
            "(1/m) -- use this as the constraint when integrating a curve generator."
        )
