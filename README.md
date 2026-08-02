# cc-code

Multi-module repository. Each top-level directory is an independent
module with its own build/benchmark scripts; CI just calls those
scripts rather than embedding build logic in the workflow itself.

## Modules

- **[`commsys/`](commsys/)** — a local + resilient-network
  communication system: shared-memory IPC, a resilient reliable-UDP
  channel for lossy WiFi, decentralized node discovery, a ROS-like
  pub/sub API, and a C++ port of the latency-critical core with a
  full benchmark comparison against the Python reference
  implementation. Three sub-modules of its own:
  [`commsys/python/`](commsys/python/) (reference implementation),
  [`commsys/cpp/`](commsys/cpp/) (CMake-built C++ port),
  [`commsys/nim/`](commsys/nim/) (Nim comparison benchmarks).

## Module conventions

Every module directory follows the same shape:
- `build.sh` — compiles/installs whatever that module needs. Safe to
  run repeatedly.
- `benchmark.sh` — runs tests (where applicable) and the module's
  benchmark suite, writing a report to `commsys/results/<module>_report.md`.
- CI (`.github/workflows/ci.yml`) does nothing module-specific beyond
  calling these two scripts in order — the scripts are the source of
  truth for how to build and benchmark each module, runnable
  identically on a laptop or in CI.

## Benchmark reports

`commsys/results/` holds the latest committed benchmark report per
module, updated automatically by the `benchmark` job in CI (manual
trigger via `gh workflow run`, or automatically on push to `main`).
These are real numbers from GitHub's hosted runners, not just local
sandbox measurements.
