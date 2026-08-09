# commsys C++ benchmark report

Generated: 2026-08-09 07:24:17 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       1.0Gi        10Gi        47Mi       4.8Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Linux runnervmvrwv9 6.17.0-1020-azure #20~24.04.1-Ubuntu SMP Fri Jun 19 20:09:14 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
```

## Unit tests (ctest / Catch2)
```
Test project /home/runner/work/cc-code/cc-code/commsys/cpp/build
    Start 1: commsys_tests
1/1 Test #1: commsys_tests ....................   Passed   27.38 sec

100% tests passed, 0 tests failed out of 1

Total Test time (real) =  27.38 sec
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
[keep_latest] sent=273631 (unpaced firehose)
[keep_latest] dispatched=81
[keep_latest] mean=0.0132ms p50=0.0119ms p99=0.0307ms max=0.0307ms
-- test_ring_stress --
[fifo ring] sent=474247 (unpaced firehose)
[fifo ring] dispatched=474247 drops=0
[fifo ring] mean=0.0096ms p50=0.0079ms p99=0.0259ms max=0.8914ms
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
| 500Hz shm                    |     1215 |      0 |     0.0156 MB/s |    0.0007ms |    0.0072ms |    0.0155ms |
| 1000Hz shm                   |     2364 |      0 |     0.0303 MB/s |    0.0007ms |    0.0058ms |    0.0215ms |
| 2000Hz shm                   |     4486 |      0 |     0.0574 MB/s |    0.0007ms |    0.0052ms |    0.0196ms |
| 5000Hz shm                   |     9710 |      0 |     0.1243 MB/s |    0.0006ms |    0.0046ms |    0.0293ms |
| 10000Hz shm                  |    15784 |      0 |     0.2020 MB/s |    0.0006ms |    0.0043ms |    0.0428ms |
| 500Hz udp                    |     1215 |      0 |     0.0156 MB/s |    0.0044ms |    0.0094ms |    0.0628ms |
| 1000Hz udp                   |     2361 |      0 |     0.0302 MB/s |    0.0045ms |    0.0069ms |    0.0409ms |
| 2000Hz udp                   |     4474 |      0 |     0.0573 MB/s |    0.0050ms |    0.0068ms |    0.0550ms |
| 5000Hz udp                   |     9722 |      0 |     0.1244 MB/s |    0.0039ms |    0.0050ms |    0.0548ms |
| 10000Hz udp                  |    15735 |      0 |     0.2014 MB/s |    0.0043ms |    0.0052ms |    0.0563ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0174ms |    0.0290ms |    0.0290ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0164ms |    0.0433ms |    0.0433ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0155ms |    0.0510ms |    0.0510ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0136ms |    0.0202ms |    0.0537ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0423ms |    0.1025ms |    0.1025ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0411ms |    0.1006ms |    0.1006ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0370ms |    0.1041ms |    0.1041ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0343ms |    0.0671ms |    0.1111ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   426518 |      0 | 13976.1418 MB/s |    0.0098ms |    0.0217ms |    1.0861ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  470458 dispatched=  470458 drops=     0 mean=  0.0093ms p50=  0.0079ms p99=  0.0257ms max=   0.5497ms
unpinned                                 sent=  486445 dispatched=  486445 drops=     0 mean=  0.0094ms p50=  0.0078ms p99=  0.0250ms max=   0.5565ms
unpinned                                 sent=  482373 dispatched=  482373 drops=     0 mean=  0.0094ms p50=  0.0079ms p99=  0.0262ms max=   0.5524ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent= 1247240 dispatched=       0 drops=     0 mean=  0.0000ms p50=  0.0000ms p99=  0.0000ms max=   0.0000ms
pinned                                   sent=  379760 dispatched=  379760 drops=     0 mean=  0.0092ms p50=  0.0080ms p99=  0.0186ms max=   0.8900ms
pinned                                   sent=  376634 dispatched=  376634 drops=     0 mean=  0.0093ms p50=  0.0080ms p99=  0.0187ms max=   0.8891ms
```
