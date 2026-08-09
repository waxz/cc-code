# commsys C++ benchmark report

Generated: 2026-08-09 08:19:35 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       1.0Gi        11Gi        45Mi       3.1Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Linux runnervmvrwv9 6.17.0-1020-azure #20~24.04.1-Ubuntu SMP Fri Jun 19 20:09:14 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
```

## Unit tests (ctest / Catch2)
```
Test project /home/runner/work/cc-code/cc-code/commsys/cpp/build
    Start 1: commsys_tests
1/1 Test #1: commsys_tests ....................   Passed   27.38 sec

100% tests passed, 0 tests failed out of 1

Total Test time (real) =  27.48 sec
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
[keep_latest] sent=380937 (unpaced firehose)
[keep_latest] dispatched=377587
[keep_latest] mean=0.0064ms p50=0.0062ms p99=0.0074ms max=0.0290ms
-- test_ring_stress --
[fifo ring] sent=319156 (unpaced firehose)
[fifo ring] dispatched=319156 drops=0
[fifo ring] mean=0.0090ms p50=0.0080ms p99=0.0274ms max=0.6382ms
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
| 500Hz shm                    |     1208 |      0 |     0.0155 MB/s |    0.0009ms |    0.0152ms |    0.0314ms |
| 1000Hz shm                   |     2348 |      0 |     0.0301 MB/s |    0.0007ms |    0.0094ms |    0.0230ms |
| 2000Hz shm                   |     4425 |      0 |     0.0566 MB/s |    0.0006ms |    0.0087ms |    0.0253ms |
| 5000Hz shm                   |     9467 |      0 |     0.1212 MB/s |    0.0006ms |    0.0073ms |    0.0228ms |
| 10000Hz shm                  |    15164 |      0 |     0.1941 MB/s |    0.0006ms |    0.0076ms |    0.0235ms |
| 500Hz udp                    |     1209 |      0 |     0.0155 MB/s |    0.0088ms |    0.0176ms |    0.0549ms |
| 1000Hz udp                   |     2345 |      0 |     0.0300 MB/s |    0.0081ms |    0.0160ms |    0.2058ms |
| 2000Hz udp                   |     4418 |      0 |     0.0566 MB/s |    0.0082ms |    0.0148ms |    0.0536ms |
| 5000Hz udp                   |     9419 |      0 |     0.1206 MB/s |    0.0078ms |    0.0125ms |    0.0528ms |
| 10000Hz udp                  |    14952 |      0 |     0.1914 MB/s |    0.0090ms |    0.0161ms |    0.0477ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0264ms |    0.0395ms |    0.0395ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0198ms |    0.0507ms |    0.0507ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0153ms |    0.0483ms |    0.0483ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0173ms |    0.0299ms |    0.0520ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0714ms |    0.1101ms |    0.1101ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0641ms |    0.1248ms |    0.1248ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0559ms |    0.1003ms |    0.1003ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0539ms |    0.0758ms |    0.1056ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   451579 |      0 | 14797.3407 MB/s |    0.0080ms |    0.0262ms |    0.8670ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  298009 dispatched=  298009 drops=     0 mean=  0.0095ms p50=  0.0085ms p99=  0.0284ms max=   0.6291ms
unpinned                                 sent=  320706 dispatched=  320706 drops=     0 mean=  0.0088ms p50=  0.0079ms p99=  0.0274ms max=   0.6111ms
unpinned                                 sent=  315130 dispatched=  315130 drops=     0 mean=  0.0091ms p50=  0.0081ms p99=  0.0279ms max=   0.6398ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent=  323627 dispatched=  323627 drops=     0 mean=  0.0127ms p50=  0.0084ms p99=  0.0516ms max=   0.9257ms
pinned                                   sent=  880478 dispatched=       0 drops=     0 mean=  0.0000ms p50=  0.0000ms p99=  0.0000ms max=   0.0000ms
pinned                                   sent=  373526 dispatched=  373526 drops=     0 mean=  0.0145ms p50=  0.0078ms p99=  0.0553ms max=   0.9425ms
```
