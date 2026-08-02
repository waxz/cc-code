#!/usr/bin/env bash
# nim/benchmark.sh -- run the compiled Nim benchmarks.
# Builds first if binaries aren't present. Writes results/nim_report.md.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$SCRIPT_DIR/../results/nim_report.md}"
cd "$SCRIPT_DIR"

if [ ! -x bench_struct_nim ] || [ ! -x bench_ringbuffer_nim ]; then
  echo "binaries not found, building first..."
  ./build.sh
fi

mkdir -p "$(dirname "$OUT")"

{
  echo "# commsys Nim benchmark report"
  echo
  echo "Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  echo
  echo "## Hardware"
  echo '```'
  echo "vCPUs: $(nproc)"
  free -h
  nim --version | head -1
  echo '```'
  echo
  echo "## bench_struct.nim (raw struct pack/unpack)"
  echo '```'
} > "$OUT"

./bench_struct_nim >> "$OUT" 2>&1
echo '```' >> "$OUT"
echo >> "$OUT"

echo "## bench_ringbuffer.nim (cross-process shared memory)" >> "$OUT"
echo '```' >> "$OUT"
rm -f /dev/shm/nim_bench_ring 2>/dev/null || true
./bench_ringbuffer_nim >> "$OUT" 2>&1
echo '```' >> "$OUT"
echo >> "$OUT"

if [ -x bench_flatbuffers_nim ]; then
  echo "## bench_flatbuffers.nim (Nim calling the C++ FlatBuffers library)" >> "$OUT"
  echo '```' >> "$OUT"
  ./bench_flatbuffers_nim >> "$OUT" 2>&1
  echo '```' >> "$OUT"
fi

echo "== wrote $OUT =="
