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


def test_astar_heuristic_matches_dijkstra_on_lane_graph():
    """Regression test for the Dijkstra -> A* upgrade in src/lane_graph/routing.py
    (see its module docstring for why this was made -- the measured single-agent
    benchmark in src/single_agent/). A straight-line-distance heuristic must not
    change which path is found, only how many nodes are expanded getting there.
    """
    from src.lane_graph.routing import shortest_path

    g = LaneGraph()
    g.add_node(JunctionNode("a", (0.0, 0.0)))
    g.add_node(JunctionNode("b", (10.0, 0.0)))
    g.add_node(JunctionNode("c", (10.0, 10.0)))
    g.add_node(JunctionNode("d", (0.0, 10.0)))
    g.add_segment(LaneSegment("ab", "a", "b", length=10.0, width=3.0))
    g.add_segment(LaneSegment("bc", "b", "c", length=10.0, width=3.0))
    g.add_segment(LaneSegment("ad", "a", "d", length=10.0, width=3.0))
    g.add_segment(LaneSegment("dc", "d", "c", length=10.0, width=3.0))

    cost = lambda seg_id: g.segments[seg_id].length
    feasible = lambda seg_id: True

    path_dijkstra = shortest_path(g, "a", "c", cost, feasible, heuristic_fn=None)

    def heuristic(node_id: str) -> float:
        gx, gy = g.nodes["c"].position
        nx, ny = g.nodes[node_id].position
        return ((nx - gx) ** 2 + (ny - gy) ** 2) ** 0.5

    path_astar = shortest_path(g, "a", "c", cost, feasible, heuristic_fn=heuristic)

    cost_dijkstra = sum(g.segments[s].length for s in path_dijkstra)
    cost_astar = sum(g.segments[s].length for s in path_astar)
    assert cost_dijkstra == cost_astar == 20.0  # both equally-short routes cost 20
