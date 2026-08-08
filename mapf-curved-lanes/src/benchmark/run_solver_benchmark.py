"""Run the lane-graph solver (src/solver.py) and the classical grid-CBS baseline
(src/baselines/grid_cbs.py) on the same set of generated instances and report both,
per docs/benchmark_plan.md sections 1-3.

This is the actual "does the research gap's proposed approach do anything" check:
baseline #1 (grid_cbs) ignores curvature and load-dependence entirely; comparing it
against ours_full on the same instances is what would show whether that matters, in
terms of success rate, cost, and the metrics specific to this project's contribution
(min_stability_margin). CL-CBS and HCBS (baselines #2/#3 in the benchmark plan) are
not implemented here -- see docs/benchmark_plan.md and README.md "Status" for why
that remains a separate, larger piece of work rather than something quietly skipped.

KNOWN LIMITATION, found by actually running this (not by inspection): ours_full's
success rate on denser instances (roughly 4+ agents on a small, sparse lane-graph)
is noticeably lower than the grid baseline's, and it is NOT primarily an
expansion-budget problem -- tracing a specific non-converging instance showed the
search exploring hundreds of branches that all plateau at the exact same cost,
which is the signature of a real completeness gap rather than "just needs more
budget". Root cause: the low-level planners (src/planners/) fix their route via
Dijkstra once and, under a constraint, only insert waits -- they never try an
alternate route around a contested segment. On a sparse graph, a bottleneck
contested by 3+ agents can be structurally unsolvable by waiting alone even though
a solution exists via a longer alternate path. The natural fix is a low-level
planner that treats a constraint's (location, time-window) as a temporarily removed
edge and re-runs Dijkstra, not just a wait-insertion pass -- flagged here as the
clear next step rather than worked around by loosening the comparison.

Usage:
    python -m src.benchmark.run_solver_benchmark --out results/solver_benchmark.csv \\
        --map-sizes small medium --agent-counts 6 10 16 --n-instances 5
"""
from __future__ import annotations

import argparse
import csv
import zlib
from pathlib import Path
from typing import List

from src.baselines.grid_cbs import instance_to_grid, solve_grid_cbs
from src.benchmark.generate_instances import generate_instance
from src.solver import solve_instance

FIELDNAMES = [
    "instance_id", "map_size", "junction_density", "n_agents", "fleet_mix",
    "solver", "success", "sum_of_costs", "makespan", "runtime_s",
    "high_level_expansions", "min_stability_margin",
]


def run_one_instance(instance_id, map_size, junction_density, n_agents, fleet_mix, seed):
    graph, instance = generate_instance(
        instance_id, map_size, junction_density, n_agents, fleet_mix, seed
    )
    rows = []

    ours = solve_instance(graph, instance.agents, mode="cbs", max_expansions=300)
    rows.append({
        "instance_id": instance_id, "map_size": map_size, "junction_density": junction_density,
        "n_agents": n_agents, "fleet_mix": fleet_mix, "solver": "ours_full",
        "success": ours.success, "sum_of_costs": round(ours.sum_of_costs, 3),
        "makespan": round(ours.makespan, 3), "runtime_s": round(ours.runtime_s, 4),
        "high_level_expansions": ours.high_level_expansions,
        "min_stability_margin": round(ours.min_stability_margin, 3),
    })

    grid_agents, width, height = instance_to_grid(graph, instance.agents)
    grid_result = solve_grid_cbs(grid_agents, width, height, max_t=200, max_expansions=500)
    rows.append({
        "instance_id": instance_id, "map_size": map_size, "junction_density": junction_density,
        "n_agents": n_agents, "fleet_mix": fleet_mix, "solver": "grid_cbs",
        "success": grid_result.success, "sum_of_costs": grid_result.sum_of_costs,
        "makespan": grid_result.makespan, "runtime_s": round(grid_result.runtime_s, 4),
        "high_level_expansions": grid_result.high_level_expansions,
        "min_stability_margin": "",  # not a meaningful metric for the grid baseline
    })

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--map-sizes", nargs="+", default=["small"])
    parser.add_argument("--agent-counts", type=int, nargs="+", default=[6, 10])
    parser.add_argument("--fleet-mix", default="50:50")
    parser.add_argument("--junction-density", default="medium")
    parser.add_argument("--n-instances", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    all_rows = []

    for map_size in args.map_sizes:
        for n_agents in args.agent_counts:
            for k in range(args.n_instances):
                instance_id = f"{map_size}_{args.junction_density}_a{n_agents}_{k:03d}"
                # zlib.crc32, not Python's built-in hash(): hash() of strings is
                # randomized per-process (PYTHONHASHSEED) unless explicitly fixed,
                # so seeding off it silently made "the same" instance_id refer to a
                # different random instance on every run -- caught by manually
                # tracing a "non-converging" instance twice and getting two
                # different agent sets both times. crc32 is deterministic.
                seed = args.seed + zlib.crc32(instance_id.encode()) % 100000
                rows = run_one_instance(
                    instance_id, map_size, args.junction_density, n_agents, args.fleet_mix, seed
                )
                all_rows.extend(rows)
                for r in rows:
                    print(f"  {instance_id:35s} {r['solver']:10s} success={r['success']!s:5} "
                          f"cost={r['sum_of_costs']!s:>8} runtime={r['runtime_s']}s")

    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(all_rows)

    _print_summary(all_rows)
    print(f"\nwrote {args.out}")


def _print_summary(rows: List[dict]) -> None:
    by_solver: dict = {}
    for r in rows:
        by_solver.setdefault(r["solver"], []).append(r)

    print("\n=== Summary ===")
    for solver, solver_rows in sorted(by_solver.items()):
        n = len(solver_rows)
        successes = [r for r in solver_rows if r["success"] in (True, "True")]
        success_rate = len(successes) / n if n else 0.0
        avg_runtime = sum(r["runtime_s"] for r in solver_rows) / n if n else 0.0
        avg_cost = (
            sum(r["sum_of_costs"] for r in successes) / len(successes) if successes else float("nan")
        )
        print(
            f"{solver:10s}  n={n:4d}  success_rate={success_rate:.2%}  "
            f"avg_runtime={avg_runtime:.4f}s  avg_cost_when_solved={avg_cost:.2f}"
        )


if __name__ == "__main__":
    main()
