# commsys

A high-efficiency local + resilient-network communication system,
built up in stages: shared-memory IPC, a resilient reliability layer
for lossy WiFi links, a ROS-like decentralized discovery/pub-sub
layer, and finally a C++ port of the latency-critical core with a
full benchmark comparison.

## Layout

- **`python/`** — the reference implementation. Shared-memory ring
  buffer and seqlock "latest value" primitive, a resilient
  reliable-UDP channel for lossy networks, decentralized node
  discovery, and a ROS-like pub/sub `Node` API. See
  [`python/README.md`](python/README.md) for the full architecture
  writeup, including the p99 latency investigation and fixes.
- **`cpp/node/`** — a C++ port of the discovery + pub/sub core (the
  part shown to actually have a latency bottleneck worth porting).
  See [`cpp/CPP_PORT_REPORT.md`](cpp/CPP_PORT_REPORT.md) for the full
  benchmark comparison and bottleneck analysis against the Python
  version, including two real bugs the port caught along the way, and
  [`cpp/node/API_GUIDE.md`](cpp/node/API_GUIDE.md) for how to actually
  use `Node` in new code -- typed messages, construction options, the
  event-loop-driving footgun that caused a real ~300ms latency bug,
  and error handling. [`cpp/node/ROSBAG_GUIDE.md`](cpp/node/ROSBAG_GUIDE.md)
  covers `commsys_bag`, a record/play/info CLI for topic sessions.
- **`cpp/bench_reference/`** — standalone microbenchmarks (raw struct
  packing, FlatBuffers, ring buffer bandwidth, TCC JIT) used earlier
  to evaluate whether C++ was worth the port before committing to it.
- **`nim/`** — a Nim implementation of the same hot-path benchmarks,
  evaluated as a safer/more Python-like alternative to C++ (see
  `cpp/CPP_PORT_REPORT.md`'s sibling discussion for that comparison).

## Try it

Each module has `build.sh` and `benchmark.sh` (see the repo-root
README for the convention). Quick start:

```bash
# Python
cd python && ./build.sh && ./benchmark.sh

# C++ (CMake-based; see cpp/CMakeLists.txt)
cd cpp && ./build.sh && ./benchmark.sh

# Nim
cd nim && ./build.sh && ./benchmark.sh
```

Reports land in `results/*_report.md`.

## CI

`.github/workflows/ci.yml` has two jobs: `test` (every push/PR) runs
each module's `build.sh` plus a quick smoke test; `benchmark` (manual
trigger via `gh workflow run`, or on push to `main`) runs each
module's full `build.sh && benchmark.sh` on GitHub's 4-vCPU runner and
commits the resulting reports straight into `results/` — the first
real multi-core data point for the scheduling questions raised in
`cpp/CPP_PORT_REPORT.md`, which were all measured on a 1-vCPU sandbox
up to that point.

Trigger it manually:
```bash
gh workflow run ci.yml
```

