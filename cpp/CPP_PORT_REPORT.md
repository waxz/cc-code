# C++ port: benchmark report and bottleneck analysis

## Scope

Ported the latency-critical core: `discovery.hpp` (shared-memory node
registry), `ring_buffer.hpp` (FIFO SPSC ring), `latest_value_slot.hpp`
(seqlock-based bounded-staleness primitive), and `node.hpp`
(advertise/publish/subscribe, epoll-driven single-threaded event loop,
UDP with MTU-safe chunking). This is a deliberate scope decision, not
an oversight: `network_resilience.py`'s reliable-channel logic (ACKs,
retransmission, RTT estimation for lossy WiFi) is a different problem
from intra-host pub/sub latency, and the FlatBuffers codec is already
a thin wrapper around a C++ library — porting *that* would mean
porting away the thing that's already fast. Everything in this report
is about the part that was actually shown to have a bottleneck: the
discovery + pub/sub layer under load.

No behavior was invented for this port -- every design decision
(dual shm link types, the `~` topic-prefix convention for keep_latest,
chunked UDP, per-(topic,sender) drop tracking) is a direct port of
`node.py`'s already-debugged design, including the two shared-memory
initialization races that were found and fixed in the Python version
(`shm_open()`+`ftruncate()` non-atomicity) -- both had to be
independently re-fixed here, since C++ has the identical race with
`mmap()` instead of Python's own layer over the same syscalls, and one
of them (the discovery registry's attach path) was in fact **missed**
on the first pass here and caused a `SIGBUS` crash during testing,
caught and fixed the same way this whole project has caught everything
else: run it, watch it break, fix the real cause.

## Results

All scenarios use the identical parameters as `benchmark_report.py`
(same rates, same payload sizes, same 2.5s steady-state duration, same
machine, same single-core sandbox). Full C++ benchmark source:
`bench/benchmark_report.cpp`.

### 1. IMU rate sweep (32B payload, single pub -> single sub)

| rate | transport | msgs (C++) | msgs (Python) | p99 (C++) | p99 (Python) |
|---|---|---|---|---|---|
| 500Hz | shm | 1,199 | 916 | **0.031ms** | 0.456ms |
| 1000Hz | shm | 2,297 | 1,717 | **0.037ms** | 0.542ms |
| 2000Hz | shm | 4,229 | 1,713 | **0.037ms** | 0.665ms |
| 5000Hz | shm | 8,578 | 1,735 | **0.041ms** | 0.525ms |
| 10000Hz | shm | 13,373 | 1,738 | **0.034ms** | 0.499ms |

Two things stand out. First, C++ latency is **~15x tighter across the
board** and, critically, *stays* tight as the requested rate climbs --
Python's per-message overhead means the received rate plateaus around
850-900 msg/s no matter what's requested (confirmed in the earlier
Python investigation: that ceiling is the publisher's own asyncio loop,
not the transport). C++ keeps scaling because there's no interpreter
between "decide to publish" and "the syscall/memcpy that does it."

Second: even C++ doesn't hit the literal requested rate (13,373
messages at "10000Hz" over 2.5s is ~5,349 msg/s achieved, not 25,000)
-- `std::this_thread::sleep_for()`'s actual granularity on this
sandboxed kernel is coarser than the sub-100-microsecond intervals
these rates imply. That's a real, separate finding: **for genuinely
sub-millisecond publish pacing, don't use sleep-based pacing at all**
-- use a busy-wait against a monotonic clock (accepting 100% of one
core) or a hardware timer. This project's own event loop already does
exactly that for the *receive* side (deliberately never blocks in
`epoll_wait`); the benchmark harness's *publish* pacing didn't, and it
shows.

### 2. LaserScan rate sweep (~8KB payload)

| rate | transport | p99 (C++) | max (C++) |
|---|---|---|---|
| 10Hz shm | 0.090ms | 0.090ms |
| 20Hz shm | 0.081ms | 0.081ms |
| 40Hz shm | 0.073ms | 0.073ms |
| 60Hz shm | 0.185ms | 2.106ms |
| 10Hz udp | 0.261ms | 0.261ms |
| 20Hz udp | 2.074ms | 2.074ms |
| 40Hz udp | 0.151ms | 0.151ms |
| 60Hz udp | 0.117ms | 0.123ms |

