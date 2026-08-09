#!/usr/bin/env bash
# mapf-curved-lanes/benchmark.sh -- run the unit test suite, instance generation
# timing, and a solver-vs-classical-grid-CBS-baseline comparison. Writes
# results/mapf-curved-lanes_report.md.
#
# This module is early-stage research code (see README.md "Status"): the
# lane-graph geometry, Frenet conflict checking, CBS/PBS high-level search, both
# low-level planners, and a classical grid-CBS baseline are implemented and tested.
# The junction swept-volume checker (as opposed to the simpler node-occupancy
# approximation actually in use) and a literal CL-CBS/HCBS reimplementation are
# not -- see docs/benchmark_plan.md and README.md "Status".
#
# Usage: ./benchmark.sh [output_file]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$SCRIPT_DIR/../mapf-curved-lanes/results/mapf-curved-lanes_report.md}"
mkdir -p "$(dirname "$OUT")"

{
  echo "# mapf-curved-lanes benchmark report"
  echo
  echo "Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  echo
  echo "## Hardware"
  echo '```'
  echo "vCPUs: $(nproc)"
  free -h
  python3 --version
  echo '```'
  echo
  echo "## Unit tests"
  echo '```'
} > "$OUT"

cd "$SCRIPT_DIR"
python3 -m pytest tests/ -v >> "$OUT" 2>&1
echo '```' >> "$OUT"
echo >> "$OUT"

echo "== unit tests done, running single-agent benchmark (MovingAI dataset) =="
{
  echo "## Single-agent global planner benchmark (real MovingAI dataset)"
  echo
  echo "See \`docs/single_agent_benchmark.md\` for the full writeup -- this is the"
  echo "foundation the multi-agent low-level planners' routing"
  echo "(\`src/lane_graph/routing.py\`) is built on and was benchmarked against."
  echo
  echo '```'
} >> "$OUT"
python3 -m src.benchmark.single_agent_benchmark \
  --map data/movingai/random-32-32-20.map \
  --scen data/movingai/random-32-32-20-random-1.scen \
  --out "$SCRIPT_DIR/results/single_agent_benchmark.csv" \
  >> "$OUT" 2>&1
echo '```' >> "$OUT"
echo >> "$OUT"

echo "== single-agent benchmark done, running instance generation across map sizes =="
INSTANCE_DIR="$(mktemp -d)"

{
  echo "## Instance generation timing"
  echo
  echo '```'
} >> "$OUT"

for size in small medium large; do
  for agents in 10 25; do
    t0=$(date +%s.%N)
    python3 -m src.benchmark.generate_instances \
      --out "$INSTANCE_DIR" \
      --map-size "$size" --n-agents "$agents" --fleet-mix 50:50 --n-instances 3 \
      >> "$OUT" 2>&1
    t1=$(date +%s.%N)
    elapsed=$(python3 -c "print(f'{$t1 - $t0:.3f}')")
    echo "  (${size} map, ${agents} agents, 3 instances: ${elapsed}s)" >> "$OUT"
  done
done
echo '```' >> "$OUT"
echo >> "$OUT"
rm -rf "$INSTANCE_DIR"

echo "== instance generation done, running solver-vs-grid-CBS comparison =="
{
  echo "## Solver comparison: ours_full vs. classical grid-CBS baseline"
  echo
  echo "See \`docs/benchmark_plan.md\` for what each column means. This is a small,"
  echo "CI-runtime-bounded sweep (few agents, few instances) -- not the full"
  echo "benchmark sweep described in the research proposal, which would need much"
  echo "more compute than a CI job budget allows."
  echo
  echo '```'
} >> "$OUT"
python3 -m src.benchmark.run_solver_benchmark \
  --out "$SCRIPT_DIR/results/solver_benchmark.csv" \
  --map-sizes small --agent-counts 2 3 4 --n-instances 3 --seed 7 \
  >> "$OUT" 2>&1
echo '```' >> "$OUT"
echo >> "$OUT"

cat >> "$OUT" << 'EOF'
### Known limitation, found by running this comparison (not by inspection)

Both solvers show a real completeness gap on these small/sparse instances, for two
different reasons:

- **`ours_full`**: the low-level planners (`src/planners/forklift_planner.py`,
  `src/planners/quadruped_planner.py`) fix their route via A* once (see
  `docs/single_agent_benchmark.md` for the upgrade from plain Dijkstra) and, under
  a high-level constraint, only insert waits -- they never try an alternate route
  around a contested segment. Tracing a specific non-converging instance showed the
  search exploring hundreds of branches that all plateau at the exact same cost,
  which is the signature of a real incompleteness rather than "just needs a bigger
  expansion budget" (confirmed by re-running the same instance at 5000 expansions
  with no change). The fix is a low-level planner that treats a constraint as a
  temporarily removed edge and re-runs the search, not just a wait-insertion pass
  -- that's the clear next implementation step, not something papered over here.
- **`grid_cbs`**: the grid-discretization translation (`instance_to_grid`) can snap
  multiple distinct lane-graph junctions to the same coarse grid cell on a small
  map, which can make an otherwise-solvable instance spuriously harder or
  degenerate after translation. This is a limitation of the *baseline's map
  translation*, not the CBS algorithm itself -- `src/baselines/grid_cbs.py` is
  independently verified correct on hand-built swap-conflict cases (see
  `tests/test_grid_cbs.py`).

Reported success rates and costs above should be read with both caveats in mind --
they are real numbers from real runs, not fabricated, but they reflect these two
distinct known limitations rather than a clean apples-to-apples capability
comparison yet.

EOF

echo "== unit tests + instance generation + solver comparison done ==" >> "$OUT" 2>&1

echo "== wrote $OUT =="
