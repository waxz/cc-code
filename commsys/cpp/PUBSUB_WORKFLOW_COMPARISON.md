# Pub/sub workflow: C++ vs Python

Both `pubsub_workflow_benchmark` implementations run the identical
scenario: one publisher process, one subscriber process, three
concurrent topics at realistic robot sensor rates (`imu` 100Hz,
`encoder` 50Hz, `pose` 20Hz), for a fixed 5-second duration, on the
same machine. This is deliberately different from
`benchmark_report`'s isolated single-topic rate sweeps and unpaced
firehose stress tests -- it's the shape of load an actual robot's
perception/control stack looks like, not a worst-case probe.

Same measurement methodology as `benchmark_report` (per-message
`send_ns` timestamp, p50/p99/max latency in ms), same message field
layouts (`commsys::msg::{Imu,Encoder,Pose2D}` on the C++ side,
matching `struct.pack` layouts on the Python side), so the numbers
are apples-to-apples.

## Results (1-vCPU sandbox, shm transport, 5s duration)

| | C++ mean | C++ p99 | Python mean | Python p99 |
|---|---|---|---|---|
| imu (100Hz) | 0.0086-0.0126ms | 0.04-0.09ms | 0.63ms | 1.18ms |
| encoder (50Hz) | 0.0085-0.0160ms | 0.04ms | 0.59ms | 1.11ms |
| pose (20Hz) | 0.0083-0.0270ms | 0.04-1.93ms | 0.59ms | 1.90ms |

Zero drops on either side, across every run. C++ is roughly **50-100x
tighter on mean latency** here -- consistent with every other
comparison in this project (the C++ port report, the earlier p99
investigation), and for the same underlying reason: no interpreter
between "there's a message" and "the callback runs."

## A finding worth reporting on its own: the numbers were briefly backwards

While building this benchmark, the *first* measured result showed
the opposite of the table above: C++ mean latency around 3.2-3.9ms,
Python around 0.28-0.36ms -- **Python looking 10x faster**, contradicting
every other measurement in this project. That contradiction was
treated as a signal to investigate, not a surprising-but-valid result
to report as-is.

The cause: the C++ publisher's pacing loop (`while (now() < t_end) {
...; pub.spin_once(0); }`) was a completely unyielding busy-spin, the
same bug class already found and fixed twice elsewhere in this
project (the ring buffer's write backoff, the `keep_latest` slot's
write path) -- on this sandbox's single contended core, it starved
the subscriber's own tight polling loop of any natural scheduling
opportunity. Python's `await asyncio.sleep(0)` naturally yields on
every publish iteration; the C++ loop, freshly written for this
benchmark, didn't have the equivalent `sched_yield()` that
`Node::publish()` itself already has internally for exactly this
reason.

Adding one line (`sched_yield()` after `pub.spin_once(0)`) took C++
from 3.2-3.9ms mean to 0.008-0.017ms mean -- the numbers in the table
above. The lesson generalizes: **a missing yield point in a tight
loop can make a genuinely faster implementation measure as slower,
for reasons that have nothing to do with the work being measured** --
worth checking for explicitly whenever a benchmark result contradicts
established findings, rather than either dismissing the result or
reporting it uncritically.

## Reproducing this

```bash
# C++
cd cpp && ./build.sh
./build/node/pubsub_workflow_benchmark shm 5
./build/node/pubsub_workflow_benchmark udp 5

# Python
cd python
python3 pubsub_workflow_benchmark.py shm 5
python3 pubsub_workflow_benchmark.py udp 5
```

Both are wired into their module's `benchmark.sh` and therefore into
CI's `benchmark` job -- current numbers are in `commsys/results/
cpp_report.md` and `commsys/results/python_report.md`, regenerated on
every full benchmark run (manual `gh workflow run`, or push to
`main`).
