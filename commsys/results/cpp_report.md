# commsys C++ benchmark report

Generated: 2026-08-08 15:52:05 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       1.0Gi        11Gi        45Mi       3.0Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Linux runnervmvrwv9 6.17.0-1020-azure #20~24.04.1-Ubuntu SMP Fri Jun 19 20:09:14 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
```

## Unit tests (ctest / Catch2)
```
Test project /home/runner/work/cc-code/cc-code/commsys/cpp/build
    Start 1: commsys_tests
1/1 Test #1: commsys_tests ....................   Passed   27.39 sec

100% tests passed, 0 tests failed out of 1

Total Test time (real) =  27.47 sec
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
[keep_latest] sent=156860 (unpaced firehose)
[keep_latest] dispatched=155751
[keep_latest] mean=0.0142ms p50=0.0140ms p99=0.0217ms max=0.0498ms
-- test_ring_stress --
[fifo ring] sent=428490 (unpaced firehose)
[fifo ring] dispatched=428490 drops=0
[fifo ring] mean=0.0077ms p50=0.0068ms p99=0.0266ms max=0.5860ms
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
| 500Hz shm                    |     1200 |      0 |     0.0154 MB/s |    0.0015ms |    0.0294ms |    0.0340ms |
| 1000Hz shm                   |     2354 |      0 |     0.0301 MB/s |    0.0011ms |    0.0206ms |    0.0512ms |
| 2000Hz shm                   |     4453 |      0 |     0.0570 MB/s |    0.0010ms |    0.0150ms |    0.0318ms |
| 5000Hz shm                   |     9539 |      0 |     0.1221 MB/s |    0.0009ms |    0.0113ms |    0.0300ms |
| 10000Hz shm                  |    15526 |      0 |     0.1987 MB/s |    0.0009ms |    0.0089ms |    0.0286ms |
| 500Hz udp                    |     1200 |      0 |     0.0154 MB/s |    0.0177ms |    0.0341ms |    0.0781ms |
| 1000Hz udp                   |     2354 |      0 |     0.0301 MB/s |    0.0086ms |    0.0154ms |    0.0716ms |
| 2000Hz udp                   |     4449 |      0 |     0.0569 MB/s |    0.0081ms |    0.0147ms |    0.0729ms |
| 5000Hz udp                   |     9562 |      0 |     0.1224 MB/s |    0.0076ms |    0.0148ms |    0.0693ms |
| 10000Hz udp                  |    15488 |      0 |     0.1982 MB/s |    0.0075ms |    0.0126ms |    0.0684ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0377ms |    0.0535ms |    0.0535ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0317ms |    0.0728ms |    0.0728ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0253ms |    0.0643ms |    0.0643ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0226ms |    0.0418ms |    0.0632ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0926ms |    0.1340ms |    0.1340ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0774ms |    0.1377ms |    0.1377ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0664ms |    0.1303ms |    0.1303ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0608ms |    0.0883ms |    0.1399ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   253443 |      0 |  8304.8202 MB/s |    0.0107ms |    0.0270ms |    0.6395ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  380670 dispatched=  380670 drops=     0 mean=  0.0086ms p50=  0.0074ms p99=  0.0290ms max=   0.8428ms
unpinned                                 sent=  487916 dispatched=  487916 drops=     0 mean=  0.0077ms p50=  0.0062ms p99=  0.0281ms max=   0.8394ms
unpinned                                 sent=  348913 dispatched=  348913 drops=     0 mean=  0.0087ms p50=  0.0078ms p99=  0.0294ms max=   0.5792ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent=  316900 dispatched=  316900 drops=     0 mean=  0.0118ms p50=  0.0089ms p99=  0.0492ms max=   0.9634ms
pinned                                   sent=  345541 dispatched=  345541 drops=     0 mean=  0.0130ms p50=  0.0089ms p99=  0.0503ms max=   0.9932ms
pinned                                   sent=  331222 dispatched=  331222 drops=     0 mean=  0.0122ms p50=  0.0088ms p99=  0.0499ms max=   0.9771ms
```