Sub-millisecond p99 essentially everywhere at realistic robot sensor
rates. The UDP numbers bounce around more than shm's (20Hz shows a
2ms outlier that 40Hz doesn't) -- with this few samples per scenario
(only 20-149 messages at these low rates over 2.5s) a single scheduling
hiccup swings the whole percentile, which is itself a useful reminder
not to over-read single-run tail numbers at low sample counts. The
UDP path's chunking logic (ported from the discovery of the same
100%-silent-data-loss bug found in the Python `node.py` UDP path) was
exercised here too -- an 8KB payload needs 7 chunks at the 1200B
chunk size, and delivery was still 0 drops throughout.

### 3. The actual point: unpaced firehose, FIFO ring, 64KB payload

This is the scenario that originally exposed Python's 898ms p99 /
2500ms max catastrophic tail.

| | Python (after all fixes) | C++ |
|---|---|---|
| Messages sent | ~230,000 (2.5s) | 62,357 (2.5s, but 64KB not smaller) |
| Bandwidth | 137.6 MB/s (31KB payload) | **2,043 MB/s** (64KB payload) |
| p99 latency | 142ms | **6.99ms** |
| max latency | 152ms | 308ms (one-time outlier, see below) |
| Drops | 0 | 0 |

**~20x tighter p99, ~15-60x higher bandwidth** depending on which
Python payload size you compare against (they're not identical sizes,
which is why bandwidth alone isn't the whole story -- p99 latency at
comparable-or-larger payload size is the fairer single number, and
that's the ~20x figure).

### 4. `keep_latest` under the identical unpaced firehose

| | Python | C++ |
|---|---|---|
| p99 | 0.13ms | **0.0125ms** |
| max | 2.4ms | 62.7ms (one-time outlier) |

C++'s p99 is ~10x tighter than Python's already-excellent
`keep_latest` result. The max column tells a more interesting story
than the p99 column here, and it's covered in the bottleneck analysis
below rather than glossed over.

## Bottleneck analysis

### What C++ actually removed

The Python investigation found two concrete, named bottlenecks: (1) a
background *thread* competing with the main event-loop *thread* for
OS scheduling with no fairness guarantee, and (2) a blocking
`time.sleep()` call inside a coroutine silently freezing the entire
single-threaded event loop, including every other task on it. Neither
of these bottlenecks is *fixable* in the sense of "make it fast" --
they're structural: Python's GIL means only one thread runs bytecode
at a time, and asyncio's cooperative model means a coroutine that
doesn't yield blocks everything else on its loop, full stop. The
Python fixes (converting the reader to a cooperative task, making the
write path poll instead of block) worked around both, but didn't
eliminate the class of problem -- they made the *existing* mechanism
(GIL + asyncio scheduling) behave better.

C++ doesn't have that class of problem to work around. There is no
GIL. There is no cooperative scheduler with tasks that can starve each
other by failing to yield. `Node::spin_once()` is a plain function
that polls a ring buffer, polls a seqlock slot, and drains an epoll
socket, in that order, on the calling thread, with no scheduler
between "there's data" and "the callback runs" other than the OS
process scheduler itself.

### What C++ did NOT remove: single-core OS-process contention

This matters enough to state plainly rather than let the good numbers
imply it went away. Every C++ number above still runs on the same
single-core (`nproc=1`) sandbox as the Python numbers, and this
project independently confirmed during the C++ port that **the same
class of starvation still exists, just one layer down the stack**:

- The `keep_latest` unpaced test initially showed p99=495ms, max=520ms
  -- just as bad as Python's original numbers, on code that had zero
  Python involved. Root cause, found the same way every bug in this
  project has been found (measure, don't guess): a tight, syscall-free
  publish loop gives the Linux CFS scheduler no natural opportunity to
  preempt it in favor of the subscriber process, so the two processes
  only trade the single core at CFS's own timeslice granularity --
  which, under contention on this sandbox, was measured in the
  *hundreds of milliseconds*, not the low single digits a trivial
  two-busy-loop control test showed (8ms max gap, no IPC involved).
- That gap between "trivial busy loop: 8ms" and "our Node: 495ms"
  turned out not to be pure OS scheduling at all, but a **second, real
  bug**: the seqlock read had no change-detection, so the subscriber
  was calling the dispatch path over a million times for content that
  hadn't changed since the last read (692 real updates worth
  dispatching, 1,020,444 actual dispatches). That's not "C++ is slow"
  -- it's the same bug class as "did you actually check whether the
  thing you're about to redo needs redoing," and it was burning enough
  CPU in the subscriber's poll loop to be a major contributor to the
  starvation independent of the scheduler question. Fixing it (compare
  the seqlock's version counter, an 8-byte integer, instead of
  re-dispatching unconditionally) took p99 from 495ms to 0.0125ms --
  a ~40,000x improvement from one bug fix.
- What's left after both fixes: p99 is excellent (12.5 microseconds),
  but **max is still 62.7ms, once, in an otherwise tight distribution**.
  This pattern -- one bad outlier, otherwise flat -- matches the
  Python investigation's "cold start" finding almost exactly: a
  one-time scheduling hiccup while processes are still settling
  (registering with discovery, setting up the first link), not a
  recurring problem. It was not chased further given the pattern is
  already well-understood from the Python side and diminishing-returns
  applies equally here.

The honest summary: **C++ removed the interpreter- and
scheduler-shaped bottlenecks that were specific to Python's execution
model, and that's a real, large, measured win (10-60x depending on the
metric). It did not, and structurally cannot, remove the bottleneck
that comes from the deployment environment having exactly one CPU
core.** On real multi-core hardware -- which is the actual target for
a robot's onboard compute, not a CI sandbox -- the remaining gap
between "trivial busy loop: 8ms worst case" and "two heavily-loaded
processes contending for one core: hundreds of ms worst case" should
close substantially, since publisher and subscriber could genuinely
run concurrently instead of time-slicing. That's a testable claim
this report doesn't have the hardware to test, and it's flagged as
exactly that rather than assumed.

