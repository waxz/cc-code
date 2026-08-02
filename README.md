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
  version, including two real bugs the port caught along the way.
- **`cpp/bench_reference/`** — standalone microbenchmarks (raw struct
  packing, FlatBuffers, ring buffer bandwidth, TCC JIT) used earlier
  to evaluate whether C++ was worth the port before committing to it.
- **`nim/`** — a Nim implementation of the same hot-path benchmarks,
  evaluated as a safer/more Python-like alternative to C++ (see
  `cpp/CPP_PORT_REPORT.md`'s sibling discussion for that comparison).

## Try it

```bash
# Python: full test suite + demo
cd python && python3 -m pytest tests/ -v
python3 demo_ros_like.py

# C++: compile and smoke-test
cd cpp/node
g++ -O2 -std=c++17 -I. bench/test_node_basic.cpp -o /tmp/t -lrt && /tmp/t
```

## CI

`.github/workflows/ci.yml` runs the Python test suite and a C++
compile-and-smoke-test on every push/PR. A separate `benchmark` job
(manually triggered, or on push to `main`) runs the full benchmark
sweep on GitHub's 4-vCPU runner and uploads the reports as a build
artifact — the first real multi-core data point for the scheduling
questions raised in `cpp/CPP_PORT_REPORT.md`, which were all measured
on a 1-vCPU sandbox up to that point.

Trigger it manually:
```bash
gh workflow run ci.yml
```
