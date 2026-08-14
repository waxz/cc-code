#!/usr/bin/env bash
# python/benchmark.sh -- run the unit test suite and the full
# benchmark sweep. Writes results/python_report.md.
# Usage: ./benchmark.sh [output_file] [--skip-tests]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$SCRIPT_DIR/../results/python_report.md}"

mkdir -p "$(dirname "$OUT")"
rm -f /dev/shm/commsys_* 2>/dev/null || true

{
  echo "# commsys Python benchmark report"
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

echo "== unit tests done, running benchmark sweep (this takes a few minutes) =="
rm -f /dev/shm/commsys_* 2>/dev/null || true
python3 benchmark_report.py

echo >> "$OUT"
echo "## Full benchmark sweep" >> "$OUT"
echo >> "$OUT"
cat "$SCRIPT_DIR/BENCHMARK_REPORT.md" >> "$OUT"

echo >> "$OUT"
echo "## Pub/sub workflow benchmark" >> "$OUT"
echo >> "$OUT"
echo "Realistic multi-topic workflow (imu=100Hz, encoder=50Hz, pose=20Hz)," >> "$OUT"
echo "as opposed to the isolated single-topic sweeps and unpaced firehose" >> "$OUT"
echo "stress tests above. Same workflow exists in C++ for direct comparison" >> "$OUT"
echo "-- see cpp/PUBSUB_WORKFLOW_COMPARISON.md." >> "$OUT"
echo '```' >> "$OUT"
rm -f /dev/shm/commsys_* 2>/dev/null || true
python3 "$SCRIPT_DIR/pubsub_workflow_benchmark.py" shm 5 >> "$OUT" 2>&1
rm -f /dev/shm/commsys_* 2>/dev/null || true
python3 "$SCRIPT_DIR/pubsub_workflow_benchmark.py" udp 5 >> "$OUT" 2>&1
echo '```' >> "$OUT"

echo "== wrote $OUT =="