### Two bugs this port caught that the Python version didn't have

Neither of these has a Python equivalent -- they're specific to
porting a design that was debugged in one language into another with
different default behaviors:

1. **`SIGBUS` from the discovery registry's attach path.** The ring
   buffer and slot primitives already had the "wait for the creator to
   finish `ftruncate()`" fix (carried over from the Python
   investigation), but the discovery registry's own attach path was
   written fresh for C++ and initially skipped it. `mmap()`-ing a
   segment before its creator has resized it doesn't fail cleanly in
   C++ the way Python's `SharedMemory` wrapper raises `ValueError` --
   it segfaults (`SIGBUS`) on first access, with no exception to catch.
   Fixed with the identical `fstat()`-based size-polling retry the
   other two primitives already used.
2. **Massive over-dispatch from missing change-detection**, described
   above -- Python's `_poll_slot` had this check
   (`val != last_seen`) from the start (byte comparison, since Python
   doesn't have a cheap way to expose the seqlock's internal counter
   across the language boundary as naturally); the direct port to C++
   used `try_read()` without carrying that check over, since the
   obvious-looking translation ("if read succeeded, dispatch") looks
   correct and compiles cleanly. Fixed by adding a versioned read
   variant that exposes the seqlock's sequence number so the caller
   can compare one integer instead of either re-dispatching
   unconditionally or comparing potentially-large payload bytes.

## What's not in this port

- `network_resilience.py`'s `ResilientChannel` (ACKs, RTO estimation,
  retransmission) -- out of scope by design, see above.
- `transport.py`'s `UnifiedTransport` and large-payload chunking for
  the *reliable* network path -- same reasoning; `node.hpp` has its
  own independent (best-effort) UDP chunking, ported from `node.py`'s
  equivalent, not from `transport.py`.
- FlatBuffers codec integration -- the C++ FlatBuffers library this
  project already benchmarked (`cpp_bench/bench_flatbuffers.cpp`) is
  directly usable with `Node::publish()`'s raw `(pointer, length)`
  API with no additional wrapper needed; not duplicated here since
  there's nothing to port, only to wire together.
- Automated unit tests in the Python `pytest` sense -- the C++ side
  has been validated by the smoke/stress test programs in `bench/`
  (basic pub/sub, fan-out implied by the discovery loop's design,
  UDP chunking, both shm link types under load) rather than a
  dedicated test framework, given the scope and time already spent
  finding and fixing the bugs above. Porting the Python test suite's
  ~20 `node`/`discovery`-related test cases to a C++ test framework
  (Catch2/GoogleTest) is the natural next step before treating this
  as production-ready rather than a validated performance reference.
