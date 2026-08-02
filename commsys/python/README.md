# commsys — local high-efficiency + resilient-network communication

A two-tier messaging system: near-zero-overhead shared memory for
processes on the same host, and a reliability layer on top of UDP for
peers reachable only over a lossy network like WiFi. `transport.py`
unifies both behind one API so application code doesn't care which
path a given peer uses.

## Modules

### `shared_memory_ipc.py` — local transport
- `SPSCRingBuffer`: lock-free single-producer/single-consumer ring
  buffer over `multiprocessing.shared_memory`. Producer only writes
  `write_idx`, consumer only writes `read_idx` — no lock needed on the
  hot path. Uses the doubled-modulus indexing trick to tell full from
  empty without wasting a slot. Backoff on wait is spin → yield →
  short sleep, tuned for low latency without pegging a core.
  **Benchmark in this environment: ~180-390k msg/s for small messages
  cross-process, and ~1.6-1.8 GB/s for large (64KB-4MB) payloads**
  (see `test_shm.py`).

  **A real bug was found and fixed here**: the original
  `_write_bytes`/`_read_bytes` used ctypes array slice assignment
  (`self._data[a:b] = data`), which looks like it should be a bulk
  memcpy but isn't — CPython's ctypes falls back to an element-by-
  element path for this case, measured at **~215x slower** than a
  real memcpy (0.036 GB/s vs 7.7 GB/s in isolation on this machine).
  This was invisible for the small messages the early benchmarks used
  (a few dozen bytes costs nothing either way) and only showed up once
  large payloads were actually tested. Fixed by switching to
  `ctypes.memmove`/`ctypes.string_at`, which go straight to the C
  implementation — a 100x improvement at 64KB payloads (0.017 GB/s →
  1.75 GB/s).

  The remaining gap to raw memory bandwidth (single-threaded `memcpy`
  measures 11.1 GB/s on this exact machine) is this sandbox's `nproc`
  == 1: with only one CPU core, the producer and consumer processes
  can't run concurrently at all, so every handoff costs a context
  switch. That's an environment constraint visible even in a tuned
  C++ version of the same ring buffer (~2.5 GB/s here) — on real
  multi-core hardware, cross-process bandwidth should scale much
  closer to the single-threaded ceiling, since producer and consumer
  can genuinely overlap instead of time-slicing one core.
- `MPMCQueue`: same ring buffer, guarded by a `multiprocessing.Lock`
  for correctness with multiple writers/readers. Requires the lock to
  come from a common parent process (fork/spawn model). For true
  independent processes without a shared ancestor, swap in a named
  POSIX semaphore (`posix_ipc`) — noted as the production path below.

### `network_resilience.py` — resilient transport
`ResilientChannel` wraps a UDP socket with:
- Sequence numbers + ACKs, sliding-window flow control
- Adaptive RTO (Jacobson/Karels estimator, same technique as TCP) so
  the retransmit timer tracks real conditions instead of a fixed guess
- Backoff multiplier that escalates on correlated timeouts but resets
  immediately on any successful ack, so a brief WiFi hiccup doesn't
  leave the timer pinned at its ceiling long after the link recovers
- Reorder buffer so the application always sees messages in order,
  even though UDP doesn't guarantee that
- Heartbeat/liveness detection and automatic reconnect with backoff +
  jitter, with an `on_reconnect` hook for state resync after a
  blackout (e.g. WiFi roaming between access points)
- A `LinkState` (HEALTHY / DEGRADED / DOWN) signal derived from a
  rolling loss-rate window, so the app or the unified transport can
  react — shed non-critical traffic, warn the user, fail over

**Reliability guarantee**: a message sent with `reliable=True` is
retried indefinitely (with backoff) until acked or the channel is
closed — it is never silently dropped. Dropping would leave a
permanent gap in the receiver's reorder buffer and stall every later
message, which defeats the point of "reliable." Validated in
`test_network.py` under a simulated 20% independent loss rate in each
direction (~36% round-trip loss): 100/100 messages delivered, in
order.

### `serialization.py`
Shared, pluggable serializer (msgpack if available, pickle fallback)
with 4-byte length-prefixed framing, used identically by both paths so
a peer can be moved from local to remote with a one-line config change.

### `transport.py` — unified API
`UnifiedTransport.connect_local(...)` for same-host peers,
`connect_remote(...)` for networked peers, then a single
`send(peer_id, message)` / `on_message` callback regardless of path.

### `discovery.py` + `node.py` — ROS-like node discovery and pub/sub
On top of the two transports above, `Node` gives you a ROS-style API:
`advertise(topic)`, `publish(topic, payload)`, `subscribe(topic, callback)`.
There's no central master process (unlike ROS1's `roscore`) — nodes find
each other via `discovery.py`, a decentralized table in shared memory
that any node can attach to by well-known name and use to see who else
is up and what they publish/subscribe. Each node heartbeats its own
entry; stale or crashed nodes (checked via PID liveness, not just a
heartbeat timeout) are pruned automatically.

