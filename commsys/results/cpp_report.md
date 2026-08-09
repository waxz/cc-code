# commsys C++ benchmark report

Generated: 2026-08-09 07:33:40 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       1.0Gi        11Gi        45Mi       3.2Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Linux runnervmvrwv9 6.17.0-1020-azure #20~24.04.1-Ubuntu SMP Fri Jun 19 20:09:14 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
```

## Unit tests (ctest / Catch2)
```
Test project /home/runner/work/cc-code/cc-code/commsys/cpp/build
    Start 1: commsys_tests
1/1 Test #1: commsys_tests ....................   Passed   27.38 sec

100% tests passed, 0 tests failed out of 1

Total Test time (real) =  27.46 sec
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
[keep_latest] sent=351583 (unpaced firehose)
[keep_latest] dispatched=350240
[keep_latest] mean=0.0068ms p50=0.0066ms p99=0.0093ms max=0.0715ms
-- test_ring_stress --
[fifo ring] sent=536330 (unpaced firehose)
[fifo ring] dispatched=536330 drops=0
[fifo ring] mean=0.0080ms p50=0.0054ms p99=0.0266ms max=1.1105ms
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
| 500Hz shm                    |     1209 |      0 |     0.0155 MB/s |    0.0009ms |    0.0186ms |    0.0249ms |
| 1000Hz shm                   |     2345 |      0 |     0.0300 MB/s |    0.0007ms |    0.0105ms |    0.0193ms |
| 2000Hz shm                   |     4420 |      0 |     0.0566 MB/s |    0.0006ms |    0.0084ms |    0.0256ms |
| 5000Hz shm                   |     9447 |      0 |     0.1209 MB/s |    0.0006ms |    0.0075ms |    0.0737ms |
| 10000Hz shm                  |    15037 |      0 |     0.1925 MB/s |    0.0006ms |    0.0084ms |    0.0195ms |
| 500Hz udp                    |     1209 |      0 |     0.0155 MB/s |    0.0093ms |    0.0146ms |    0.0576ms |
| 1000Hz udp                   |     2339 |      0 |     0.0299 MB/s |    0.0101ms |    0.0161ms |    0.0544ms |
| 2000Hz udp                   |     4412 |      0 |     0.0565 MB/s |    0.0087ms |    0.0151ms |    0.0532ms |
| 5000Hz udp                   |     9373 |      0 |     0.1200 MB/s |    0.0087ms |    0.0147ms |    0.0461ms |
| 10000Hz udp                  |    14816 |      0 |     0.1896 MB/s |    0.0098ms |    0.0174ms |    0.0537ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0256ms |    0.0383ms |    0.0383ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0213ms |    0.0482ms |    0.0482ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0182ms |    0.0472ms |    0.0472ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0175ms |    0.0260ms |    0.0480ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0727ms |    0.1112ms |    0.1112ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0606ms |    0.1191ms |    0.1191ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0554ms |    0.1143ms |    0.1143ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0549ms |    0.0797ms |    0.1136ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   547732 |      0 | 17948.0822 MB/s |    0.0074ms |    0.0261ms |    0.7052ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  308999 dispatched=  308999 drops=     0 mean=  0.0092ms p50=  0.0082ms p99=  0.0281ms max=   0.5986ms
unpinned                                 sent=  316412 dispatched=  316412 drops=     0 mean=  0.0139ms p50=  0.0081ms p99=  0.0462ms max=   1.2794ms
unpinned                                 sent=  243967 dispatched=  243967 drops=     0 mean=  0.0107ms p50=  0.0098ms p99=  0.0297ms max=   0.6041ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent=  329846 dispatched=  329846 drops=     0 mean=  0.0126ms p50=  0.0081ms p99=  0.0516ms max=   0.9443ms
pinned                                   sent=  363103 dispatched=  363103 drops=     0 mean=  0.0139ms p50=  0.0080ms p99=  0.0526ms max=   0.9745ms
pinned                                   sent=  339014 dispatched=  339014 drops=     0 mean=  0.0130ms p50=  0.0082ms p99=  0.0503ms max=   0.9224ms
```
