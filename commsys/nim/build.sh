#!/usr/bin/env bash
# nim/build.sh -- compile the Nim benchmarks (C++ backend, release mode).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "== commsys/nim build =="
echo "nim: $(nim --version | head -1)"

NIMFLAGS="-d:release -d:danger --opt:speed --passC:-flto --passL:-flto"

echo "-- bench_struct.nim --"
nim cpp $NIMFLAGS -o:bench_struct_nim bench_struct.nim

echo "-- bench_ringbuffer.nim --"
nim cpp $NIMFLAGS -o:bench_ringbuffer_nim bench_ringbuffer.nim

echo "-- bench_flatbuffers.nim (requires system flatbuffers headers) --"
if [ -f /usr/include/flatbuffers/flatbuffers.h ]; then
  nim cpp $NIMFLAGS --passC:-std=c++17 -o:bench_flatbuffers_nim bench_flatbuffers.nim
else
  echo "flatbuffers headers not found, skipping (apt install libflatbuffers-dev flatbuffers-compiler)"
fi

echo "== build complete =="
ls -la bench_*_nim 2>/dev/null || true
