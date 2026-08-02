#!/usr/bin/env bash
# cpp/benchmark.sh -- run smoke tests and the full benchmark sweep.
# Assumes build.sh has already been run (or runs it if the build dir
# is missing). Writes results/cpp_report.md.
# Usage: ./benchmark.sh [build_dir] [output_file]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${1:-$SCRIPT_DIR/build}"
OUT="${2:-$SCRIPT_DIR/../results/cpp_report.md}"

if [ ! -x "$BUILD_DIR/node/benchmark_report" ]; then
  echo "build not found at $BUILD_DIR, building first..."
  "$SCRIPT_DIR/build.sh" "$BUILD_DIR"
fi

mkdir -p "$(dirname "$OUT")"
rm -f /dev/shm/commsys_cpp_* 2>/dev/null || true

{
  echo "# commsys C++ benchmark report"
  echo
  echo "Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  echo
  echo "## Hardware"
  echo '```'
  echo "vCPUs: $(nproc)"
  free -h
  uname -a
  echo '```'
  echo
  echo "## Smoke tests"
  echo '```'
} > "$OUT"

echo "-- test_node_basic --" >> "$OUT"
rm -f /dev/shm/commsys_cpp_* 2>/dev/null || true
"$BUILD_DIR/node/test_node_basic" >> "$OUT" 2>&1

echo "-- test_node_udp_latest --" >> "$OUT"
rm -f /dev/shm/commsys_cpp_* 2>/dev/null || true
"$BUILD_DIR/node/test_node_udp_latest" >> "$OUT" 2>&1

echo "-- test_ring_stress --" >> "$OUT"
rm -f /dev/shm/commsys_cpp_* 2>/dev/null || true
"$BUILD_DIR/node/test_ring_stress" >> "$OUT" 2>&1

echo '```' >> "$OUT"
echo >> "$OUT"
echo "## Full benchmark sweep" >> "$OUT"
echo >> "$OUT"

rm -f /dev/shm/commsys_cpp_* 2>/dev/null || true
"$BUILD_DIR/node/benchmark_report" >> "$OUT"

echo "== wrote $OUT =="
