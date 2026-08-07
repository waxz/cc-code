#!/usr/bin/env bash
# mapf-curved-lanes/build.sh -- install the module's Python dependencies.
# "Build" here means "make the interpreter environment ready" -- there's no
# compilation step for this module (it's pure Python; the optional
# Reeds-Shepp/OMPL dependency for the forklift planner is not yet wired up,
# see src/planners/forklift_planner.py).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "== mapf-curved-lanes build (dependency install) =="
echo "python: $(python3 --version)"

PIP_FLAGS="--break-system-packages"
python3 -m pip install $PIP_FLAGS -q \
  -r "$SCRIPT_DIR/requirements.txt" pytest pytest-cov

echo "== dependencies installed =="
python3 -c "import numpy, pytest; print('all imports OK')"
