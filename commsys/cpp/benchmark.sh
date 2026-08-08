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
  echo "## Unit tests (ctest / Catch2)"
  echo '```'
} > "$OUT"

rm -f /dev/shm/*_test_* /dev/shm/commsys_test_* /dev/shm/rb_* /dev/shm/lvs_* /dev/shm/disc_* 2>/dev/null || true
(cd "$BUILD_DIR" && ctest --output-on-failure --repeat until-pass:3) >> "$OUT" 2>&1 || echo "(unit tests unavailable or failed -- see above; Catch2 may not be installed)" >> "$OUT"
echo '```' >> "$OUT"
echo >> "$OUT"

{
  echo "## Smoke tests"
  echo '```'
} >> "$OUT"

echo "-- test_node_basic --" >> "$OUT"
rm -f /dev/shm/commsys_cpp_* 2>/dev/null || true
"$BUILD_DIR/node/test_node_basic" >> "$OUT" 2>&1

echo "-- test_node_udp_latest --" >> "$OUT"
rm -f /dev/shm/commsys_cpp_* 2>/dev/null || true
"$BUILD_DIR/node/test_node_udp_latest" >> "$OUT" 2>&1

echo "-- test_ring_stress --" >> "$OUT"
rm -f /dev/shm/commsys_cpp_* 2>/dev/null || true
"$BUILD_DIR/node/test_ring_stress" >> "$OUT" 2>&1

echo "-- test_typed_api --" >> "$OUT"
rm -f /dev/shm/commsys_cpp_* 2>/dev/null || true
"$BUILD_DIR/node/test_typed_api" >> "$OUT" 2>&1

echo '```' >> "$OUT"
echo >> "$OUT"
echo "## Full benchmark sweep" >> "$OUT"
echo >> "$OUT"

rm -f /dev/shm/commsys_cpp_* 2>/dev/null || true
"$BUILD_DIR/node/benchmark_report" >> "$OUT"

echo >> "$OUT"
echo "## CPU core affinity comparison" >> "$OUT"
echo >> "$OUT"
echo "Tests whether pinning the publisher and subscriber to dedicated CPU" >> "$OUT"
echo "cores (sched_setaffinity) reduces scheduling-contention tail latency," >> "$OUT"
echo "compared to leaving scheduling up to the OS default. On a single-core" >> "$OUT"
echo "machine this is structurally a no-op (nothing to isolate from)." >> "$OUT"
echo '```' >> "$OUT"
rm -f /dev/shm/commsys_cpp_* 2>/dev/null || true
"$BUILD_DIR/node/bench_cpu_affinity" >> "$OUT" 2>&1
echo '```' >> "$OUT"

echo "== wrote $OUT =="
