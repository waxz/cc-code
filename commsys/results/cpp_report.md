# commsys C++ benchmark report

Generated: 2026-08-14 17:12:56 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       1.0Gi        11Gi        45Mi       3.1Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Linux runnervmzvulz 6.17.0-1022-azure #22-Ubuntu SMP Mon Jul 27 17:24:03 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
```

## Unit tests (ctest / Catch2)
```
Test project /home/runner/work/cc-code/cc-code/commsys/cpp/build
    Start 1: commsys_tests
1/1 Test #1: commsys_tests ....................   Passed   34.39 sec

100% tests passed, 0 tests failed out of 1

Total Test time (real) =  34.63 sec
```

## Smoke tests
```
-- test_node_basic --
[sub] received 5 messages:
  hello-0
  hello-1
  hello-2
  hello-3
  hello-4
subscriber exit status: 0
-- test_node_udp_latest --
[udp] received 5/5
[keep_latest] sent=381733 (unpaced firehose)
[keep_latest] dispatched=379290
[keep_latest] mean=0.0064ms p50=0.0063ms p99=0.0089ms max=0.0568ms
-- test_ring_stress --
[fifo ring] sent=301121 (unpaced firehose)
[fifo ring] dispatched=301121 drops=0
[fifo ring] mean=0.0094ms p50=0.0084ms p99=0.0281ms max=0.6346ms
-- test_typed_api --
[sub] received 5 ImuSample messages
[sub] received 3 RawBytes blobs
typed API end-to-end test: PASS
```

## Full benchmark sweep

# commsys C++ benchmark report

Same scenario matrix as benchmark_report.py, same machine, same 2.5s steady-state duration after 0.8s discovery settle.

## 1. IMU rate sweep (single publisher -> single subscriber, 32B payload)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 500Hz shm                    |     1209 |      0 |     0.0155 MB/s |    0.0009ms |    0.0168ms |    0.0291ms |
| 1000Hz shm                   |     2342 |      0 |     0.0300 MB/s |    0.0008ms |    0.0121ms |    0.0292ms |
| 2000Hz shm                   |     4415 |      0 |     0.0565 MB/s |    0.0007ms |    0.0100ms |    0.0247ms |
| 5000Hz shm                   |     9446 |      0 |     0.1209 MB/s |    0.0006ms |    0.0079ms |    0.0263ms |
| 10000Hz shm                  |    15107 |      0 |     0.1934 MB/s |    0.0006ms |    0.0080ms |    0.0264ms |
| 500Hz udp                    |     1209 |      0 |     0.0155 MB/s |    0.0088ms |    0.0157ms |    0.0606ms |
| 1000Hz udp                   |     2340 |      0 |     0.0300 MB/s |    0.0094ms |    0.0165ms |    0.0573ms |
| 2000Hz udp                   |     4419 |      0 |     0.0566 MB/s |    0.0076ms |    0.0122ms |    0.0578ms |
| 5000Hz udp                   |     9306 |      0 |     0.1191 MB/s |    0.0093ms |    0.0163ms |    0.0591ms |
| 10000Hz udp                  |    14869 |      0 |     0.1903 MB/s |    0.0090ms |    0.0156ms |    0.0569ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0300ms |    0.0411ms |    0.0411ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0235ms |    0.0500ms |    0.0500ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0191ms |    0.0562ms |    0.0562ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0178ms |    0.0313ms |    0.0506ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0786ms |    0.1113ms |    0.1113ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0869ms |    0.1305ms |    0.1305ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0756ms |    0.1276ms |    0.1276ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0550ms |    0.0785ms |    0.1115ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   287491 |      0 |  9420.5051 MB/s |    0.0100ms |    0.0287ms |    0.9776ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  287854 dispatched=  287854 drops=     0 mean=  0.0097ms p50=  0.0086ms p99=  0.0286ms max=   0.7080ms
unpinned                                 sent=  312207 dispatched=  312207 drops=     0 mean=  0.0089ms p50=  0.0081ms p99=  0.0275ms max=   0.6321ms
unpinned                                 sent=  309053 dispatched=  309053 drops=     0 mean=  0.0092ms p50=  0.0082ms p99=  0.0281ms max=   0.6156ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent=  878079 dispatched=       0 drops=     0 mean=  0.0000ms p50=  0.0000ms p99=  0.0000ms max=   0.0000ms
pinned                                   sent=  341409 dispatched=  341409 drops=     0 mean=  0.0136ms p50=  0.0083ms p99=  0.0502ms max=   1.0397ms
pinned                                   sent=  315281 dispatched=  315281 drops=     0 mean=  0.0130ms p50=  0.0087ms p99=  0.0488ms max=   0.9904ms
```

## Pub/sub workflow benchmark

Realistic multi-topic workflow (imu=100Hz, encoder=50Hz, pose=20Hz),
as opposed to the isolated single-topic sweeps and unpaced firehose
stress tests above. Same workflow exists in Python for direct
comparison -- see PUBSUB_WORKFLOW_COMPARISON.md.
```
# commsys C++ pub/sub workflow benchmark (transport=shm, duration=5.0s)

Workflow: one publisher, one subscriber, three concurrent topics at
realistic robot sensor rates (imu=100Hz, encoder=50Hz, pose=20Hz).

| topic      |   sent | recv'd |  drops | mean(ms) |  p99(ms) |  max(ms) |
|------------|--------|--------|--------|----------|----------|----------|
| imu        |    500 |    500 |      0 |   0.0010 |   0.0252 |   0.0318 |
| encoder    |    250 |    250 |      0 |   0.0011 |   0.0248 |   0.0270 |
| pose       |    100 |    100 |      0 |   0.0014 |   0.0277 |   0.0277 |
# commsys C++ pub/sub workflow benchmark (transport=udp, duration=5.0s)

Workflow: one publisher, one subscriber, three concurrent topics at
realistic robot sensor rates (imu=100Hz, encoder=50Hz, pose=20Hz).

| topic      |   sent | recv'd |  drops | mean(ms) |  p99(ms) |  max(ms) |
|------------|--------|--------|--------|----------|----------|----------|
| imu        |    500 |    500 |      0 |   0.0107 |   0.0183 |   0.0610 |
| encoder    |    250 |    250 |      0 |   0.0062 |   0.0122 |   0.0181 |
| pose       |    100 |    100 |      0 |   0.0060 |   0.0078 |   0.0078 |
```
