"""Generate benchmark instances per docs/benchmark_plan.md section 1.

Produces a lane-graph map plus a set of (agent_id, class, start, goal, load_state)
tuples, saved as JSON so any baseline (grid-CBS, CL-CBS, HCBS, this project's solver)
can consume the same instance definitions for a fair comparison.

Run as a script:

    python -m src.benchmark.generate_instances --out data/instances \\
        --map-size medium --n-agents 10 --fleet-mix 50:50 --n-instances 5

This module has no dependency on the still-stubbed planners -- it only needs the
lane-graph data structures, so it is runnable today.
"""
from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Tuple

from src.lane_graph.graph import JunctionNode, LaneGraph, LaneSegment

MAP_SIZES = {
    "small": 50.0,
    "medium": 100.0,
    "large": 300.0,
}


@dataclass
class AgentSpec:
    agent_id: str
    agent_class: str  # "forklift" or "quadruped"
    start_node: str
    goal_node: str
    load_state: str  # "empty" or "laden"; ignored for quadrupeds


@dataclass
class Instance:
    instance_id: str
    map_size: str
    junction_density: str
    n_agents: int
    fleet_mix: str
    agents: List[AgentSpec]


def _grid_lane_graph(extent: float, junction_density: str, rng: random.Random) -> LaneGraph:
    """Build a simple grid-of-junctions lane graph as a starting point.

    Not the final curved-lane map generator -- this produces straight segments on a
    regular junction grid, spaced according to junction_density, as a structurally
    valid LaneGraph that downstream code can already run against. Replacing straight
    segments with clothoid arcs between the same junctions (to get genuinely curved
    lanes, per the research proposal) is a follow-up: see the `curvature` field on
    LaneSegment, which this function currently leaves at 0.0 (straight).
    """
    spacing = {"low": 25.0, "medium": 15.0, "high": 8.0}[junction_density]
    n = max(2, int(extent // spacing))
    graph = LaneGraph()

    for i in range(n):
        for j in range(n):
            node_id = f"n_{i}_{j}"
            graph.add_node(JunctionNode(node_id=node_id, position=(i * spacing, j * spacing)))

    for i in range(n):
        for j in range(n):
            if i + 1 < n:
                seg_id = f"s_{i}_{j}_{i+1}_{j}"
                graph.add_segment(
                    LaneSegment(
                        segment_id=seg_id,
                        start_node=f"n_{i}_{j}",
                        end_node=f"n_{i+1}_{j}",
                        length=spacing,
                        width=3.0,
                        curvature=0.0,
                        start_pose=(i * spacing, j * spacing, 0.0),
                    )
                )
            if j + 1 < n:
                seg_id = f"s_{i}_{j}_{i}_{j+1}"
                graph.add_segment(
                    LaneSegment(
                        segment_id=seg_id,
                        start_node=f"n_{i}_{j}",
                        end_node=f"n_{i}_{j+1}",
                        length=spacing,
                        width=3.0,
                        curvature=0.0,
                        start_pose=(i * spacing, j * spacing, 1.5707963),
                    )
                )
    problems = graph.validate()
    if problems:
        raise RuntimeError(f"generated an invalid lane graph: {problems}")
    return graph, list(graph.nodes.keys())


def _parse_fleet_mix(mix: str) -> Tuple[int, int]:
    forklift_pct, quadruped_pct = (int(x) for x in mix.split(":"))
    if forklift_pct + quadruped_pct != 100:
        raise ValueError(f"fleet mix must sum to 100, got {mix}")
    return forklift_pct, quadruped_pct


def generate_instance(
    instance_id: str,
    map_size: str,
    junction_density: str,
    n_agents: int,
    fleet_mix: str,
    seed: int,
) -> Tuple[LaneGraph, Instance]:
    rng = random.Random(seed)
    extent = MAP_SIZES[map_size]
    graph, node_ids = _grid_lane_graph(extent, junction_density, rng)

    forklift_pct, _ = _parse_fleet_mix(fleet_mix)
    n_forklift = round(n_agents * forklift_pct / 100)
    n_quadruped = n_agents - n_forklift

    agents: List[AgentSpec] = []
    used_starts = set()
    for i in range(n_agents):
        agent_class = "forklift" if i < n_forklift else "quadruped"
        start = rng.choice(node_ids)
        goal = rng.choice([n for n in node_ids if n != start])
        used_starts.add(start)
        load_state = rng.choice(["empty", "laden"]) if agent_class == "forklift" else "empty"
        agents.append(
            AgentSpec(
                agent_id=f"{agent_class}_{i}",
                agent_class=agent_class,
                start_node=start,
                goal_node=goal,
                load_state=load_state,
            )
        )

    instance = Instance(
        instance_id=instance_id,
        map_size=map_size,
        junction_density=junction_density,
        n_agents=n_agents,
        fleet_mix=fleet_mix,
        agents=agents,
    )
    return graph, instance


def save_instance(graph: LaneGraph, instance: Instance, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    graph_json = {
        "nodes": {
            nid: {"position": n.position, "connected_segments": n.connected_segments}
            for nid, n in graph.nodes.items()
        },
        "segments": {
            sid: asdict(s) for sid, s in graph.segments.items()
        },
    }
    (out_dir / f"{instance.instance_id}_map.json").write_text(json.dumps(graph_json, indent=2))
    (out_dir / f"{instance.instance_id}_agents.json").write_text(
        json.dumps(asdict(instance), indent=2)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--map-size", choices=list(MAP_SIZES), default="medium")
    parser.add_argument("--junction-density", choices=["low", "medium", "high"], default="medium")
    parser.add_argument("--n-agents", type=int, default=10)
    parser.add_argument("--fleet-mix", default="50:50")
    parser.add_argument("--n-instances", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    for k in range(args.n_instances):
        instance_id = (
            f"{args.map_size}_{args.junction_density}_a{args.n_agents}_"
            f"m{args.fleet_mix.replace(':', '-')}_{k:03d}"
        )
        graph, instance = generate_instance(
            instance_id=instance_id,
            map_size=args.map_size,
            junction_density=args.junction_density,
            n_agents=args.n_agents,
            fleet_mix=args.fleet_mix,
            seed=args.seed + k,
        )
        save_instance(graph, instance, args.out)
        print(f"wrote {instance_id}")


if __name__ == "__main__":
    main()
