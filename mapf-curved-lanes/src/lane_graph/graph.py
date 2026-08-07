"""Lane-graph map representation.

Represents the environment as lane segments (straight or clothoid arcs) meeting at
junction nodes, instead of a 4/8-connected occupancy grid. Agent trajectories are
expressed in a Frenet frame (arc-length `s` along a lane, lateral offset `d`) so that
conflict checking on a shared straight lane segment reduces to a 1-D interval-overlap
test; full 2-D swept-volume checks are reserved for junctions.

This module is intentionally dependency-light (numpy only) so it can be unit-tested
without OMPL/ROS installed. The Reeds-Shepp curve generation used by the forklift
planner (src/planners/forklift_planner.py) is a separate, optional dependency.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np


@dataclass
class LaneSegment:
    """A single lane segment: either a straight line or a constant-curvature arc.

    Parameterized so that any point on the segment can be recovered from its
    arc-length `s` in [0, length], independent of whether the segment is straight or
    curved. This is what lets straight-segment conflict checks stay 1-D.
    """

    segment_id: str
    start_node: str
    end_node: str
    length: float
    width: float
    curvature: float = 0.0  # 0 => straight; constant curvature => circular arc
    start_pose: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # x, y, heading (rad)

    def pose_at(self, s: float) -> Tuple[float, float, float]:
        """Return (x, y, heading) at arc-length `s` along this segment."""
        if s < 0 or s > self.length + 1e-6:
            raise ValueError(f"s={s} out of range [0, {self.length}] for {self.segment_id}")
        x0, y0, theta0 = self.start_pose
        if abs(self.curvature) < 1e-9:
            x = x0 + s * np.cos(theta0)
            y = y0 + s * np.sin(theta0)
            return x, y, theta0
        r = 1.0 / self.curvature
        dtheta = self.curvature * s
        cx = x0 - r * np.sin(theta0)
        cy = y0 + r * np.cos(theta0)
        theta = theta0 + dtheta
        x = cx + r * np.sin(theta)
        y = cy - r * np.cos(theta)
        return x, y, theta

    def min_turn_radius_required(self) -> Optional[float]:
        if abs(self.curvature) < 1e-9:
            return None
        return 1.0 / abs(self.curvature)


@dataclass
class JunctionNode:
    node_id: str
    position: Tuple[float, float]
    connected_segments: List[str] = field(default_factory=list)


@dataclass
class LaneGraph:
    nodes: Dict[str, JunctionNode] = field(default_factory=dict)
    segments: Dict[str, LaneSegment] = field(default_factory=dict)

    def add_node(self, node: JunctionNode) -> None:
        self.nodes[node.node_id] = node

    def add_segment(self, segment: LaneSegment) -> None:
        self.segments[segment.segment_id] = segment
        self.nodes[segment.start_node].connected_segments.append(segment.segment_id)
        self.nodes[segment.end_node].connected_segments.append(segment.segment_id)

    def neighbors(self, node_id: str) -> List[str]:
        """Segment IDs reachable from a junction node."""
        return list(self.nodes[node_id].connected_segments)

    def junctions_of(self, segment_id: str) -> Tuple[str, str]:
        seg = self.segments[segment_id]
        return seg.start_node, seg.end_node

    def validate(self) -> List[str]:
        """Return a list of consistency problems (empty if the graph is well-formed)."""
        problems = []
        for seg in self.segments.values():
            if seg.start_node not in self.nodes:
                problems.append(f"segment {seg.segment_id}: unknown start_node {seg.start_node}")
            if seg.end_node not in self.nodes:
                problems.append(f"segment {seg.segment_id}: unknown end_node {seg.end_node}")
            if seg.length <= 0:
                problems.append(f"segment {seg.segment_id}: non-positive length")
        return problems
