import math

import pytest

from src.lane_graph.graph import JunctionNode, LaneGraph, LaneSegment


def test_straight_segment_pose_at():
    seg = LaneSegment(
        segment_id="s1", start_node="a", end_node="b",
        length=10.0, width=3.0, curvature=0.0, start_pose=(0.0, 0.0, 0.0),
    )
    x, y, theta = seg.pose_at(5.0)
    assert x == pytest.approx(5.0)
    assert y == pytest.approx(0.0)
    assert theta == pytest.approx(0.0)


def test_curved_segment_quarter_circle():
    # Curvature 1/r with r=2 -> quarter circle has arc length = pi*r/2
    r = 2.0
    seg = LaneSegment(
        segment_id="s2", start_node="a", end_node="b",
        length=(math.pi * r / 2), width=3.0, curvature=1.0 / r,
        start_pose=(0.0, 0.0, 0.0),
    )
    x, y, theta = seg.pose_at(seg.length)
    # After a quarter turn to the left, heading should be pi/2 and position near (r, r)
    assert theta == pytest.approx(math.pi / 2, abs=1e-6)
    assert x == pytest.approx(r, abs=1e-6)
    assert y == pytest.approx(r, abs=1e-6)


def test_pose_at_out_of_range_raises():
    seg = LaneSegment(
        segment_id="s3", start_node="a", end_node="b",
        length=5.0, width=3.0,
    )
    with pytest.raises(ValueError):
        seg.pose_at(10.0)


def test_graph_add_and_neighbors():
    g = LaneGraph()
    g.add_node(JunctionNode(node_id="a", position=(0, 0)))
    g.add_node(JunctionNode(node_id="b", position=(10, 0)))
    g.add_segment(
        LaneSegment(segment_id="s1", start_node="a", end_node="b", length=10.0, width=3.0)
    )
    assert g.neighbors("a") == ["s1"]
    assert g.neighbors("b") == ["s1"]
    assert g.junctions_of("s1") == ("a", "b")


def test_graph_validate_catches_missing_node():
    g = LaneGraph()
    g.segments["orphan"] = LaneSegment(
        segment_id="orphan", start_node="missing_a", end_node="missing_b",
        length=5.0, width=3.0,
    )
    problems = g.validate()
    assert len(problems) == 2
