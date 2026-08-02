#!/usr/bin/env bash
# cpp/build.sh -- configure and build the C++ module via CMake.
# Usage: ./build.sh [build_dir]   (default build dir: cpp/build)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${1:-$SCRIPT_DIR/build}"

echo "== commsys/cpp build =="
echo "source: $SCRIPT_DIR"
echo "build:  $BUILD_DIR"
echo "nproc:  $(nproc)"

mkdir -p "$BUILD_DIR"
cmake -S "$SCRIPT_DIR" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD_DIR" -j"$(nproc)"

echo "== build complete =="
find "$BUILD_DIR" -maxdepth 3 -type f -executable -not -path "*/CMakeFiles/*" | sort
echo
echo "Run unit tests with: cd $BUILD_DIR && ctest --output-on-failure"
echo "(or directly:        $BUILD_DIR/node/tests/commsys_tests)"
