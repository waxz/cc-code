# commsys C++ benchmark report

Generated: 2026-08-14 17:02:00 UTC

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

Total Test time (real) =  34.53 sec
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
[keep_latest] sent=365113 (unpaced firehose)
[keep_latest] dispatched=359915
[keep_latest] mean=0.0066ms p50=0.0065ms p99=0.0114ms max=0.0542ms
-- test_ring_stress --
[fifo ring] sent=313501 (unpaced firehose)
[fifo ring] dispatched=313501 drops=0
[fifo ring] mean=0.0090ms p50=0.0081ms p99=0.0275ms max=0.5624ms
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
| 500Hz shm                    |     1210 |      0 |     0.0155 MB/s |    0.0006ms |    0.0097ms |    0.0131ms |
| 1000Hz shm                   |     2347 |      0 |     0.0300 MB/s |    0.0006ms |    0.0082ms |    0.0171ms |
| 2000Hz shm                   |     4415 |      0 |     0.0565 MB/s |    0.0006ms |    0.0086ms |    0.0182ms |
| 5000Hz shm                   |     9438 |      0 |     0.1208 MB/s |    0.0006ms |    0.0073ms |    0.0138ms |
| 10000Hz shm                  |    15153 |      0 |     0.1940 MB/s |    0.0006ms |    0.0070ms |    0.0412ms |
| 500Hz udp                    |     1208 |      0 |     0.0155 MB/s |    0.0093ms |    0.0179ms |    0.0595ms |
| 1000Hz udp                   |     2339 |      0 |     0.0299 MB/s |    0.0096ms |    0.0153ms |    0.1232ms |
| 2000Hz udp                   |     4409 |      0 |     0.0564 MB/s |    0.0082ms |    0.0148ms |    0.0994ms |
| 5000Hz udp                   |     9273 |      0 |     0.1187 MB/s |    0.0096ms |    0.0156ms |    0.0370ms |
| 10000Hz udp                  |    14715 |      0 |     0.1884 MB/s |    0.0094ms |    0.0153ms |    0.0693ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0186ms |    0.0424ms |    0.0424ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0176ms |    0.0368ms |    0.0368ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0145ms |    0.0472ms |    0.0472ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0165ms |    0.0242ms |    0.0370ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0566ms |    0.1002ms |    0.1002ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0547ms |    0.0933ms |    0.0933ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0539ms |    0.1091ms |    0.1091ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0540ms |    0.0779ms |    0.1115ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   289341 |      0 |  9481.1259 MB/s |    0.0096ms |    0.0284ms |    0.5778ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  262353 dispatched=  262353 drops=     0 mean=  0.0104ms p50=  0.0093ms p99=  0.0295ms max=   0.8732ms
unpinned                                 sent=  307921 dispatched=  307921 drops=     0 mean=  0.0093ms p50=  0.0080ms p99=  0.0282ms max=   0.8533ms
unpinned                                 sent=  273863 dispatched=  273863 drops=     0 mean=  0.0101ms p50=  0.0090ms p99=  0.0290ms max=   0.8761ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent=  374735 dispatched=  374735 drops=     0 mean=  0.0145ms p50=  0.0078ms p99=  0.0543ms max=   1.1985ms
pinned                                   sent=  332541 dispatched=  332541 drops=     0 mean=  0.0132ms p50=  0.0083ms p99=  0.0519ms max=   1.2040ms
pinned                                   sent=  353893 dispatched=  353893 drops=     0 mean=  0.0137ms p50=  0.0079ms p99=  0.0520ms max=   1.2017ms
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
| imu        |    500 |    500 |      0 |   0.0007 |   0.0110 |   0.0162 |
| encoder    |    250 |    250 |      0 |   0.0008 |   0.0103 |   0.0159 |
| pose       |    100 |    100 |      0 |   0.0009 |   0.0130 |   0.0130 |
# commsys C++ pub/sub workflow benchmark (transport=udp, duration=5.0s)

Workflow: one publisher, one subscriber, three concurrent topics at
realistic robot sensor rates (imu=100Hz, encoder=50Hz, pose=20Hz).

| topic      |   sent | recv'd |  drops | mean(ms) |  p99(ms) |  max(ms) |
|------------|--------|--------|--------|----------|----------|----------|
| imu        |    500 |    500 |      0 |   0.0101 |   0.0182 |   0.0567 |
| encoder    |    250 |    250 |      0 |   0.0063 |   0.0133 |   0.0150 |
| pose       |    100 |    100 |      0 |   0.0060 |   0.0104 |   0.0104 |
```
