#!/usr/bin/env bash
# python/build.sh -- install the Python module's dependencies.
# "Build" here means "make the interpreter environment ready" --
# there's no compilation step for the Python module itself.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "== commsys/python build (dependency install) =="
echo "python: $(python3 --version)"

PIP_FLAGS="--break-system-packages"
python3 -m pip install $PIP_FLAGS -q \
  pytest pytest-asyncio pytest-benchmark \
  msgpack numpy flatbuffers

echo "== dependencies installed =="
python3 -c "import msgpack, numpy, flatbuffers, pytest; print('all imports OK')"
