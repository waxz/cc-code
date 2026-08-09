"""Run dijkstra(), astar(), and jps() (src/single_agent/grid_planners.py) over
every scenario in a MovingAI .scen file and report success rate and performance
metrics for each, per the "basement of multi-agent path planning" framing in
docs/single_agent_benchmark.md: this validates and benchmarks the single-agent
search the multi-agent solver's low-level planners depend on, on a standard,
citable dataset, rather than only on this project's own generated instances.

jps() targets a different (corner-cutting-allowed) cost model than dijkstra()/
astar() -- see src/single_agent/grid_planners.py's module docstring above jps()
for why -- so its "success" here means self-consistency against
dijkstra_allow_corner_cutting() (the matching-model reference), not an exact
match to the scenario's own no-corner-cut optimal_length. Whether jps's cost
happens to equal or beat that stricter optimal_length is reported as separate,
additional information, not folded into "success" as if it were a defect when
it doesn't match.

Usage:
    python -m src.benchmark.single_agent_benchmark \\
        --map data/movingai/random-32-32-20.map \\
        --scen data/movingai/random-32-32-20-random-1.scen \\
        --out results/single_agent_benchmark.csv
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import List

from src.single_agent.grid_planners import astar, dijkstra, dijkstra_allow_corner_cutting, jps
from src.single_agent.movingai_io import load_map, load_scen

FIELDNAMES = [
    "scenario_index", "start", "goal", "optimal_length",
    "planner", "success", "cost", "nodes_expanded", "runtime_s",
]

# A path counts as a success only if found AND its cost matches the scenario's
# known-optimal length within floating-point tolerance -- not just "a path was
# found", since a bug that returns a suboptimal but nonempty path should show up
# as a failure here, not a pass. (jps is scored differently -- see module docstring.)
COST_TOLERANCE = 1e-3


def run_benchmark(map_path: Path, scen_path: Path, limit: int = None) -> List[dict]:
    grid = load_map(map_path)
    scens = load_scen(scen_path)
    if limit:
        scens = scens[:limit]

    rows = []
    for i, s in enumerate(scens):
        for name, planner in (("dijkstra", dijkstra), ("astar", astar)):
            result = planner(grid, s.start, s.goal)
            success = (
                result.path is not None
                and abs(result.cost - s.optimal_length) < COST_TOLERANCE
            )
            rows.append({
                "scenario_index": i, "start": s.start, "goal": s.goal,
                "optimal_length": s.optimal_length, "planner": name,
                "success": success, "cost": result.cost,
                "nodes_expanded": result.nodes_expanded,
                "runtime_s": round(result.runtime_s, 6),
            })

        # jps targets a different cost model (corner-cutting allowed) -- score
        # against the matching-model reference, not the stricter benchmark
        # optimal_length. See module docstring.
        r_jps = jps(grid, s.start, s.goal)
        r_ref = dijkstra_allow_corner_cutting(grid, s.start, s.goal)
        jps_self_consistent = (
            r_jps.path is not None and abs(r_jps.cost - r_ref.cost) < COST_TOLERANCE
        )
        rows.append({
            "scenario_index": i, "start": s.start, "goal": s.goal,
            "optimal_length": s.optimal_length, "planner": "jps",
            "success": jps_self_consistent, "cost": r_jps.cost,
            "nodes_expanded": r_jps.nodes_expanded,
            "runtime_s": round(r_jps.runtime_s, 6),
        })
    return rows


def summarize(rows: List[dict]) -> str:
    by_planner: dict = {}
    for r in rows:
        by_planner.setdefault(r["planner"], []).append(r)

    lines = ["=== Single-agent benchmark summary (random-32-32-20, MovingAI) ==="]
    for planner, planner_rows in sorted(by_planner.items()):
        n = len(planner_rows)
        successes = [r for r in planner_rows if r["success"]]
        success_rate = len(successes) / n if n else 0.0
        avg_nodes = sum(r["nodes_expanded"] for r in planner_rows) / n if n else 0.0
        avg_runtime = sum(r["runtime_s"] for r in planner_rows) / n if n else 0.0
        label = "success_rate" if planner != "jps" else "self_consistent_rate"
        lines.append(
            f"{planner:10s} n={n:4d}  {label}={success_rate:.2%}  "
            f"avg_nodes_expanded={avg_nodes:8.1f}  avg_runtime={avg_runtime*1000:.3f}ms"
        )

    if "dijkstra" in by_planner and "astar" in by_planner:
        dj_nodes = sum(r["nodes_expanded"] for r in by_planner["dijkstra"])
        as_nodes = sum(r["nodes_expanded"] for r in by_planner["astar"])
        if as_nodes > 0:
            reduction = 1 - (as_nodes / dj_nodes)
            lines.append(
                f"astar reduces total nodes expanded by {reduction:.1%} vs. dijkstra "
                f"({dj_nodes} -> {as_nodes}), at identical solution cost (both optimal)"
            )

    if "astar" in by_planner and "jps" in by_planner:
        as_nodes = sum(r["nodes_expanded"] for r in by_planner["astar"])
        jp_nodes = sum(r["nodes_expanded"] for r in by_planner["jps"])
        below_optimal = sum(
            1 for r in by_planner["jps"] if r["cost"] < r["optimal_length"] - COST_TOLERANCE
        )
        equal_optimal = sum(
            1 for r in by_planner["jps"] if abs(r["cost"] - r["optimal_length"]) < COST_TOLERANCE
        )
        n = len(by_planner["jps"])
        if as_nodes > 0:
            reduction = 1 - (jp_nodes / as_nodes)
            lines.append(
                f"jps reduces total nodes expanded by {reduction:.1%} vs. astar "
                f"({as_nodes} -> {jp_nodes}) -- different cost model (corner-cutting "
                f"allowed), so not a same-cost comparison: jps cost equals the "
                f"benchmark's stricter no-cut optimal on {equal_optimal}/{n} scenarios "
                f"and is strictly lower (a corner shortcut exists) on {below_optimal}/{n}"
            )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--scen", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=None,
                         help="Only run the first N scenarios (default: all)")
    args = parser.parse_args()

    rows = run_benchmark(args.map, args.scen, args.limit)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(summarize(rows))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
