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

- **[`mapf-curved-lanes/`](mapf-curved-lanes/)** — heterogeneous
  multi-agent path finding (forklifts + quadrupeds) on continuous,
  curved lane-graph maps instead of a grid, with load-dependent
  kinematics for wheeled agents (a laden forklift's turning radius and
  stability margin differ from an empty one). Lane-graph geometry,
  Frenet-frame conflict checking, and the CBS/PBS high-level
  conflict-tree search are implemented and unit-tested; the
  per-agent-class low-level planners (Reeds-Shepp for the forklift,
  a holonomic lattice planner for the quadruped) are scaffolded with
  the load-dependent kinematic model specified but curve generation
  not yet wired up — see
  [`mapf-curved-lanes/README.md`](mapf-curved-lanes/README.md) for
  current status and
  [`mapf-curved-lanes/docs/research_proposal.md`](mapf-curved-lanes/docs/research_proposal.md)
  for the research motivation and baselines (CL-CBS, HCBS).

## Module conventions

Every module directory follows the same shape:
- `build.sh` — compiles/installs whatever that module needs. Safe to
  run repeatedly.
- `benchmark.sh` — runs tests (where applicable) and the module's
  benchmark suite, writing a report to `<module>/results/<module>_report.md`.
- CI (`.github/workflows/ci.yml`) does nothing module-specific beyond
  calling these two scripts in order — the scripts are the source of
  truth for how to build and benchmark each module, runnable
  identically on a laptop or in CI.

## Benchmark reports

`<module>/results/` holds the latest committed benchmark report per
module, updated automatically by the `benchmark` job in CI (manual
trigger via `gh workflow run`, or automatically on push to `main`).
These are real numbers from GitHub's hosted runners, not just local
sandbox measurements. For `mapf-curved-lanes/`, the current report
covers unit tests and instance generation only — the solver itself is
partially stubbed, and the report says so explicitly rather than
reporting benchmark numbers that don't exist yet.
