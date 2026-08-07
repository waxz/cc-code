#!/usr/bin/env bash
# mapf-curved-lanes/benchmark.sh -- run the unit test suite plus the one
# stage of the pipeline that is actually end-to-end runnable today
# (benchmark instance generation). Writes results/mapf-curved-lanes_report.md.
#
# This module is early-stage research code (see README.md "Status"): the
# lane-graph geometry, Frenet conflict checking, and the CBS/PBS high-level
# search are implemented and tested. The per-agent-class low-level planners
# and the junction swept-volume checker are not, so there is no solver-level
# benchmark to run yet -- this script reports that honestly rather than
# fabricating numbers for an unimplemented solver.
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

echo "== unit tests done, running instance generation across map sizes =="
INSTANCE_DIR="$(mktemp -d)"

{
  echo "## Instance generation (the only end-to-end runnable pipeline stage)"
  echo
  echo '```'
} >> "$OUT"

for size in small medium large; do
  for agents in 10 25 50; do
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

cat >> "$OUT" << 'EOF'
## Solver status (honesty check, not a benchmark)

The high-level conflict-tree search (`src/high_level/conflict_tree.py`) and the
lane-graph geometry/conflict layer (`src/lane_graph/`) are implemented and covered
by the unit tests above. The per-agent-class low-level planners
(`src/planners/forklift_planner.py`, `src/planners/quadruped_planner.py`) and the
junction swept-volume conflict checker
(`src/lane_graph/conflicts.py::JunctionConflictChecker`) currently raise
`NotImplementedError`. There is therefore no solver-level result to compare
against the CL-CBS / HCBS baselines described in `docs/benchmark_plan.md` yet --
that comparison is the next milestone, not something this report claims to have.
EOF

echo "== wrote $OUT =="