Per-link transport is negotiated automatically and symmetrically by
both sides from the same discovery data: same host -> a dedicated
shared-memory ring per (publisher, subscriber) pair; different host ->
best-effort UDP (matching ROS2's default QoS for high-rate sensor
topics like IMU/LaserScan, where a dropped sample just means the next
one arrives on schedule rather than being worth an ACK round-trip).

See `demo_ros_like.py` for a 5-process graph (IMU + LiDAR publishers,
three subscribers split across shared-memory and UDP, including one
subscriber fanned out to both topics over the network) that measures
real bandwidth and latency end to end. Sample result from a 6s run:
zero drops on every link, sub-2ms p99 latency on both transports.

Two real concurrency bugs surfaced and got fixed while building this
(both documented inline in `discovery.py` and `shared_memory_ipc.py`):
a shared-memory ring buffer could be attached before its creator
finished initializing it, and an explicit zero-fill of a freshly
created discovery table raced against another process's legitimate
first write to it, silently erasing that write. Both are the kind of
bug that only shows up under real multi-process contention — exactly
why `demo_ros_like.py` spawns actual OS processes rather than
asyncio tasks pretending to be separate nodes.

## Pushing the limits: what got fixed, and the honest tradeoffs

Starting from the pushback that shared memory should hit multi-GB/s,
not the ~14 MB/s the pub/sub layer originally showed for large
payloads, four real issues got found and fixed by actually testing at
scale rather than trusting the earlier small-message numbers:

1. **The ctypes array-slicing bug** (see above) — 100x fix to the
   ring buffer's raw bulk-copy speed.
2. **UDP silently dropped 100% of oversized payloads.** A 1MB publish
   over `node.py`'s UDP path "succeeded" from the caller's point of
   view (`asyncio`'s fire-and-forget `sendto()` doesn't raise on this)
   while zero bytes ever arrived — real UDP datagrams cap around
   65KB. Fixed by porting `transport.py`'s MTU-safe chunking into
   `node.py`'s UDP path (it hadn't been there before, which was also
   the reason the earlier LaserScan-over-UDP benchmark numbers weren't
   trustworthy on a real network). This also surfaced a good lesson
   about chunking itself: splitting one message into N pieces makes it
   *more* fragile under loss, not less, since all N have to arrive
   for the message to reassemble at all — confirmed empirically when
   an unpaced 1MB/874-chunk stress test went from 0 delivered (buffer
   overflow) to partial delivery after raising the OS socket buffers,
   but never full delivery, because that's genuinely beyond what
   best-effort UDP without a reliability layer is for. Use shared
   memory (same host) or a reliable channel for that; UDP chunking
   fixed the correctness bug (silent 100% loss on an oversized
   datagram) without pretending to fix physics.
3. **Envelope packing did an extra full-payload copy.** `header +
   topic + sender + payload` chains `+`, and Python's last `+` in that
   chain copies the *entire* accumulated buffer including the payload
   into a new object. `b"".join(...)` computes the total size once and
   copies each piece exactly once. ~10% win, most valuable on the
   largest payloads.
4. **The default shared-memory ring was sized for the earlier tiny
   IMU messages, not general use.** 2MB holds barely two 1MB messages,
   so the publisher spent most of its time backoff-spinning waiting
   for the subscriber to drain rather than writing (confirmed via
   profiling: ~995 failed `try_write()` attempts per successful
   `write()`). Made configurable (`Node(..., shm_ring_capacity=...)`)
   and raised the default to 16MB. Result for 1MB messages: ~2x
   (0.54 -> ~1.0 GB/s through the full pub/sub stack, not just the
   raw ring buffer). Bigger isn't free, though, and this is worth
   stating plainly rather than only touting the throughput number: a
   bigger ring lets more messages queue up before backpressure kicks
   in, which raised p99 latency under sustained unpaced load (895ms
   in one large-scan stress test) even as throughput and drop count
   both improved. That's classic bufferbloat, not a bug -- size the
   ring for your actual burst behavior, not just "bigger is safer."

**Where the ceiling actually is in this environment:** single-threaded
`memcpy` measures 11.1 GB/s on this machine, matching what you'd
expect from real RAM bandwidth. But `nproc` here is 1 -- this sandbox
has exactly one CPU core, so a producer and consumer process can never
actually run concurrently; every ring-buffer handoff costs a context
switch, not just a memory copy. Confirmed this is an environment limit
rather than a remaining code issue by writing the identical ring
buffer design in tuned C++ (`-O3 -flto`) and testing it the same way:
it also caps around 2.5 GB/s here. On real multi-core hardware, where
producer and consumer can genuinely overlap, cross-process bandwidth
should scale much closer to that single-threaded ceiling.

```bash
python3 -m pytest tests/test_discovery.py tests/test_node.py -v
python3 demo_ros_like.py
```

```bash
python3 test_shm.py        # shared-memory ring buffer, cross-process
python3 test_network.py    # resilient channel under simulated loss
python3 example_demo.py    # both paths together via UnifiedTransport
```

## p99 latency: root cause and fix

Pushing large payloads at full speed exposed a p99 of 898ms (max
2500ms) -- a catastrophic, unbounded-looking tail on a system that's
supposed to be usable for control loops. Two distinct, layered causes,
both confirmed empirically rather than guessed at:

1. **OS thread starvation on a single core.** The shared-memory
   receive path ran on a separate OS thread, blocking on `ring.read()`
   and marshaling back via `call_soon_threadsafe`. Nothing guarantees
   an OS scheduler gives a background thread timely CPU access
   relative to the main event-loop thread. Proof: the *first*
   dispatched message showed 2500ms latency, decreasing steadily to
   60ms over the run -- the reader thread was starved for ~2.5 seconds
   before it ran even once.
2. **A blocking `time.sleep()` inside the ring's write-backoff path**,
   called synchronously from `publish()`. Since asyncio is
   single-threaded, this doesn't just block the current task -- it
   blocks the *entire event loop*, including any reader task that
   would otherwise drain the ring. A real deadlock-shaped starvation:
   the publisher can't proceed because the ring is full, and the ring
   can't drain because the reader never gets scheduled while the
   publisher is blocked.

**Fix:** converted the shared-memory reader from an OS thread to a
cooperative asyncio task (shares the event loop's own fair task-queue
rotation instead of depending on OS thread scheduling), and made
`publish()`'s ring-write path poll with `try_write()` +
`asyncio.sleep()` instead of the blocking call. Result on the same
stress scenario: **p99 898ms -> 142ms, max 2500ms -> 152ms** (a bounded
plateau, not an unbounded tail), and a simpler same-process benchmark
went from 4,392 messages processed to 144,744 (33x) with p99 down to
3.2ms.

**The remaining ~150ms tail** (about 4% of messages, in ~50 recurring
blocks spread through the run, not just startup) didn't respond to
`SCHED_FIFO` -- expected, since that's a cooperative asyncio scheduling
matter within one process, not OS thread/process scheduling. Rather
than keep chasing individual milliseconds of scheduling jitter on a
single core (diminishing returns, and this specific ceiling is an
environment artifact, not a design flaw), the fix was to change the
question: for topics where a control loop needs the *freshest* sample
more than it needs *every* sample, bound staleness instead of
per-message latency. That's `LatestValueSlot` and `subscribe(...,
keep_latest=True)` (see `node.py`/`shared_memory_ipc.py`) -- the same
idea as ROS2's "keep last 1" QoS depth: a lock-free single-slot
seqlock where writes never block regardless of a slow or stalled
reader, so a subscriber always gets the most recent sample instead of
working through a backlog to get there.

Result under the identical unpaced-firehose stress that produced
898ms p99 on the FIFO ring: **p99 = 0.13ms, max = 2.4ms** in the
realistic cross-process case (over 1000x tighter), and the publisher's
send rate (229k+ messages/2.5s) had no effect on tail latency at all,
which is the actual point -- staleness is bounded by the poll
interval (1ms), not by how far the publisher races ahead.

**The honest tradeoff, stated plainly:** `keep_latest=True` means a
slow subscriber sees only the latest value, never a backlog -- it can
and will miss intermediate samples under load. That's correct for a
live sensor feed driving a control loop (IMU, pose) and wrong for
anything that needs every message delivered (event logs, discrete
commands) -- for those, the default FIFO ring is still there and still
guarantees in-order, complete delivery, just without the same latency
bound.

## Production hardening notes (what a reference impl doesn't cover)
- **Local IPC notification**: this uses spin/yield/sleep backoff for
  portability with zero dependencies. For lower CPU usage under
  bursty load, swap in a named POSIX semaphore or `eventfd` (via
  `posix_ipc`) so a waiting consumer blocks in the kernel instead of
  polling.
- **MPMC correctness**: the demo lock model assumes a common parent
  process. For unrelated processes, use a named semaphore rather than
  `multiprocessing.Lock`.
- **Wire protocol robustness**: this hand-rolled reliable-UDP protocol
  is a reference implementation of the *ideas* (RTO estimation,
  windowing, reorder buffering, heartbeats). For traffic that matters
  in production, prefer a hardened implementation of the same ideas —
  QUIC, KCP, or ENet — which also add congestion control tuned against
  real-world loss/jitter distributions and, for QUIC, transport-level
  encryption.
- **Security**: neither module authenticates or encrypts payloads.
  Add TLS/DTLS (or QUIC, which bundles it) before this leaves a
  trusted LAN.
- **Backpressure across the unified transport**: currently `send()`
  on the local path blocks the calling thread if the ring is full;
  on the remote path it awaits window space. Both are intentional
  (apply backpressure to the sender rather than dropping), but an app
  with a strict latency budget should set a timeout and decide what to
  do when it's exceeded (drop, spill to disk, alert).
